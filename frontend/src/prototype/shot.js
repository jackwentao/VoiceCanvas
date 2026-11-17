import { ShotClient } from "./shot-client.js";
import { BrowserSpeechRecognitionAdapter, BrowserVoiceFeedbackAdapter, VoiceSessionController } from "./voice-session.js";
import { ShotTextEditor } from "./shot-text-editor.js";
import { StoryboardClient } from "./storyboard-client.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const baseUrl = params.get("apiBaseUrl") || "http://127.0.0.1:8000";
const storageKey = `voicecanvas:last-shot:${baseUrl}`;
const boardStorageKey = `voicecanvas:last-board:${baseUrl}`;
$("homeLink").href = `./index.html?${new URLSearchParams({ apiBaseUrl: baseUrl })}`;
let shownSvg = null;
let previewUrl = null;
let renderedSvg = null;
let renderSerial = 0;
let startedAt = 0;
let generating = false;
let listening = false;
let textEditor;
let boards;
let voice;
let thumbnailUrls = [];
let renderedBoardKey = null;
const recognition = new BrowserSpeechRecognitionAdapter();

function status(message, kind = "") {
  $("status").textContent = message;
  $("statusBox").className = `status-box ${kind}`;
}

function remember(id) {
  const url = new URL(location.href);
  url.searchParams.set("shot", id);
  if (boards?.board) url.searchParams.set("board", boards.board.id);
  history.replaceState(null, "", url);
  try { localStorage.setItem(storageKey, id); } catch { /* 隐私模式仍可用 URL 恢复。 */ }
}

async function showSvg(svg) {
  if (shownSvg === svg) return;
  shownSvg = svg;
  const serial = ++renderSerial;
  if (!svg) {
    $("preview").hidden = true;
    $("emptyFrame").hidden = false;
    $("preview").removeAttribute("src");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    renderedSvg = null;
    return;
  }
  const nextUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const candidate = new Image();
    candidate.src = nextUrl;
    await candidate.decode();
    if (serial !== renderSerial) { URL.revokeObjectURL(nextUrl); return; }
    const oldUrl = previewUrl;
    $("preview").src = nextUrl;
    previewUrl = nextUrl;
    renderedSvg = svg;
    $("preview").hidden = false;
    $("emptyFrame").hidden = true;
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    $("exportPng").disabled = client.busy || renderedSvg !== client.shot?.svg;
  } catch {
    URL.revokeObjectURL(nextUrl);
    shownSvg = null;
    status("画面已保存，但浏览器无法预览。可以导出 SVG 检查。", "error");
  }
}

function update({ shot, busy }) {
  busy = busy || Boolean(boards?.busy);
  textEditor?.setState(shot, busy);
  document.body.classList.toggle("is-busy", busy);
  $("newShot").disabled = busy || !boards?.board;
  $("newBoard").disabled = busy;
  $("voiceMode").disabled = !boards?.board || !recognition.isSupported();
  $("instruction").disabled = busy || !shot;
  $("generate").disabled = busy || !shot;
  $("dictate").disabled = busy || !shot || !recognition.isSupported() || Boolean(voice?.isActive());
  $("undo").disabled = busy || !shot?.canUndo;
  $("redo").disabled = busy || !shot?.canRedo;
  $("exportSvg").disabled = busy || !shot?.svg || Boolean(textEditor?.previewSvg);
  $("exportPng").disabled = busy || !shot?.svg || !previewUrl || renderedSvg !== shot.svg;
  $("saveState").textContent = busy ? "处理中…" : shot ? "已保存到本地服务" : "尚未连接";
  $("generate").replaceChildren(document.createTextNode(busy ? "正在处理…" : "执行指令"));
  $("promptLabel").textContent = "描述画面，或输入分镜指令";
  if (!shot) return;
  remember(shot.id);
  const active = boards?.board?.shots.findIndex(s => s.id === shot.id) ?? -1;
  $("frameTitle").textContent = active >= 0 ? `${active + 1} / ${boards.board.shots.length} · ${boards.board.shots[active].title}` : shot.title;
  $("revisionCount").textContent = `${shot.revisions.length} 个版本`;
  $("versionLabel").textContent = shot.svg ? `版本 ${shot.cursor + 1} / ${shot.revisions.length}` : "空白画面";
  const items = shot.revisions.map((revision, index) => {
    const li = document.createElement("li");
    li.className = index === shot.cursor ? "current" : index > shot.cursor ? "future" : "";
    const label = document.createElement("small");
    label.textContent = `VERSION ${String(index + 1).padStart(2, "0")}${index === shot.cursor ? " · 当前" : ""}`;
    li.append(label, document.createTextNode(revision.instruction));
    return li;
  });
  if (items.length) $("history").replaceChildren(...items);
  else {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = "每一次生成和修改，都会保存在这里。";
    $("history").replaceChildren(empty);
  }
  void showSvg(textEditor?.previewSvg || shot.svg);
}

const client = new ShotClient({ baseUrl, onChange: update });
boards = new StoryboardClient({ shots: client, onChange: renderBoard, exportShot });
textEditor = new ShotTextEditor({
  frame: $("frame"),
  preview: svg => {
    void showSvg(svg);
    $("saveState").textContent = textEditor?.previewSvg ? "文字预览未应用"
      : client.busy ? "处理中…" : "已保存到本地服务";
    $("exportSvg").disabled = client.busy || !client.shot?.svg || Boolean(textEditor?.previewSvg);
    $("exportPng").disabled = client.busy || !client.shot?.svg || Boolean(textEditor?.previewSvg);
  },
  save: layout => action(async () => { await client.editText(layout); await boards.refresh(); }, "正在保存文字…"),
});

function renderBoard() {
  update(client);
  const board = boards.board;
  if (!board) return;
  const busy = boards.busy || client.busy;
  $("boardTitle").textContent = board.title;
  $("shotCount").textContent = `${board.shots.length} 个镜头`;
  $("boardProject").disabled = busy;
  for (const id of ["duplicateShot", "deleteShot", "boardUndo", "boardRedo"]) $(id).disabled = busy;
  $("deleteShot").disabled = busy || board.shots.length <= 1;
  $("boardUndo").disabled = busy || !board.canUndo;
  $("boardRedo").disabled = busy || !board.canRedo;
  $("deleteConfirmation").hidden = !boards.pendingDelete;
  $("deleteQuestion").textContent = boards.pendingDelete?.message || "";
  $("confirmDelete").disabled = busy;
  $("cancelDelete").disabled = busy;
  const key = `${board.id}:${board.version}:${board.shots.map(s => s.version).join(',')}`;
  if (key !== renderedBoardKey) {
    renderedBoardKey = key;
    for (const url of thumbnailUrls) URL.revokeObjectURL(url);
    thumbnailUrls = [];
    $("shotList").replaceChildren(...board.shots.map((shot, index) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-current", String(shot.id === board.activeId));
      button.dataset.shotId = shot.id;
      if (shot.svg) {
        const img = document.createElement("img");
        img.className = "shot-thumbnail";
        img.alt = `${shot.title}缩略图`;
        img.src = URL.createObjectURL(new Blob([shot.svg], { type: "image/svg+xml" }));
        thumbnailUrls.push(img.src);
        button.append(img);
      } else {
        const empty = document.createElement("span");
        empty.className = "shot-thumbnail shot-empty";
        empty.textContent = "待绘制";
        button.append(empty);
      }
      const label = document.createElement("span");
      label.className = "shot-label";
      const number = document.createElement("small");
      number.textContent = `镜头 ${String(index + 1).padStart(2, '0')}`;
      label.append(number, document.createTextNode(shot.title));
      button.append(label);
      button.addEventListener("click", () => boardAction(() => boards.manage({ action: "switch", targetId: shot.id }), "正在切换镜头…"));
      li.append(button);
      return li;
    }));
  }
  for (const button of $("shotList").querySelectorAll("button")) button.disabled = busy;
  const projectOption = [...$("boardProject").options].find(option => option.value === board.id);
  if (!projectOption) {
    const option = document.createElement("option"); option.value = board.id; option.textContent = board.title;
    $("boardProject").prepend(option);
  } else projectOption.textContent = board.title;
  $("boardProject").value = board.id;
  try { localStorage.setItem(boardStorageKey, board.id); } catch { /* URL 可恢复。 */ }
}

async function refreshProjects() {
  const recent = await boards.request();
  $("boardProject").replaceChildren(...recent.map(board => {
    const option = document.createElement("option"); option.value = board.id;
    option.textContent = `${board.title} · ${board.count} 镜头`; return option;
  }));
  if (boards.board) $("boardProject").value = boards.board.id;
}

async function boardAction(fn, message) {
  if (textEditor?.previewSvg) { status("文字预览尚未应用，请先应用或关闭编辑面板。", "error"); return false; }
  const ok = await action(fn, message);
  renderBoard();
  return ok;
}

async function executeInstruction(instruction) {
  const message = await boards.execute(instruction, { allowDrawing: !textEditor?.previewSvg });
  status(message);
  return message;
}

voice = new VoiceSessionController({
  recognition, feedback: new BrowserVoiceFeedbackAdapter(),
  submitTranscript: async text => {
    if (textEditor?.previewSvg) throw new Error("请先应用或关闭文字预览，再执行语音指令");
    startedAt = Date.now(); generating = true;
    try { return await executeInstruction(text); } finally { generating = false; }
  },
  onStatusChange: text => {
    $("speechStatus").textContent = text;
    $("voiceMode").textContent = voice.isActive() ? "结束语音管理" : "开启语音管理";
    $("voiceMode").setAttribute("aria-pressed", String(voice.isActive()));
    $("dictate").disabled = voice.isActive() || client.busy || boards.busy;
  },
  onPartialTranscript: text => { $("speechStatus").textContent = text; },
  onFinalTranscript: text => { $("instruction").value = text; },
});
$("voiceMode").addEventListener("click", async () => {
  if (voice.isActive()) await voice.stop();
  else { recognition.stop(); await voice.start(); }
});

async function action(fn, message) {
  if (!voice?.isActive()) recognition.stop();
  status(message, "busy");
  try {
    await fn();
    status(client.shot?.svg ? "已保存。可以继续描述修改，或导出当前画面。" : "镜头已就绪，描述你想看到的画面。");
    return true;
  } catch (error) {
    const message = error instanceof TypeError ? "连接失败，请检查后端服务。请求可能仍在处理中，可刷新确认后再试。" : error.message;
    status(message, "error");
    return false;
  }
}

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const instruction = $("instruction").value.trim();
  if (!instruction || client.busy || boards.busy) return;
  if (textEditor?.previewSvg) { status("请先应用或关闭文字预览。", "error"); return; }
  startedAt = Date.now();
  generating = true;
  let result;
  const ok = await action(async () => { result = await executeInstruction(instruction); }, "正在执行分镜指令…");
  generating = false;
  if (ok) { $("instruction").value = ""; status(result); }
});
$("instruction").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") $("composer").requestSubmit();
});
$("newShot").addEventListener("click", () => boardAction(async () => {
  await boards.manage({ action: "add" });
  $("instruction").value = "";
}, "正在新建镜头…"));
$("newBoard").addEventListener("click", () => boardAction(async () => { await boards.create(); await refreshProjects(); }, "正在新建分镜项目…"));
$("boardProject").addEventListener("change", event => boardAction(() => boards.load(event.target.value), "正在打开分镜项目…"));
$("duplicateShot").addEventListener("click", () => boardAction(() => boards.manage({ action: "duplicate" }), "正在复制镜头…"));
$("deleteShot").addEventListener("click", () => boardAction(() => executeInstruction("删除当前镜头"), "正在确认目标…"));
$("confirmDelete").addEventListener("click", () => boardAction(() => boards.confirmDelete(), "正在删除镜头…"));
$("cancelDelete").addEventListener("click", () => { boards.cancelDelete(); status("已取消删除"); });
for (const [id, operation] of [["boardUndo", "undo"], ["boardRedo", "redo"]]) {
  $(id).addEventListener("click", () => boardAction(() => boards.manage({ action: operation }), "正在恢复分镜编排…"));
}
for (const operation of ["undo", "redo"]) {
  $(operation).addEventListener("click", () => boardAction(async () => { await client.change(operation); await boards.refresh(); }, "正在恢复画面…"));
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("exportSvg").addEventListener("click", () => {
  void exportShot("svg").catch(error => status(error.message, "error"));
});
async function exportShot(format) {
    if (!client.shot?.svg || textEditor?.previewSvg) throw new Error("请先保存画面，再导出当前镜头");
    if (format === "svg") {
      download(new Blob([client.shot.svg], { type: "image/svg+xml" }), `${client.shot.id}.svg`);
      return;
    }
    const image = $("preview");
    await image.decode();
    if (renderedSvg !== client.shot.svg) throw new Error("当前画面仍在加载，请稍后导出");
    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    canvas.getContext("2d").drawImage(image, 0, 0, 1280, 720);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("PNG 导出失败，请尝试导出 SVG");
    download(blob, `${client.shot.id}.png`);
}
$("exportPng").addEventListener("click", () => { void exportShot("png").catch(error => status(error.message, "error")); });

$("dictate").addEventListener("click", () => {
  if (listening) { recognition.stop(); return; }
  listening = true;
  $("dictate").textContent = "■ 停止录音";
  $("speechStatus").textContent = "正在听… 识别后请检查文字，再点击执行指令。";
  recognition.start({
    onPartial: (text) => { $("speechStatus").textContent = text; },
    onFinal: (text) => { $("instruction").value += `${$("instruction").value ? " " : ""}${text}`.slice(0, Math.max(0, 4000 - $("instruction").value.length)); },
    onError: () => { $("speechStatus").textContent = "语音暂不可用，请检查麦克风权限或直接输入文字。"; recognition.stop(); },
    onEnd: () => { listening = false; $("dictate").textContent = "○ 语音输入"; },
  });
});
if (!recognition.isSupported()) $("speechStatus").textContent = "此浏览器不支持语音识别，可以直接输入文字。";

setInterval(() => {
  if (generating && client.busy) status(`Agent 正在绘制 · 已等待 ${Math.floor((Date.now() - startedAt) / 1000)} 秒。完成后自动显示。`, "busy");
}, 1000);
window.addEventListener("pagehide", () => { void voice.stop({ speak: false }); recognition.abort(); if (previewUrl) URL.revokeObjectURL(previewUrl); for (const url of thumbnailUrls) URL.revokeObjectURL(url); });

let lastId = params.get("shot");
let boardId = params.get("board");
if (!boardId && !lastId) { try { boardId = localStorage.getItem(boardStorageKey); } catch { /* URL 可恢复。 */ } }
if (!boardId && !lastId) { try { lastId = localStorage.getItem(storageKey); } catch { /* URL 可恢复。 */ } }
await action(async () => { if (boardId) await boards.load(boardId); else await boards.create(lastId || undefined); await refreshProjects(); }, "正在打开分镜项目…");
if (!client.shot) $("newBoard").disabled = false;
