import { icon, renderWorkspaceIcons } from "./workspace-icons.js";
import * as backend from "./backend-client.js";
import { createWorkspaceController } from "./workspace-controller.js";
import { renderSceneMarkup, renderSceneThumbnailMarkup, setRenderCatalog, markCatalogAssetFailed } from "./canvas-renderer.js";
import { downloadBackendExport } from "./file-download.js";
import { pageUrl } from "./home-controller.js";
import { BrowserSpeechRecognitionAdapter, BrowserVoiceFeedbackAdapter, VoiceSessionController } from "./voice-session.js";

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
$(".brand").href = pageUrl("index.html", location.search);
renderWorkspaceIcons();

let selectedElement = null;
let renderedProject = null;
let sceneListKey = "";
let assistantOpen = window.innerWidth > 980;
let voiceMessage = "";
let dialogMode = "new";
let toastTimer;
let memoryBusy = false;
let memories = [];
let catalogReady = false;
let renderTick = null;

const api = {
  workspace: backend.loadWorkspace, projects: backend.listProjects,
  create: backend.createProjectState, import: backend.importProjectState,
  action: backend.executeWorkspaceAction, export: backend.exportProjectState,
  resume: backend.resumeOrchestration, orchestrate: backend.startOrchestrationStream
};
const controller = createWorkspaceController(api, render);
const voice = new VoiceSessionController({
  recognition: new BrowserSpeechRecognitionAdapter(),
  feedback: new BrowserVoiceFeedbackAdapter(),
  submitTranscript: submitInput,
  onStatusChange(message) { voiceMessage = message; render(); },
  onListeningChange() { render(); },
  onPartialTranscript(text) { $("#voiceInput").value = text; resizeInput(); },
  onFinalTranscript(text) { $("#voiceInput").value = text; resizeInput(); }
});

function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 3500);
}
function showError(error) {
  $("#errorText").textContent = error?.message || String(error);
  $("#errorBanner").hidden = false;
}
function resizeInput() {
  const input = $("#voiceInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}
function scheduleRender() {
  if (renderTick) return;
  renderTick = requestAnimationFrame(() => { renderTick = null; sceneListKey = ""; renderCanvas(); renderScenes(); });
}
function currentScene() {
  const project = controller.state.snapshot?.project;
  return project?.scenes.find(scene => scene.id === project.activeSceneId);
}
function fitCanvas() {
  const scene = currentScene();
  if (!scene) return;
  const stage = $("#canvasStage");
  const surface = $("#canvasSurface");
  const viewport = $("#canvasViewport");
  stage.style.aspectRatio = `${scene.canvas.width} / ${scene.canvas.height}`;
  // 保持真实画布比例，窄屏依然按比例缩放，不拉伸作品。
  stage.style.minHeight = "0";
  const maxHeight = Math.max(100, viewport.clientHeight - 110);
  stage.style.maxWidth = `${Math.min(1200, maxHeight * scene.canvas.width / scene.canvas.height)}px`;
  surface.style.width = `${scene.canvas.width}px`;
  surface.style.height = `${scene.canvas.height}px`;
  surface.style.transform = `scale(${stage.clientWidth / scene.canvas.width})`;
  document.querySelectorAll(".scene-thumb-content").forEach(node => {
    const width = Number(node.dataset.width);
    node.style.transform = `scale(${node.parentElement.clientWidth / width})`;
  });
}
function renderCanvas() {
  const snapshot = controller.state.snapshot;
  if (!snapshot) return;
  const project = snapshot.project;
  const scene = currentScene();
  if (!scene) return;
  const surface = $("#canvasSurface");
  surface.style.background = scene.canvas.background?.color || "#ffffff";
  surface.innerHTML = renderSceneMarkup(project, scene, selectedElement, scheduleRender);
  surface.querySelectorAll("[data-element]").forEach(node => {
    node.classList.toggle("is-changed", controller.state.highlights.includes(node.dataset.element));
    const candidates = snapshot.pending?.nextAction?.options || [];
    node.classList.toggle("is-candidate", candidates.some(option =>
      (option.elementId || option.value) === node.dataset.element));
  });
  $("#emptyCanvas").hidden = Boolean(scene.elements.length);
  $("#sceneName").textContent = scene.name;
  $("#sceneEyebrow").textContent = `SCENE ${String(project.scenes.indexOf(scene) + 1).padStart(2, "0")}`;
  $("#sceneDescription").textContent = scene.description || "让灵感，先有一个轮廓。";
  $("#canvasSize").textContent = `${scene.canvas.width} × ${scene.canvas.height}`;
  $("#backgroundColorInput").value = scene.canvas.background?.color || "#ffffff";
  $("#narrationText").textContent = scene.narration || "每一步创作，都可以继续修改";
  const selected = scene.elements.find(element => element.id === selectedElement);
  $("#selectionLabel").textContent = selected
    ? `已选择：${selected.name || selected.content?.text || selected.label || "画面元素"}`
    : "选择画面中的元素，查看它的名称";
  fitCanvas();
}
function renderScenes() {
  const { snapshot, busy } = controller.state;
  if (!snapshot) return;
  const project = snapshot.project;
  const key = JSON.stringify(project);
  if (sceneListKey !== key) {
    sceneListKey = key;
    const ordered = [...project.scenes].sort((a, b) => a.order - b.order);
    $("#sceneList").innerHTML = ordered.map((scene, index) => `
      <button class="scene-button" data-scene="${escape(scene.id)}" aria-current="${scene.id === project.activeSceneId}" aria-label="镜头 ${index + 1}：${escape(scene.name)}">
        <div class="scene-thumbnail" style="aspect-ratio:${scene.canvas.width}/${scene.canvas.height};background:${escape(scene.canvas.background?.color || "#fff")}">
          <div class="scene-thumb-content" data-width="${scene.canvas.width}" style="width:${scene.canvas.width}px;height:${scene.canvas.height}px" inert>${renderSceneThumbnailMarkup(project, scene, scheduleRender)}</div>
          ${scene.elements.length ? "" : `<div class="scene-empty-thumb">${icon("image")}</div>`}<span class="scene-number">${String(index + 1).padStart(2, "0")}</span>
        </div><div class="scene-label"><strong>${String(index + 1).padStart(2, "0")} · ${escape(scene.name)}</strong><span>${scene.durationMs ? `${scene.durationMs / 1000}s` : "分镜"}</span></div>
      </button>`).join("");
    $("#sceneCount").textContent = ordered.length;
    const history = [...snapshot.history].reverse();
    $("#historyCount").textContent = history.length;
    $("#historyList").innerHTML = history.slice(0, 40).map(item => `<li>${escape(item.summary)}<time>${escape(new Date(item.createdAt).toLocaleTimeString("zh-CN", {hour:"2-digit",minute:"2-digit"}))}</time></li>`).join("") || "<li>暂无操作</li>";
    fitCanvas();
  }
  $("#sceneList").querySelectorAll("button").forEach(button => { button.disabled = busy; });
}
function render() {
  const state = controller.state;
  const { snapshot, busy } = state;
  $("#errorBanner").hidden = !state.error;
  if (state.error) $("#errorText").textContent = state.error;
  document.querySelectorAll("[data-requires-project]").forEach(node => { node.disabled = !snapshot || busy; });
  // 麦克风必须始终可停止，即使当前请求仍在处理中。
  $("#voiceButton").disabled = !voice.isActive() && (!snapshot || busy);
  $("#newButton").disabled = busy;
  $("#importButton").disabled = busy;
  $("#retryButton").disabled = busy;
  $("#undoButton").disabled = busy || !snapshot?.undoRedo.canUndo;
  $("#redoButton").disabled = busy || !snapshot?.undoRedo.canRedo;
  $("#undoResult").hidden = busy || !snapshot?.undoRedo.canUndo;
  $("#saveStatus").dataset.busy = String(busy);
  $("#saveStatus").innerHTML = `<i></i>${state.error ? "连接待确认" : busy ? "处理中…" : snapshot ? "已同步" : "等待连接"}`;
  $("#assistantConnection").textContent = busy ? "正在协助创作" : snapshot ? "准备好和你一起创作" : "等待连接";
  $("#voiceButton").setAttribute("aria-pressed", String(voice.isActive()));
  $("#voiceButton").setAttribute("aria-label", voice.isActive() ? "结束语音创作" : "开始语音创作");
  $("#voiceStatus").textContent = voice.isActive() && voiceMessage ? voiceMessage : busy ? state.message : snapshot?.pending ? "回答助手的问题，继续这次创作" : snapshot ? "准备好了，说说你的想法吧" : "请先启动后端服务，再重新连接";
  $("#composerContext").dataset.listening = String(voice.isListening());
  $("#composerContext").dataset.busy = String(busy);
  $(".workspace").classList.toggle("assistant-hidden", !assistantOpen);
  $("#toggleAssistant").setAttribute("aria-expanded", String(assistantOpen));
  $("#voiceInput").placeholder = snapshot?.pending ? "回答助手的问题，继续这次创作…" : "描述你的画面，或说“把标题放大一点”…";
  $("#assistantPanel").dataset.active = String(Boolean(state.lastInput || snapshot?.pending));
  $("#turnCard").hidden = !state.lastInput;
  $("#lastInput").textContent = state.lastInput;
  $("#resultHeading").textContent = busy ? "正在构思画面" : state.error ? "这次需要再试一下" : snapshot?.pending ? "还需要你确认一下" : "画面已更新";
  $("#resultMessage").textContent = presentMessage(state.error || (busy ? state.message : state.summary?.message || state.message));
  $("#eventCount").textContent = state.events.length;
  $("#eventLog").innerHTML = state.events.map(event => `<li>${escape(event.message || event.question || event.export?.filename || stageLabel(event.stage) || "已更新画面")}</li>`).join("");
  const usage = snapshot?.usage?.lastTurn || state.summary?.tokenUsage;
  $("#tokenUsage").textContent = usage ? `本轮用量：${usage.totalTokens || 0} Tokens` : "";
  $("#tokenTotal").textContent = `项目累计：${snapshot?.usage?.total?.totalTokens || 0} Tokens`;
  const pending = snapshot?.pending;
  $("#clarificationCard").hidden = !pending;
  if (pending) {
    $("#clarificationQuestion").textContent = pending.nextAction.question;
    $("#clarificationOptions").innerHTML = (pending.nextAction.options || []).map(option =>
      `<button data-answer="${escape(option.value || option.id || option.label)}" ${busy ? "disabled" : ""}>${escape(option.label)}</button>`).join("");
  }
  if (!snapshot) return;
  if (renderedProject !== snapshot.project) {
    const previousId = renderedProject?.id;
    const previousScene = renderedProject?.activeSceneId;
    renderedProject = snapshot.project;
    if (previousId !== snapshot.project.id || previousScene !== snapshot.project.activeSceneId) selectedElement = null;
    if (previousId !== snapshot.project.id) {
      const url = new URL(location.href);
      url.searchParams.set("projectId", snapshot.project.id);
      history.replaceState(null, "", url);
    }
    renderCanvas();
  }
  $("#renameButton").textContent = snapshot.project.title;
  const select = $("#projectSelect");
  const optionsKey = JSON.stringify(state.projects);
  if (select.dataset.key !== optionsKey) {
    select.innerHTML = state.projects.map(project => `<option value="${escape(project.id)}">${escape(project.title)}</option>`).join("");
    select.dataset.key = optionsKey;
  }
  select.value = snapshot.project.id;
  renderScenes();
}
function presentMessage(message) { return String(message || "").replace(/^已执行\s*(\d+)\s*条命令$/, "已完成 $1 处画面调整"); }
function stageLabel(stage) {
  return ({understanding:"理解你的想法",planning:"安排画面",executing:"更新画布",summarizing:"整理结果",completed:"已完成"})[stage] || "";
}
async function submitInput(text, displayText = text) {
  if (controller.state.busy) throw new Error("上一条指令还在处理中，请稍候");
  const result = await controller.submit(text, displayText);
  if (!result) return controller.state.error || "指令未发送，请检查后端连接";
  $("#voiceInput").value = "";
  resizeInput();
  if (controller.state.snapshot.pending) assistantOpen = true;
  renderCanvas();
  render();
  if (controller.state.snapshot.pending) $("#clarificationCard").scrollIntoView({block:"nearest"});
  const exports = (result.events || []).filter(event => event.type === "EXPORT_COMPLETED");
  for (const event of exports) {
    try { await downloadResult(event.export); } catch (error) { showError(error); }
  }
  return result.summary?.message || "画布已更新";
}
async function downloadResult(result) {
  await downloadBackendExport(result, {project:controller.state.snapshot.project,element:$("#canvasSurface")});
  toast("文件已交给浏览器下载");
}
async function toggleVoice() {
  if (voice.isActive()) await voice.stop();
  else if (controller.state.snapshot && !controller.state.busy) await voice.start();
  render();
}
function openNameDialog(mode) {
  if (controller.state.busy) return;
  dialogMode = mode;
  $("#nameDialogTitle").textContent = mode === "new" ? "新建项目" : "重命名项目";
  $("#nameInput").value = mode === "new" ? "" : controller.state.snapshot.project.title;
  $("#nameDialog").showModal();
  $("#nameInput").focus();
}
async function beforeProjectSwitch() {
  await voice.stop({speak:false});
  voiceMessage = "";
  selectedElement = null;
  $("#voiceInput").value = "";
  resizeInput();
}

$("#composerForm").addEventListener("submit", async event => { event.preventDefault(); await submitInput($("#voiceInput").value); });
$("#voiceInput").addEventListener("input", resizeInput);
$("#voiceInput").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("#composerForm").requestSubmit(); } });
$("#voiceButton").addEventListener("click", toggleVoice);
$("#toggleAssistant").addEventListener("click", () => { assistantOpen = !assistantOpen; render(); requestAnimationFrame(fitCanvas); });
$("#clearUsage").addEventListener("click", () => controller.action({action:"reset_usage"}));
$("#undoButton").addEventListener("click", () => controller.action({action:"undo"}));
$("#undoResult").addEventListener("click", () => controller.action({action:"undo"}));
$("#redoButton").addEventListener("click", () => controller.action({action:"redo"}));
$("#fitButton").addEventListener("click", fitCanvas);
$("#backgroundColorInput").addEventListener("change", event => controller.action({action:"set_background",sceneId:currentScene().id,color:event.target.value}));
$("#newButton").addEventListener("click", () => openNameDialog("new"));
$("#renameButton").addEventListener("click", () => openNameDialog("rename"));
$("#nameForm").addEventListener("submit", async event => {
  event.preventDefault();
  const title = $("#nameInput").value.trim();
  if (!title) { $("#nameInput").focus(); return; }
  $("#nameDialog").close();
  if (dialogMode === "new") { await beforeProjectSwitch(); await controller.create(title); }
  else await controller.action({action:"rename_project",title});
});
$("#projectSelect").addEventListener("change", async event => { const id = event.target.value; await beforeProjectSwitch(); await controller.load(id); });
$("#importButton").addEventListener("click", () => $("#importInput").click());
$("#importInput").addEventListener("change", async event => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  try { const payload = JSON.parse(await file.text()); await beforeProjectSwitch(); await controller.import(payload); }
  catch { showError(new Error("文件不是有效的 JSON，请选择导出的项目文件")); }
});
$("#retryButton").addEventListener("click", async () => { await initialize(); });
$("#dismissError").addEventListener("click", () => { controller.state.error = null; $("#errorBanner").hidden = true; });
$("#exportButton").addEventListener("click", () => {
  const open = $("#exportMenu").hidden;
  $("#exportMenu").hidden = !open;
  $("#exportButton").setAttribute("aria-expanded", String(open));
  if (open) $("#exportMenu button").focus();
});
document.addEventListener("click", async event => {
  const scene = event.target.closest("[data-scene]");
  if (scene && !controller.state.busy) { selectedElement = null; await controller.action({action:"switch_scene",sceneId:scene.dataset.scene}); }
  const element = event.target.closest("#canvasSurface [data-element]");
  if (element) { selectedElement = element.dataset.element; renderCanvas(); }
  const prompt = event.target.closest("[data-prompt]");
  if (prompt && !controller.state.busy && controller.state.snapshot) { $("#voiceInput").value = prompt.dataset.prompt; $("#voiceInput").focus(); resizeInput(); }
  const answer = event.target.closest("[data-answer]");
  if (answer) await submitInput(answer.dataset.answer, answer.textContent);
  const download = event.target.closest("[data-export]");
  if (download) {
    $("#exportMenu").hidden = true;
    $("#exportButton").setAttribute("aria-expanded", "false");
    const result = await controller.export(download.dataset.export);
    if (result) { try { await downloadResult(result); } catch (error) { showError(error); } }
  }
  if (!event.target.closest(".export-wrap")) { $("#exportMenu").hidden = true; $("#exportButton").setAttribute("aria-expanded", "false"); }
  if (event.target.closest("[data-close-dialog]")) event.target.closest("dialog").close();
});
document.addEventListener("keydown", event => {
  const typing = event.target.matches("input,textarea,select,[contenteditable=true]");
  if (event.altKey && event.code === "KeyV" && !event.repeat) { event.preventDefault(); toggleVoice(); }
  if (!typing && (event.ctrlKey || event.metaKey) && event.code === "KeyZ") {
    event.preventDefault();
    const action = event.shiftKey ? "redo" : "undo";
    if (controller.state.snapshot?.undoRedo[event.shiftKey ? "canRedo" : "canUndo"]) controller.action({action});
  }
  if (event.key === "Escape") {
    $("#exportMenu").hidden = true; $("#exportButton").setAttribute("aria-expanded", "false");
    if (window.innerWidth <= 980) { assistantOpen = false; render(); }
    selectedElement = null; renderCanvas();
  }
  if (event.target.closest("#exportMenu") && ["ArrowDown","ArrowUp","Home","End"].includes(event.key)) {
    event.preventDefault();
    const items = [...$("#exportMenu").querySelectorAll("button")];
    const index = items.indexOf(document.activeElement);
    items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
  }
});
document.addEventListener("error", event => {
  const image = event.target;
  if (image.tagName !== "IMG" || !image.closest(".canvas-surface,.scene-thumb-content")) return;
  if (image.dataset.assetPath) { markCatalogAssetFailed(image.dataset.assetPath); scheduleRender(); }
  else { const label = document.createElement("span"); label.textContent = `${image.alt || "图片"}暂不可用`; image.replaceWith(label); }
}, true);
new ResizeObserver(fitCanvas).observe($("#canvasViewport"));
window.addEventListener("beforeunload", () => voice.stop({speak:false}));

// 偏好编辑只提交表单字段，状态、验证与持久化均来自后端。
const memoryStatus = {candidate:"待确认",active:"已生效",rejected:"已拒绝",archived:"已归档"};
async function refreshMemories() {
  memories = (await backend.listUserMemories()).memories;
  $("#memoryList").innerHTML = memories.map(item => `<div class="memory-item"><p>${escape(item.content)}</p><div class="memory-item-bottom"><span>${escape(memoryStatus[item.status] || item.status)}</span><button class="text-button" data-memory="edit" data-id="${escape(item.id)}">编辑</button><button class="text-button" data-memory="${item.status === "active" ? "archive" : "activate"}" data-id="${escape(item.id)}">${item.status === "active" ? "停用" : "启用"}</button><button class="text-button" data-memory="delete" data-id="${escape(item.id)}">删除</button></div></div>`).join("") || "<p>还没有偏好，添加第一条吧。</p>";
}
async function memoryRequest(operation) {
  if (memoryBusy) return;
  memoryBusy = true;
  $("#memoryError").textContent = "";
  $("#memoryDialog").querySelectorAll("button,input,select,textarea").forEach(node => { if (!node.hasAttribute("data-close-dialog")) node.disabled = true; });
  try { await operation(); await refreshMemories(); }
  catch (error) { $("#memoryError").textContent = error.message; }
  finally { memoryBusy = false; $("#memoryDialog").querySelectorAll("button,input,select,textarea").forEach(node => { node.disabled = false; }); }
}
$("#memoryButton").addEventListener("click", () => { $("#memoryDialog").showModal(); memoryRequest(async () => {}); });
$("#memoryForm").addEventListener("submit", event => {
  event.preventDefault();
  const content = $("#memoryContent").value.trim();
  const kind = $("#memoryKind").value;
  if (!content) return;
  memoryRequest(async () => { await backend.createUserMemory(backend.DEFAULT_USER_ID,{content,kind,scope:"global"}); $("#memoryContent").value = ""; });
});
$("#memoryList").addEventListener("click", event => {
  const button = event.target.closest("[data-memory]");
  if (!button || memoryBusy) return;
  const id = button.dataset.id;
  if (button.dataset.memory === "edit") {
    const item = memories.find(memory => memory.id === id);
    const wrapper = button.closest(".memory-item");
    if (wrapper.querySelector("form")) return;
    const form = document.createElement("form");
    form.className = "memory-edit";
    form.innerHTML = `<input aria-label="偏好内容" required value="${escape(item.content)}"/><button class="button small">保存</button>`;
    wrapper.append(form);
    form.querySelector("input").focus();
    form.addEventListener("submit", event => { event.preventDefault(); const content = form.querySelector("input").value; memoryRequest(() => backend.updateUserMemory(id,{content})); });
  } else if (button.dataset.memory === "delete") {
    memoryRequest(() => backend.deleteUserMemory(id));
  } else {
    memoryRequest(() => backend.updateUserMemory(id,{status:button.dataset.memory === "activate" ? "active" : "archived"}));
  }
});

async function initialize() {
  if (!catalogReady) {
    try { setRenderCatalog(await backend.loadRenderCatalog()); catalogReady = true; }
    catch { /* 项目连接错误统一由控制器展示；重新连接时继续读取目录。 */ }
  }
  sceneListKey = "";
  renderedProject = null;
  await controller.load(new URLSearchParams(location.search).get("projectId"));
  if (controller.state.snapshot?.pending) assistantOpen = true;
  render();
}
render();
initialize();
