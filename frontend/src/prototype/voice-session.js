const DEFAULT_RESTART_DELAY_MS = 260;

export class BrowserSpeechRecognitionAdapter {
  constructor({ win = window, lang = "zh-CN" } = {}) {
    this.win = win;
    this.lang = lang;
    this.recognition = null;
    this.started = false;
  }

  isSupported() {
    return Boolean(this._RecognitionCtor());
  }

  start(handlers) {
    const RecognitionCtor = this._RecognitionCtor();
    if (!RecognitionCtor) {
      handlers.onError?.(new Error("当前浏览器不支持 Web Speech API"));
      return;
    }

    if (!this.recognition) {
      this.recognition = new RecognitionCtor();
      this.recognition.lang = this.lang;
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 1;
    }

    this.recognition.onresult = (event) => {
      let partialText = "";
      let finalText = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0]?.transcript?.trim() || "";
        if (!transcript) continue;
        if (event.results[index].isFinal) {
          finalText += transcript;
        } else {
          partialText += transcript;
        }
      }

      if (partialText) handlers.onPartial?.(partialText);
      if (finalText) handlers.onFinal?.(finalText);
    };
    this.recognition.onerror = (event) => {
      handlers.onError?.(new Error(event.error || "语音识别失败"));
    };
    this.recognition.onend = () => {
      this.started = false;
      handlers.onEnd?.();
    };

    try {
      this.started = true;
      this.recognition.start();
    } catch (error) {
      this.started = false;
      if (error?.name !== "InvalidStateError") handlers.onError?.(error);
    }
  }

  stop() {
    if (!this.recognition || !this.started) return;
    this.started = false;
    this.recognition.stop();
  }

  abort() {
    if (!this.recognition) return;
    this.started = false;
    this.recognition.abort();
  }

  _RecognitionCtor() {
    return this.win.SpeechRecognition || this.win.webkitSpeechRecognition;
  }
}

export class BrowserVoiceFeedbackAdapter {
  constructor({ win = window, lang = "zh-CN" } = {}) {
    this.win = win;
    this.lang = lang;
    this.currentResolve = null;
  }

  say(text) {
    const message = String(text || "").trim();
    if (!message || !this.win.speechSynthesis || !this.win.SpeechSynthesisUtterance) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      const utterance = new this.win.SpeechSynthesisUtterance(message);
      this.currentResolve = resolve;
      utterance.lang = this.lang;
      utterance.rate = 1;
      utterance.onend = () => this._finishCurrentSpeech(resolve);
      utterance.onerror = () => this._finishCurrentSpeech(resolve);
      this.win.speechSynthesis.cancel();
      this.win.speechSynthesis.speak(utterance);
    });
  }

  cancel() {
    this.win.speechSynthesis?.cancel();
    this.currentResolve?.();
    this.currentResolve = null;
  }

  async playReadyTone() {
    const AudioContextCtor = this.win.AudioContext || this.win.webkitAudioContext;
    if (!AudioContextCtor) return;

    let audioContext = null;
    try {
      audioContext = new AudioContextCtor();
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }

      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const startAt = audioContext.currentTime;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(880, startAt);
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(0.18, startAt + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.16);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(startAt);
      oscillator.stop(startAt + 0.18);
      await new Promise((resolve) => {
        oscillator.onended = resolve;
      });
    } catch {
      // 提示音失败不应阻断语音会话恢复监听。
    } finally {
      await audioContext?.close?.();
    }
  }

  _finishCurrentSpeech(resolve) {
    if (this.currentResolve === resolve) {
      this.currentResolve = null;
    }
    resolve();
  }
}

export class VoiceSessionController {
  constructor({
    recognition,
    feedback,
    submitTranscript,
    onStatusChange = () => {},
    onListeningChange = () => {},
    onPartialTranscript = () => {},
    onFinalTranscript = () => {},
    restartDelayMs = DEFAULT_RESTART_DELAY_MS
  }) {
    this.recognition = recognition;
    this.feedback = feedback;
    this.submitTranscript = submitTranscript;
    this.onStatusChange = onStatusChange;
    this.onListeningChange = onListeningChange;
    this.onPartialTranscript = onPartialTranscript;
    this.onFinalTranscript = onFinalTranscript;
    this.restartDelayMs = restartDelayMs;
    this.active = false;
    this.listening = false;
    this.processing = false;
    this.speaking = false;
    this.acceptingUserSpeech = false;
    this.currentSpeechText = "";
    this.restartTimer = null;
  }

  isActive() {
    return this.active;
  }

  isListening() {
    return this.listening;
  }

  async start() {
    if (this.active) return;
    if (!this.recognition.isSupported()) {
      this.onStatusChange("当前浏览器不支持持续语音识别，请使用最新版 Chrome 或 Edge");
      return;
    }

    this.active = true;
    this.acceptingUserSpeech = false;
    this.onStatusChange("语音创作模式已开启，请说出你想绘制的内容");
    await this._say("语音创作模式已开启，请说出你想绘制的内容。");
    await this._resumeListeningWithReadyTone();
  }

  async stop({ speak = true } = {}) {
    if (!this.active) return;
    this.active = false;
    this.processing = false;
    this.acceptingUserSpeech = false;
    this.currentSpeechText = "";
    this._clearRestartTimer();
    this.recognition.abort?.();
    this.recognition.stop?.();
    this.feedback.cancel?.();
    this._setListening(false);
    this.onStatusChange("语音创作模式已结束");
    if (speak) await this._say("语音创作模式已结束。");
  }

  async handleFinalTranscript(text) {
    const transcript = String(text || "").trim();
    if (!this.active || !this.acceptingUserSpeech || !transcript || this.processing) return;
    if (isAmbientNoiseTranscript(transcript)) {
      this.onStatusChange("已忽略环境噪声");
      return;
    }

    if (isEndVoiceSessionIntent(transcript)) {
      await this.stop({ speak: true });
      return;
    }

    this.processing = true;
    this.acceptingUserSpeech = false;
    this.recognition.stop?.();
    this._setListening(false);
    this.onFinalTranscript(transcript);
    this.onStatusChange("正在执行语音指令");

    let feedbackText = "已处理";
    try {
      const result = await this.submitTranscript(transcript);
      feedbackText = normalizeFeedbackText(result);
    } catch (error) {
      feedbackText = error?.message || "语音指令执行失败";
    }

    this.processing = false;
    this.onStatusChange(feedbackText);
    await this._say(feedbackText);
    if (this.active && !this.processing && !this.speaking && !this.listening) {
      await this._resumeListeningWithReadyTone();
    }
  }

  _startListening() {
    if (!this.active || this.processing || this.speaking || this.listening) return;
    this.acceptingUserSpeech = true;
    this._setListening(true);
    this.onStatusChange("持续监听中，可以继续说绘图指令");
    this.recognition.start({
      onPartial: (text) => {
        if (!this.acceptingUserSpeech) return;
        this.onPartialTranscript(text);
      },
      onFinal: (text) => {
        this.handleFinalTranscript(text);
      },
      onError: (error) => {
        if (["not-allowed", "service-not-allowed", "audio-capture"].includes(error.message)) {
          void this.stop({ speak: false });
          this.onStatusChange("麦克风或语音服务不可用，请检查权限；也可以直接输入同样的指令。");
          return;
        }
        this.onStatusChange(error.message || "语音识别失败，正在尝试恢复监听");
      },
      onEnd: () => {
        this._setListening(false);
        if (this.active && !this.processing && !this.speaking) {
          this._scheduleRestart();
        }
      }
    });
  }

  _scheduleRestart() {
    this._clearRestartTimer();
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      this._startListening();
    }, this.restartDelayMs);
  }

  _clearRestartTimer() {
    if (!this.restartTimer) return;
    clearTimeout(this.restartTimer);
    this.restartTimer = null;
  }

  async _say(text) {
    this.speaking = true;
    this.currentSpeechText = String(text || "");
    this.acceptingUserSpeech = false;
    try {
      await this.feedback.say(text);
    } finally {
      this.speaking = false;
      this.currentSpeechText = "";
    }
  }

  async _resumeListeningWithReadyTone() {
    if (!this.active || this.processing || this.speaking || this.listening) return;
    this.onStatusChange("提示音后可以继续说绘图指令");
    await this.feedback.playReadyTone?.();
    this._startListening();
  }

  _setListening(value) {
    if (this.listening === value) return;
    this.listening = value;
    this.onListeningChange(value);
  }
}

export function isEndVoiceSessionIntent(text) {
  return ["结束创作", "结束语音创作", "退出语音", "停止创作", "关闭麦克风"].some((keyword) =>
    String(text || "").includes(keyword)
  );
}

export function normalizeFeedbackText(result) {
  if (!result) return "已处理";
  if (typeof result === "string") return result;
  return result.message || result.summary?.message || result.status || "已处理";
}

export function isLikelyFeedbackEcho(transcript, spokenText) {
  const transcriptText = normalizeAnswer(transcript);
  const spoken = normalizeAnswer(spokenText);
  if (isSystemFeedbackPhrase(transcriptText) && spoken.includes(transcriptText)) return true;
  if (transcriptText.length < 7 || spoken.length < 7) return false;
  if (spoken.includes(transcriptText) || transcriptText.includes(spoken)) return true;

  const transcriptChars = [...new Set([...transcriptText])];
  const overlap = transcriptChars.filter((char) => spoken.includes(char)).length;
  return overlap / transcriptChars.length >= 0.82;
}

function isSystemFeedbackPhrase(text) {
  return ["已", "正在", "请", "我还", "语音创作模式"].some((prefix) => text.startsWith(prefix));
}

export function isAmbientNoiseTranscript(text) {
  const normalized = normalizeAnswer(text);
  if (!normalized) return true;
  if (hasCommandKeyword(normalized)) return false;
  if (normalized.length <= 1) return true;
  if (/^[。,.，、!！?？~…]+$/.test(normalized)) return true;
  if (/^(嗯+|啊+|呃+|额+|唉+|喂+|咳+|咳嗽+|哈哈+|呵呵+)$/.test(normalized)) return true;
  if (["背景噪声", "环境噪声", "杂音", "音乐", "说话声", "听不清", "没有声音"].includes(normalized)) {
    return true;
  }
  return normalized.length <= 2 && !/[a-z0-9\u4e00-\u9fa5]/i.test(normalized);
}

function hasCommandKeyword(text) {
  return [
    "创建",
    "画",
    "加",
    "添加",
    "修改",
    "改",
    "放大",
    "缩小",
    "移动",
    "删除",
    "清空",
    "撤销",
    "重做",
    "导出",
    "确认",
    "确定",
    "取消",
    "不清空",
    "结束",
    "继续",
    "左边",
    "右边",
    "第",
  ].some((keyword) => text.includes(keyword));
}

function normalizeAnswer(value) {
  return String(value || "")
    .trim()
    .replaceAll(/\s/g, "")
    .replaceAll("，", "")
    .replaceAll("。", "")
    .toLowerCase();
}
