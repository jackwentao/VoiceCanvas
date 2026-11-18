import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  isAmbientNoiseTranscript,
  isLikelyFeedbackEcho,
  VoiceSessionController
} from "../../src/prototype/voice-session.js";

async function testPrototypeHtml() {
  const root = new URL("../../src/prototype/", import.meta.url);
  const html = await readFile(new URL("workspace.html", root), "utf-8");
  const home = await readFile(new URL("index.html", root), "utf-8");
  const app = await readFile(new URL("svg-workspace.js", root), "utf-8");
  const css = await readFile(new URL("workspace.css", root), "utf-8");
  for (const id of ["voiceButton", "voiceInput", "canvasSurface", "sceneList", "undoButton",
    "redoButton", "clarificationCard", "exportButton", "textEditor", "retryButton"]) {
    assert.ok(html.includes(`id="${id}"`), `工作台缺少入口 ${id}`);
  }
  assert.ok(html.includes('src="./svg-workspace.js"'));
  for (const removed of ["memoryDialog", "memoryButton", "importButton", "backgroundColorInput", "workspace-entry.js"]) {
    assert.ok(!html.includes(removed), `工作台不应保留旧入口 ${removed}`);
  }
  assert.ok(app.includes("new StoryboardClient"));
  assert.match(home, /用三个镜头讲一场雨和一杯咖啡/);
  assert.match(html, /data-prompt="给咖啡店[^"]*景别和时长/);
  assert.match(html, /data-prompt="画一个雨夜便利店/);
  assert.ok(!app.includes('params.get("shot")'));
  assert.ok(!app.includes('import("./app.js")'));
  assert.ok(css.includes("prefers-reduced-motion"));
  assert.ok(css.includes("max-width:680px"));
}

class MockRecognition {
  constructor() {
    this.handlers = null;
    this.started = false;
    this.stopCount = 0;
  }

  isSupported() {
    return true;
  }

  start(handlers) {
    this.handlers = handlers;
    this.started = true;
  }

  stop() {
    this.stopCount += 1;
    this.started = false;
  }

  abort() {
    this.started = false;
  }

  emitFinal(text) {
    this.handlers.onFinal(text);
  }

  emitPartial(text) {
    this.handlers.onPartial(text);
  }
}

class MockFeedback {
  constructor() {
    this.messages = [];
    this.cancelCount = 0;
    this.readyToneCount = 0;
    this.pendingResolve = null;
    this.holdNext = false;
  }

  async say(text) {
    this.messages.push(text);
    if (!this.holdNext) return;
    this.holdNext = false;
    await new Promise((resolve) => {
      this.pendingResolve = resolve;
    });
  }

  cancel() {
    this.cancelCount += 1;
    this.pendingResolve?.();
    this.pendingResolve = null;
  }

  async playReadyTone() {
    this.readyToneCount += 1;
  }

  release() {
    this.pendingResolve?.();
    this.pendingResolve = null;
  }
}

async function testVoiceSessionController() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const statuses = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: "已创建三个分镜" };
    },
    onStatusChange: (message) => statuses.push(message)
  });

  await controller.start();
  assert.equal(controller.isActive(), true);
  assert.equal(recognition.started, true);
  assert.equal(feedback.messages[0], "语音创作模式已开启，请说出你想绘制的内容。");
  assert.equal(feedback.readyToneCount, 1);

  await controller.handleFinalTranscript("创建一个三镜头雨夜便利店分镜");
  assert.deepEqual(submitted, ["创建一个三镜头雨夜便利店分镜"]);
  assert.ok(feedback.messages.includes("已创建三个分镜"));
  assert.equal(feedback.readyToneCount, 2);
  assert.equal(controller.isListening(), true);

  await controller.handleFinalTranscript("结束创作");
  assert.equal(controller.isActive(), false);
  assert.ok(statuses.includes("语音创作模式已结束"));
}

async function testVoiceSessionDoesNotListenDuringFeedback() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: text.includes("创建") ? "已创建三个分镜，请继续修改。" : "已撤销上一步。" };
    }
  });

  await controller.start();
  feedback.holdNext = true;
  const firstTurn = controller.handleFinalTranscript("创建一个三镜头雨夜便利店分镜");
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(controller.isListening(), false, "系统播报期间必须关闭语音监听");
  assert.equal(recognition.started, false, "系统播报期间 recognition 不应保持 started");
  assert.deepEqual(submitted, ["创建一个三镜头雨夜便利店分镜"]);

  feedback.release();
  await firstTurn;
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(feedback.readyToneCount, 2, "播报结束后必须播放可说话提示音");
  assert.equal(controller.isListening(), true, "提示音后必须恢复监听");

  await controller.handleFinalTranscript("撤销上一步");
  assert.deepEqual(submitted, ["创建一个三镜头雨夜便利店分镜", "撤销上一步"]);
  assert.equal(feedback.cancelCount, 0, "播报期间不再通过打断监听取消系统播报");
}

async function testVoiceSessionDropsAmbientNoise() {
  const recognition = new MockRecognition();
  const feedback = new MockFeedback();
  const submitted = [];
  const statuses = [];
  const controller = new VoiceSessionController({
    recognition,
    feedback,
    restartDelayMs: 1,
    submitTranscript: async (text) => {
      submitted.push(text);
      return { message: "已处理" };
    },
    onStatusChange: (message) => statuses.push(message)
  });

  await controller.start();
  await controller.handleFinalTranscript("嗯");
  await controller.handleFinalTranscript("环境噪声");
  await controller.handleFinalTranscript("撤销上一步");

  assert.deepEqual(submitted, ["撤销上一步"]);
  assert.ok(statuses.includes("已忽略环境噪声"));
}

function testAmbientNoiseDetection() {
  assert.equal(isAmbientNoiseTranscript("嗯"), true);
  assert.equal(isAmbientNoiseTranscript("咳嗽"), true);
  assert.equal(isAmbientNoiseTranscript("环境噪声"), true);
  assert.equal(isAmbientNoiseTranscript("确认"), false);
  assert.equal(isAmbientNoiseTranscript("取消"), false);
  assert.equal(isAmbientNoiseTranscript("清空当前画布"), false);
  assert.equal(isAmbientNoiseTranscript("撤销"), false);
}

function testFeedbackEchoDetection() {
  assert.equal(isLikelyFeedbackEcho("已创建三个分镜请继续修改", "已创建三个分镜，请继续修改。"), true);
  assert.equal(isLikelyFeedbackEcho("已导出图片", "已导出图片。"), true);
  assert.equal(isLikelyFeedbackEcho("导出图片", "已导出图片。"), false);
  assert.equal(isLikelyFeedbackEcho("撤销", "已创建三个分镜，请继续修改。"), false);
}

await testVoiceSessionController();
await testVoiceSessionDoesNotListenDuringFeedback();
await testVoiceSessionDropsAmbientNoise();
testAmbientNoiseDetection();
testFeedbackEchoDetection();
await testPrototypeHtml();
console.log("分镜工作台与语音测试通过");
