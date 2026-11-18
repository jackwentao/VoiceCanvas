import { ShotClient } from "./shot-client.js";
import { StoryboardClient } from "./storyboard-client.js";
import { ShotTextEditor } from "./shot-text-editor.js";
import { BrowserSpeechRecognitionAdapter, BrowserVoiceFeedbackAdapter, VoiceSessionController } from "./voice-session.js";
import { renderWorkspaceIcons } from "./workspace-icons.js";
import { pageUrl } from "./home-controller.js";
import { visualFeedback } from "./shot-visual-feedback.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const baseUrl = (window.VOICECANVAS_API_BASE_URL || params.get("apiBaseUrl") || "http://127.0.0.1:8000").replace(/\/+$/, "");
const storageKey = `voicecanvas:last-board:${baseUrl}`;
document.body.classList.add("svg-workspace");
document.querySelector(".brand").href = pageUrl("index.html", location.search);
renderWorkspaceIcons();
$("exportMenu").replaceChildren(...[ ["png", "当前镜头 · PNG"], ["svg", "当前镜头 · SVG"] ].map(([format, text]) => {
  const button = document.createElement("button"); button.dataset.export = format; button.textContent = text; return button;
}));
$("voiceInput").maxLength = 8000;
$("voiceInput").placeholder = "描述完整故事、需要几个镜头，或直接说要修改哪里…";
$("selectionLabel").textContent = "自由绘制 · 可继续改画或编辑文字";

let boards, textEditor, voice;
let working = false;
let lastInput = "";
let renderedBoardId;
const inputDrafts = new Map();
let message = "连接后即可开始创作";
let failure = "";
let missingBoardId;
let assistantOpen = innerWidth > 980;
let dialogMode = "new";
let previewSvg = null;
let previewUrl = null;
let previewSerial = 0;
let thumbnails = [];
let listKey = "";
let feedbackKey = "";
let toastTimer;
let actionStarted = 0;
let progressTimer;
const recognition = new BrowserSpeechRecognitionAdapter();
const shots = new ShotClient({ baseUrl, onChange: () => render() });
boards = new StoryboardClient({ shots, onChange: () => render(), exportShot });
textEditor = new ShotTextEditor({ frame: $("canvasStage"),
  preview: svg => {
    void showSvg(svg);
    $("exportButton").disabled = isBusy() || !shots.shot?.svg || Boolean(textEditor?.hasDraft);
    $("selectionLabel").textContent = textEditor?.hasDraft ? "改字草稿未保存" : "自由绘制 · 可继续改画或编辑文字";
  },
  save: layout => act(async () => { await shots.editText(layout); await boards.refresh(); return "文字已保存，可以撤销或继续修改。"; }, { guard: false }).catch(showError),
});
voice = new VoiceSessionController({ recognition, feedback: new BrowserVoiceFeedbackAdapter(),
  submitTranscript: text => submit(text),
  onStatusChange: text => { $("voiceStatus").textContent = text; renderVoice(); },
  onListeningChange: () => renderVoice(),
  onPartialTranscript: text => { $("voiceInput").value = text; resizeInput(); },
  onFinalTranscript: text => { $("voiceInput").value = text; resizeInput(); },
});

function isBusy() { return working || shots.busy || boards.busy; }
function renderStatus() {
  const elapsed = Math.floor((Date.now() - actionStarted) / 1000);
  const run = boards?.agent;
  const active = run?.steps.filter(s => s.status === "running") || [];
  const labels = { draw_shot: "绘制镜头", create_shots: "建立分镜", set_context: "保存角色设定", describe_shot: "整理拍摄说明", finish_task: "核对交付", manage_storyboard: "调整分镜", get_storyboard: "读取分镜", inspect_shot: "检查画面源码", render_shot: "渲染真实预览", review_shot: "看图检查", delete_shot: "处理删除确认", export_shots: "准备导出" };
  const progress = active.map(s => {
    const target = boards.board?.shots.find(p => p.id === s.call.arguments.shotId);
    return `${labels[s.call.name] || "执行操作"}${target ? `：${target.title}` : ""}`;
  }).join("；");
  const status = failure || (run?.status === "running" ? `${progress || run.summary} · 已等待 ${elapsed} 秒，逐镜保存` : isBusy() && shots.busy ? `正在绘制画面 · 已等待 ${elapsed} 秒，完成后自动保存` : message);
  if (!voice?.isActive() || failure || shots.busy || run?.status === "running") $("voiceStatus").textContent = status.length > 120 ? `${status.slice(0, 120)}… 展开创作助手查看结果` : status;
  $("resultMessage").textContent = status;
}
function renderVoice() {
  if (!voice) return;
  $("voiceButton").setAttribute("aria-pressed", String(voice.isActive()));
  $("voiceButton").setAttribute("aria-label", voice.isActive() ? "结束语音创作" : "开始语音创作");
  $("voiceButton").disabled = !voice.isActive() && (!boards.board || isBusy() || !recognition.isSupported());
  $("composerContext").dataset.listening = String(voice.isListening());
}
function remember() {
  const url = new URL(location.href);
  url.searchParams.delete("shot"); url.searchParams.delete("projectId");
  url.searchParams.set("board", boards.board.id);
  history.replaceState(null, "", url);
  try { localStorage.setItem(storageKey, boards.board.id); } catch { /* URL 仍可恢复。 */ }
}
async function showSvg(svg) {
  if (svg === previewSvg) return;
  previewSvg = svg;
  const serial = ++previewSerial;
  if (!svg) {
    $("canvasSurface").replaceChildren(); $("emptyCanvas").hidden = false;
    if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null;
    return;
  }
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  const image = new Image(); image.alt = "当前镜头画面"; image.src = url;
  try {
    await image.decode();
    if (serial !== previewSerial) { URL.revokeObjectURL(url); return; }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = url; $("canvasSurface").replaceChildren(image); $("emptyCanvas").hidden = true;
  } catch { URL.revokeObjectURL(url); previewSvg = null; showError("画面已保存但预览失败，可以导出 SVG 检查。"); }
}
function render() {
  if (!boards) return;
  const board = boards.board, shot = shots.shot, busy = isBusy();
  if (board && board.id !== renderedBoardId) {
    if (renderedBoardId) {
      inputDrafts.set(renderedBoardId, $("voiceInput").value);
      $("voiceInput").value = inputDrafts.get(board.id) || "";
      resizeInput();
    }
    renderedBoardId = board.id;
    lastInput = "";
  }
  textEditor?.setState(shot, busy);
  document.querySelectorAll("[data-requires-project]").forEach(node => { node.disabled = !board || busy; });
  for (const id of ["newButton", "addSvgScene", "copySvgScene", "deleteSvgScene", "renameSvgScene", "moveSvgSceneUp", "moveSvgSceneDown", "retryButton"]) $(id).disabled = busy || (id !== "newButton" && id !== "retryButton" && !board);
  $("deleteSvgScene").disabled = busy || !board || board.shots.length <= 1;
  $("undoStructure").disabled = busy || !board?.canUndo;
  $("redoStructure").disabled = busy || !board?.canRedo;
  $("undoButton").disabled = busy || !shot?.canUndo;
  $("redoButton").disabled = busy || !shot?.canRedo;
  $("undoResult").hidden = busy || !shot?.canUndo;
  $("exportButton").disabled = busy || !shot?.svg || Boolean(textEditor?.hasDraft);
  $("saveStatus").replaceChildren(document.createTextNode(failure ? "连接待确认" : busy ? "处理中…" : board ? "已同步" : "等待连接"));
  $("saveStatus").dataset.busy = String(busy);
  $("errorBanner").hidden = !failure; $("errorText").textContent = failure;
  $("retryButton").textContent = missingBoardId ? "打开可用项目" : "重新连接";
  const naming = $("nameDialog").open && busy;
  $("nameInput").disabled = naming;
  $("nameSubmit").disabled = naming;
  $("nameSubmit").textContent = naming ? "正在保存…" : "确认";
  $("assistantConnection").textContent = busy ? "正在协助创作" : board ? "准备好和你一起创作" : "等待连接";
  $("backendStatus").textContent = busy ? "正在执行，完成后自动保存" : "每次修改，自动保存";
  $("composerContext").dataset.busy = String(busy);
  renderStatus();
  $("sendButton").setAttribute("aria-label", busy ? "正在执行指令" : "发送指令");
  $("turnCard").hidden = !lastInput && !boards.agent;
  $("assistantPanel").dataset.active = String(Boolean(lastInput || boards.pendingDelete));
  $("lastInput").textContent = lastInput || boards.agent?.request || "";
  $("resultHeading").textContent = busy ? "正在完成你的指令" : failure ? "这次需要再试一下" : boards.agent?.status === "needs_input" ? "等待验收或确认" : "已完成";
  const feedback = visualFeedback(board, boards.agent);
  const nextFeedbackKey = JSON.stringify(feedback);
  if (nextFeedbackKey !== feedbackKey) {
    feedbackKey = nextFeedbackKey;
    $("visualFeedback").replaceChildren(...feedback.map(item => {
      const section = document.createElement("details"); section.className = "visual-review";
      const title = document.createElement("summary");
      title.textContent = `${item.title} · 版本 ${item.version} · ${item.current ? "当前画面" : "历史评审，画面已变化"}`;
      const text = document.createElement("p"); text.textContent = item.review;
      section.append(title);
      if (item.previewUrl) {
        const image = new Image(); image.alt = `${item.title}的真实渲染预览`; image.loading = "lazy";
        image.src = `${baseUrl}${item.previewUrl}`; section.append(image);
      }
      section.append(text); return section;
    }));
    $("visualFeedback").hidden = !feedback.length;
  }
  $("clarificationCard").hidden = !boards.pendingDelete;
  if (boards.pendingDelete) assistantOpen = true;
  if (boards.pendingDelete) $("clarificationQuestion").textContent = boards.pendingDelete.message;
  document.querySelectorAll("[data-delete-answer]").forEach(button => { button.disabled = busy; });
  document.querySelector(".workspace").classList.toggle("assistant-hidden", !assistantOpen);
  $("toggleAssistant").setAttribute("aria-expanded", String(assistantOpen));
  renderVoice();
  if (!board || !shot) return;
  remember();
  $("renameButton").textContent = board.title;
  $("sceneCount").textContent = board.shots.length;
  const index = board.shots.findIndex(s => s.id === board.activeId);
  $("sceneName").textContent = board.shots[index].title;
  $("sceneEyebrow").textContent = `SCENE ${String(index + 1).padStart(2, "0")}`;
  $("sceneDescription").textContent = `${index + 1} / ${board.shots.length} · ${board.shots[index].title}`;
  $("canvasSize").textContent = "1280 × 720";
  const detail = board.shots[index];
  $("shotBrief").hidden = !detail.description;
  $("shotBriefText").textContent = [detail.durationSeconds ? `${detail.durationSeconds} 秒` : "", detail.camera, detail.description].filter(Boolean).join(" · ");
  $("narrationText").textContent = [detail.durationSeconds ? `${detail.durationSeconds} 秒` : "", detail.camera, detail.description, shot.svg ? `画面版本 ${shot.cursor + 1} / ${shot.revisions.length}` : "等待绘制"].filter(Boolean).join(" · ");
  $("narrationText").title = $("narrationText").textContent;
  $("moveSvgSceneUp").disabled = busy || index === 0;
  $("moveSvgSceneDown").disabled = busy || index === board.shots.length - 1;
  document.querySelectorAll("[data-prompt]").forEach(button => { button.disabled = busy; });
  const key = `${board.id}:${board.version}:${board.shots.map(s => s.version).join(',')}`;
  if (key !== listKey) {
    listKey = key;
    thumbnails.forEach(url => URL.revokeObjectURL(url)); thumbnails = [];
    $("sceneList").replaceChildren(...board.shots.map((s, i) => {
      const button = document.createElement("button"); button.className = "scene-button"; button.dataset.scene = s.id;
      button.setAttribute("aria-current", String(s.id === board.activeId)); button.setAttribute("aria-label", `镜头 ${i + 1}：${s.title}`);
      const thumb = document.createElement("div"); thumb.className = "scene-thumbnail";
      if (s.svg) { const img = new Image(); img.alt = `${s.title}缩略图`; img.src = URL.createObjectURL(new Blob([s.svg], { type: "image/svg+xml" })); thumbnails.push(img.src); thumb.append(img); }
      const label = document.createElement("div"); label.className = "scene-label";
      const title = document.createElement("strong"); title.textContent = `${String(i + 1).padStart(2, "0")} · ${s.title}`;
      const info = document.createElement("span"); info.textContent = `${s.durationSeconds ? `${s.durationSeconds} 秒 · ` : ""}${s.svg ? "已绘制" : "待绘制"}`;
      label.append(title, info); button.append(thumb, label); return button;
    }));
    $("historyCount").textContent = shot.revisions.length;
    $("historyList").replaceChildren(...[...shot.revisions].reverse().map(r => { const li = document.createElement("li"); li.textContent = r.instruction; return li; }));
    let option = [...$("projectSelect").options].find(o => o.value === board.id);
    if (!option) { option = document.createElement("option"); option.value = board.id; $("projectSelect").prepend(option); }
    option.textContent = board.title;
  }
  $("projectSelect").value = board.id;
  $("sceneList").querySelectorAll("button").forEach(button => { button.disabled = busy; });
  void showSvg(textEditor?.previewSvg || shot.svg);
  fitCanvas();
}
function fitCanvas() {
  const maxHeight = Math.max(160, $("canvasViewport").clientHeight - 125);
  $("canvasStage").style.maxWidth = innerWidth > 640 ? `${Math.min(1200, maxHeight * 16 / 9)}px` : "100%";
}
function errorMessage(error) { return error instanceof TypeError ? "连接失败，请检查服务并刷新确认结果后再试。" : error?.message || String(error); }
function showError(error) { failure = errorMessage(error); render(); }
function toast(text) { $("toast").textContent = text; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500); }
async function act(fn, { guard = true, inlineError = false } = {}) {
  if (isBusy()) throw new Error("正在完成上一条指令，请稍候");
  if (guard && textEditor?.hasDraft) throw new Error("请先应用改字或舍弃草稿，再切换镜头或执行指令。");
  working = true; failure = ""; message = "正在完成指令，请稍候…";
  actionStarted = Date.now(); progressTimer = setInterval(renderStatus, 1000); render();
  try { const result = await fn(); message = typeof result === "string" ? result : "已保存，可以继续创作。"; return message; }
  catch (error) {
    if (!inlineError) failure = errorMessage(error);
    message = "本次操作未完成。";
    throw error;
  }
  finally { clearInterval(progressTimer); working = false; render(); }
}
// 按钮吞掉已展示的错误；语音路径保留异常供语音反馈播报。
const clickAction = fn => { void fn().catch(showError); };
async function refreshProjects() {
  let recent;
  try { recent = await boards.request(); }
  catch { toast("最近项目列表暂时无法更新。"); return; }
  $("projectSelect").replaceChildren(...recent.map(b => { const option = document.createElement("option"); option.value = b.id; option.textContent = b.title; return option; }));
  if (boards.board) { listKey = ""; render(); }
}
async function submit(text) {
  text = String(text || "").trim(); if (!text) return "请描述画面或分镜指令。";
  return act(async () => {
    lastInput = text;
    const reply = await boards.execute(text);
    $("voiceInput").value = ""; resizeInput();
    await refreshProjects();
    return reply;
  });
}
function resizeInput() { $("voiceInput").style.height = "auto"; $("voiceInput").style.height = `${Math.min($("voiceInput").scrollHeight, 120)}px`; }
function openName(mode) {
  dialogMode = mode; $("nameDialogTitle").textContent = mode === "new" ? "新建分镜项目" : mode === "scene" ? "重命名镜头" : "重命名项目";
  $("nameInput").value = mode === "new" ? "" : mode === "scene" ? boards.board.shots.find(s => s.id === boards.board.activeId).title : boards.board.title;
  $("nameError").hidden = true;
  $("nameDialog").showModal(); $("nameInput").focus();
}
async function saveName(title) {
  $("nameError").hidden = true;
  try {
    await act(async () => {
      if (dialogMode === "new") {
        await boards.create(title);
        missingBoardId = undefined;
      } else {
        await boards.manage({ action: dialogMode === "scene" ? "rename" : "rename_project", title });
      }
      await refreshProjects();
    }, { inlineError: true });
    $("nameDialog").close();
  } catch (error) {
    $("nameError").textContent = errorMessage(error);
    $("nameError").hidden = false;
  }
}
function download(blob, extension, shotId) {
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = `${shotId}.${extension}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function exportShot(format, shotId = shots.shot?.id) {
  const target = boards.board?.shots.find(s => s.id === shotId);
  if (!target?.svg || textEditor.hasDraft) throw new Error("请先保存画面，再导出镜头。");
  if (format === "svg") { download(new Blob([target.svg], { type: "image/svg+xml" }), "svg", shotId); return; }
  const img = new Image(), url = URL.createObjectURL(new Blob([target.svg], { type: "image/svg+xml" }));
  try {
    img.src = url; await img.decode(); const canvas = document.createElement("canvas"); canvas.width = 1280; canvas.height = 720;
    canvas.getContext("2d").drawImage(img, 0, 0, 1280, 720);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("PNG 导出失败，请尝试 SVG。"); download(blob, "png", shotId);
  } finally { URL.revokeObjectURL(url); }
}

$("composerForm").addEventListener("submit", event => { event.preventDefault(); clickAction(() => submit($("voiceInput").value)); });
$("voiceInput").addEventListener("input", resizeInput);
$("voiceInput").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("composerForm").requestSubmit(); } });
$("voiceButton").addEventListener("click", () => clickAction(() => voice.isActive() ? voice.stop() : voice.start()));
$("sceneList").addEventListener("click", event => { const button = event.target.closest("[data-scene]"); if (button) clickAction(() => act(() => boards.manage({ action: "switch", targetId: button.dataset.scene }))); });
$("projectSelect").addEventListener("change", event => {
  const boardId = event.target.value;
  clickAction(() => act(async () => {
    await boards.load(boardId);
    return boards.agent?.summary || "已切换项目。";
  }));
});
for (const [id, action] of [["addSvgScene", "add"], ["copySvgScene", "duplicate"], ["undoStructure", "undo"], ["redoStructure", "redo"]]) $(id).addEventListener("click", () => clickAction(() => act(() => boards.manage({ action }))));
$("deleteSvgScene").addEventListener("click", () => clickAction(() => act(async () => {
  const { activeId, shots: members } = boards.board;
  const target = members.find(member => member.id === activeId);
  if (!window.confirm(`删除镜头「${target.title}」？可通过“撤销分镜”恢复。`)) return "已取消删除。";
  await boards.manage({ action: "delete", targetId: activeId, confirmed: true });
  return `已删除镜头「${target.title}」。`;
})));
for (const [id, direction] of [["moveSvgSceneUp", -1], ["moveSvgSceneDown", 1]]) $(id).addEventListener("click", () => clickAction(() => act(() => boards.manage({ action: "move", position: boards.board.shots.findIndex(s => s.id === boards.board.activeId) + 1 + direction }))));
for (const [id, action] of [["undoButton", "undo"], ["redoButton", "redo"], ["undoResult", "undo"]]) $(id).addEventListener("click", () => clickAction(() => act(async () => { await shots.change(action); await boards.refresh(); })));
$("clarificationOptions").replaceChildren(...[ ["确认删除", "确认删除"], ["取消", "取消"] ].map(([answer, text]) => { const button = document.createElement("button"); button.textContent = text; button.dataset.deleteAnswer = answer; button.addEventListener("click", () => clickAction(() => submit(answer))); return button; }));
$("newButton").addEventListener("click", () => openName("new")); $("renameButton").addEventListener("click", () => openName("board")); $("renameSvgScene").addEventListener("click", () => openName("scene"));
$("nameForm").addEventListener("submit", event => {
  event.preventDefault();
  const title = $("nameInput").value.trim();
  if (title && !isBusy()) void saveName(title);
});
$("nameDialog").addEventListener("cancel", event => { if (isBusy()) event.preventDefault(); });
document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => {
  if (!isBusy()) button.closest("dialog").close();
}));
$("exportButton").addEventListener("click", () => { $("exportMenu").hidden = !$("exportMenu").hidden; $("exportButton").setAttribute("aria-expanded", String(!$("exportMenu").hidden)); });
$("exportMenu").addEventListener("click", event => { const button = event.target.closest("[data-export]"); if (button) clickAction(async () => { await exportShot(button.dataset.export); $("exportMenu").hidden = true; $("exportButton").setAttribute("aria-expanded", "false"); toast("已导出当前镜头"); }); });
document.addEventListener("click", event => { if (!event.target.closest(".export-wrap")) { $("exportMenu").hidden = true; $("exportButton").setAttribute("aria-expanded", "false"); } });
$("toggleAssistant").addEventListener("click", () => { assistantOpen = !assistantOpen; render(); });
$("dismissError").addEventListener("click", () => { failure = ""; render(); });
$("fitButton").addEventListener("click", fitCanvas);
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => { $("voiceInput").value = button.dataset.prompt; resizeInput(); $("voiceInput").focus(); }));
document.addEventListener("keydown", event => {
  if (event.altKey && event.key.toLowerCase() === "v") { event.preventDefault(); if (!$("voiceButton").disabled) $("voiceButton").click(); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.target.closest("input,textarea,select,[contenteditable]")) { event.preventDefault(); $(event.shiftKey ? "redoButton" : "undoButton").click(); }
});
new ResizeObserver(fitCanvas).observe($("canvasViewport"));
let compact = innerWidth <= 980;
window.addEventListener("resize", () => {
  const next = innerWidth <= 980;
  if (next && !compact) { assistantOpen = false; render(); }
  compact = next; fitCanvas();
});
window.addEventListener("pagehide", () => { void voice.stop({ speak: false }); recognition.abort(); if (previewUrl) URL.revokeObjectURL(previewUrl); thumbnails.forEach(url => URL.revokeObjectURL(url)); });

async function connect() {
  await act(async () => {
    let id = new URLSearchParams(location.search).get("board");
    if (!id) { try { id = localStorage.getItem(storageKey); } catch { /* URL 可恢复。 */ } }
    if (missingBoardId) {
      const recent = await boards.request();
      id = recent.find(board => board.id !== missingBoardId)?.id;
    }
    try {
      if (id) await boards.load(id); else await boards.create();
    } catch (error) {
      if (id && error.status === 404 && !boards.board) {
        missingBoardId = id;
        throw new Error("该分镜项目已找不到。可以打开最近的项目，或在没有可用项目时新建。");
      }
      throw error;
    }
    missingBoardId = undefined;
    await refreshProjects(); return boards.agent?.summary || (recognition.isSupported() ? "准备好了，说说你的想法吧。" : "当前浏览器不支持语音，可以输入文字继续创作。");
  });
}
$("retryButton").addEventListener("click", () => clickAction(() => boards.board ? act(() => boards.refresh()) : connect()));
render(); await connect().catch(showError);
