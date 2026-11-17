import { ShotClient } from "./shot-client.js";
import { BrowserSpeechRecognitionAdapter } from "./voice-session.js";
import { ShotTextEditor } from "./shot-text-editor.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const baseUrl = params.get("apiBaseUrl") || "http://127.0.0.1:8000";
const storageKey = `voicecanvas:last-shot:${baseUrl}`;
$("homeLink").href = `./index.html?${new URLSearchParams({ apiBaseUrl: baseUrl })}`;
let shownSvg = null;
let previewUrl = null;
let renderedSvg = null;
let renderSerial = 0;
let startedAt = 0;
let generating = false;
let listening = false;
let textEditor;
const recognition = new BrowserSpeechRecognitionAdapter();

function status(message, kind = "") {
  $("status").textContent = message;
  $("statusBox").className = `status-box ${kind}`;
}

function remember(id) {
  const url = new URL(location.href);
  url.searchParams.set("shot", id);
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
  textEditor?.setState(shot, busy);
  document.body.classList.toggle("is-busy", busy);
  $("newShot").disabled = busy;
  $("instruction").disabled = busy || !shot;
  $("generate").disabled = busy || !shot;
  $("dictate").disabled = busy || !shot || !recognition.isSupported();
  $("undo").disabled = busy || !shot?.canUndo;
  $("redo").disabled = busy || !shot?.canRedo;
  $("exportSvg").disabled = busy || !shot?.svg || Boolean(textEditor?.previewSvg);
  $("exportPng").disabled = busy || !shot?.svg || !previewUrl || renderedSvg !== shot.svg;
  $("saveState").textContent = busy ? "处理中…" : shot ? "已保存到本地服务" : "尚未连接";
  $("generate").replaceChildren(document.createTextNode(busy ? "正在处理…" : shot?.svg ? "修改这个镜头" : "生成这个镜头"));
  $("promptLabel").textContent = shot?.svg ? "这次想调整什么？" : "你想看到什么画面？";
  if (!shot) return;
  remember(shot.id);
  $("frameTitle").textContent = shot.revisions[0]?.instruction.slice(0, 32) || shot.title;
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
textEditor = new ShotTextEditor({
  frame: $("frame"),
  preview: svg => {
    void showSvg(svg);
    $("saveState").textContent = textEditor?.previewSvg ? "文字预览未应用"
      : client.busy ? "处理中…" : "已保存到本地服务";
    $("exportSvg").disabled = client.busy || !client.shot?.svg || Boolean(textEditor?.previewSvg);
    $("exportPng").disabled = client.busy || !client.shot?.svg || Boolean(textEditor?.previewSvg);
  },
  save: layout => action(() => client.editText(layout), "正在保存文字…"),
});

async function action(fn, message) {
  recognition.stop();
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
  if (!instruction || client.busy) return;
  startedAt = Date.now();
  generating = true;
  const ok = await action(() => client.change("generate", instruction), "Agent 正在绘制，通常需要 1–3 分钟…");
  generating = false;
  if (ok) $("instruction").value = "";
});
$("instruction").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") $("composer").requestSubmit();
});
$("newShot").addEventListener("click", () => action(async () => {
  await client.create();
  $("instruction").value = "";
}, "正在新建镜头…"));
for (const operation of ["undo", "redo"]) {
  $(operation).addEventListener("click", () => action(() => client.change(operation), "正在恢复画面…"));
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
  download(new Blob([client.shot.svg], { type: "image/svg+xml" }), `${client.shot.id}.svg`);
});
$("exportPng").addEventListener("click", async () => {
  try {
    const image = $("preview");
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    canvas.getContext("2d").drawImage(image, 0, 0, 1280, 720);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("PNG 导出失败，请尝试导出 SVG");
    download(blob, `${client.shot.id}.png`);
  } catch (error) { status(error.message, "error"); }
});

$("dictate").addEventListener("click", () => {
  if (listening) { recognition.stop(); return; }
  listening = true;
  $("dictate").textContent = "■ 停止录音";
  $("speechStatus").textContent = "正在听… 识别后请检查文字，再点击生成。";
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
window.addEventListener("pagehide", () => { recognition.abort(); if (previewUrl) URL.revokeObjectURL(previewUrl); });

let lastId = params.get("shot");
if (!lastId) { try { lastId = localStorage.getItem(storageKey); } catch { /* URL 可单独恢复。 */ } }
await action(() => lastId ? client.load(lastId) : client.create(), "正在打开镜头…");
if (!client.shot) $("newShot").disabled = false;
