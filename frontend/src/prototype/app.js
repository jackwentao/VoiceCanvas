import { COMMAND_BINDINGS, initialHistory, initialProject, initialSession } from "./mock-data.js";
import {
  DEFAULT_USER_ID,
  DEFAULT_PROJECT_ID,
  createProjectState,
  createUserMemory,
  deleteUserMemory,
  importProjectState,
  listUserMemories,
  loadProjectState,
  resolveCatalogAssetUrl,
  resumeOrchestration,
  startOrchestrationStream,
  updateUserMemory
} from "./backend-client.js";
import {
  applyBackendEvent,
  appendBackendError,
  applyBackendResponse,
  createBackendPendingSession
} from "./state-sync.js";
import { mergeElementPatch } from "./element-patch.js";
import { sceneDisplayNumber, visibleSceneEntries } from "./scene-numbering.js";
import { fitTextFontSize } from "./text-layout.js";
import {
  exportFromBackendResult,
  exportProjectFile,
  exportSceneImage,
  importProjectFile
} from "./export-service.js";
import {
  BrowserSpeechRecognitionAdapter,
  BrowserVoiceFeedbackAdapter,
  VoiceSessionController,
  resolveClarificationOption
} from "./voice-session.js";

const state = {
  project: structuredClone(initialProject),
  history: structuredClone(initialHistory),
  session: structuredClone(initialSession),
  eventLog: [],
  selectedElementId: null,
  voiceStatus: "等待语音输入",
  voiceRecording: null,
  voiceSessionActive: false,
  voiceListening: false,
  voiceDraftReady: false,
  settingsOpen: false,
  memory: {
    panelOpen: false,
    loading: false,
    error: null,
    memories: [],
    editingId: null
  },
  backend: {
    projectId: DEFAULT_PROJECT_ID,
    connected: false,
    lastError: null
  }
};

const stageLabels = {
  listening: "监听中",
  understanding: "理解需求",
  planning: "拆解任务",
  calling_tool: "调用工具",
  executing: "执行命令",
  waiting_for_user: "等待确认",
  summarizing: "总结变更",
  completed: "已完成",
  failed: "执行失败"
};

const commandSummaries = {
  CREATE_SCENE: "创建镜头",
  UPDATE_SCENE: "更新镜头",
  DELETE_SCENE: "删除镜头",
  SWITCH_SCENE: "切换镜头",
  ADD_ELEMENT: "新增元素",
  UPDATE_ELEMENT: "修改元素",
  DELETE_ELEMENT: "删除元素",
  ARRANGE_LAYOUT: "调整布局",
  UPDATE_PROJECT_STYLE: "更新风格",
  EXPORT_PROJECT: "导出项目"
};

const memoryKindLabels = {
  style_preference: "风格偏好",
  layout_preference: "布局偏好",
  naming_convention: "命名习惯",
  workflow_preference: "工作流偏好",
  negative_preference: "负向偏好"
};

const memoryScopeLabels = {
  global: "全局",
  canvas: "画布",
  storyboard: "分镜",
  commerce: "带货"
};

const memoryStatusLabels = {
  candidate: "待确认",
  active: "已生效",
  rejected: "已拒绝",
  archived: "已归档"
};

const renderCatalogState = {
  ready: false,
  items: [],
  byKey: new Map(),
  aliasRules: []
};

const catalogAssetState = {
  urls: new Map(),
  pending: new Set(),
  failed: new Set()
};

const $ = (selector) => document.querySelector(selector);
let voiceController = null;

async function hydrateRenderCatalog() {
  try {
    const response = await fetch("./render-catalog.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`render catalog ${response.status}`);
    indexRenderCatalog(await response.json());
  } catch (error) {
    console.warn("Render Catalog 加载失败，语义素材将使用占位渲染", error);
  }
}

function indexRenderCatalog(catalog) {
  const items = Array.isArray(catalog?.items) ? catalog.items : [];
  renderCatalogState.items = items;
  renderCatalogState.byKey = new Map(items.map((item) => [item.renderKey, item]));
  renderCatalogState.aliasRules = items.flatMap((item) => catalogAliasRulesForItem(item));
  renderCatalogState.ready = true;
}

function catalogAliasRulesForItem(item) {
  const baseAliases = [item.renderKey, item.displayName, ...(item.aliases || [])];
  const rules = baseAliases.map((alias) => ({
    alias,
    renderKey: item.renderKey,
    variant: null
  }));

  for (const variant of item.variants || []) {
    for (const alias of [variant.key, variant.displayName, ...(variant.aliases || [])]) {
      rules.push({
        alias,
        renderKey: item.renderKey,
        variant: variant.key
      });
    }
  }
  return rules;
}

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function createLocalBlankProject(title = "未命名项目", mode = "storyboard") {
  const timestamp = nowIso();
  return {
    id: makeId("project"),
    title,
    mode,
    activeSceneId: "scene_1",
    metadata: {
      source: "local_fallback",
      version: 1
    },
    createdAt: timestamp,
    updatedAt: timestamp,
    scenes: [
      {
        id: "scene_1",
        name: "空白画布",
        order: 1,
        description: null,
        canvas: {
          width: 960,
          height: 540,
          background: {
            type: "solid",
            color: "#ffffff"
          }
        },
        elements: [],
        createdAt: timestamp,
        updatedAt: timestamp
      }
    ]
  };
}

function activeScene() {
  return state.project.scenes.find((scene) => scene.id === state.project.activeSceneId);
}

function pushEvent(event) {
  state.eventLog.unshift({
    id: makeId("event"),
    createdAt: nowIso(),
    ...event
  });
  state.eventLog = state.eventLog.slice(0, 14);
}

function pushHistory(command, patches, summary) {
  state.history.unshift({
    id: makeId("history"),
    command,
    patches,
    summary,
    status: "applied",
    createdAt: nowIso()
  });
}

function publishStage(stage, message) {
  state.session.stage = stage;
  pushEvent({
    type: "STAGE_CHANGED",
    sessionId: state.session.id,
    stage,
    message
  });
}

function publishPatch(patch, commandId) {
  pushEvent({
    type: "CANVAS_PATCH_APPLIED",
    sessionId: state.session.id,
    patch,
    commandId
  });
}

function executeCommand(command) {
  const patches = [];
  const timestamp = nowIso();

  if (command.type === "SWITCH_SCENE") {
    state.project.activeSceneId = command.payload.sceneId;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ACTIVE_SCENE_CHANGED",
      sceneId: command.payload.sceneId,
      createdAt: timestamp
    });
  }

  if (command.type === "ADD_ELEMENT") {
    const targetScene = state.project.scenes.find((scene) => scene.id === command.payload.sceneId);
    const element = {
      id: makeId("el"),
      createdAt: timestamp,
      updatedAt: timestamp,
      ...command.payload.element
    };
    targetScene.elements.push(element);
    targetScene.updatedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ELEMENT_ADDED",
      sceneId: targetScene.id,
      element,
      createdAt: timestamp
    });
  }

  if (command.type === "UPDATE_ELEMENT") {
    const targetScene = state.project.scenes.find((scene) => scene.id === command.payload.sceneId);
    const element = targetScene.elements.find((item) => item.id === command.payload.elementId);
    Object.assign(element, mergeElementPatch(element, command.payload.patch), { updatedAt: timestamp });
    targetScene.updatedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "ELEMENT_UPDATED",
      sceneId: targetScene.id,
      elementId: element.id,
      patch: command.payload.patch,
      createdAt: timestamp
    });
  }

  if (command.type === "EXPORT_PROJECT") {
    state.project.metadata ||= {};
    state.project.metadata.lastExportedAt = timestamp;
    patches.push({
      id: makeId("patch"),
      commandId: command.id,
      type: "EXPORT_COMPLETED",
      result: {
        format: command.payload.format,
        data: command.payload.format === "json" ? state.project : undefined,
        url: command.payload.format !== "json" ? "local://prototype-export.png" : undefined,
        createdAt: timestamp
      },
      createdAt: timestamp
    });
  }

  patches.forEach((patch) => publishPatch(patch, command.id));
  pushHistory(command, patches, `${commandSummaries[command.type]}：${command.reason || "原型命令"}`);
}

function beginSession(userInput) {
  const sessionId = makeId("session");
  state.session = {
    id: sessionId,
    status: "RUNNING",
    stage: "listening",
    originalUserInput: userInput,
    currentUserInput: userInput,
    progress: {
      completedSteps: 0,
      totalSteps: 3,
      message: "收到语音输入"
    },
    taskPlan: null,
    pendingClarification: null,
    lastSummary: null
  };
  pushEvent({
    type: "TRANSCRIPT_FINAL",
    sessionId,
    text: userInput
  });
}

function submitVoiceDraft() {
  const input = $("#voiceInput").value.trim();
  if (!input) return;

  state.voiceDraftReady = false;
  state.voiceStatus = "已发送";
  runCustomInput();
}

async function playEvents(steps) {
  setBusy(true);
  for (const step of steps) {
    await wait(step.delay || 420);
    step.run();
    render();
  }
  setBusy(false);
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setBusy(isBusy) {
  document.body.dataset.busy = String(isBusy);
  document.querySelectorAll("[data-run]").forEach((button) => {
    button.disabled = isBusy;
  });
}

async function hydrateBackendState() {
  try {
    state.voiceStatus = "正在同步后端状态";
    const response = await loadProjectState(state.backend.projectId);
    applyBackendResponse(state, response);
    state.backend.connected = true;
    state.backend.lastError = null;
    state.voiceStatus = "后端状态已同步";
  } catch (error) {
    state.backend.connected = false;
    state.backend.lastError = error.message || String(error);
    appendBackendError(state, error);
  }

  render();
}

async function runBackendInput(userInput, fallback) {
  if (!userInput) return null;

  setBusy(true);
  state.settingsOpen = false;
  state.voiceDraftReady = false;
  state.voiceStatus = "正在提交后端编排";
  state.session = createBackendPendingSession(makeId("session"), userInput);
  pushEvent({
    type: "TRANSCRIPT_FINAL",
    sessionId: state.session.id,
    text: userInput
  });
  render();

  try {
    const response = await startOrchestrationStream(state.backend.projectId, userInput, {
      onEvent: async (event) => {
        applyBackendEvent(state, event, { userInput });
        if (event.type === "EXPORT_COMPLETED") {
          await exportFromBackendResult(event.export, state.project);
        }
        state.backend.connected = true;
        state.backend.lastError = null;
        render();
      }
    });
    if (!response) {
      throw new Error("后端流式响应缺少最终结果");
    }
    applyBackendResponse(state, { ...response, events: [] }, { userInput });
    state.backend.connected = true;
    state.backend.lastError = null;
    render();
    return response;
  } catch (error) {
    state.backend.connected = false;
    state.backend.lastError = error.message || String(error);
    appendBackendError(state, error);
    render();
    if (fallback) {
      await fallback();
    }
    return null;
  } finally {
    setBusy(false);
  }
}

async function runBackendResume(answer, fallback) {
  const pending = state.session.pendingClarification;
  const sessionId = pending?.resumePolicy?.sessionId || state.session.id;
  if (!answer || !sessionId) return null;

  setBusy(true);
  state.settingsOpen = false;
  state.voiceDraftReady = false;
  state.voiceStatus = "正在恢复澄清任务";
  pushEvent({
    type: "TRANSCRIPT_FINAL",
    sessionId,
    text: answer
  });
  render();

  try {
    const response = await resumeOrchestration(state.backend.projectId, sessionId, answer);
    applyBackendResponse(state, response, { userInput: answer });
    state.backend.connected = true;
    state.backend.lastError = null;
    render();
    return response;
  } catch (error) {
    state.backend.connected = false;
    state.backend.lastError = error.message || String(error);
    appendBackendError(state, error);
    render();
    if (fallback) {
      await fallback();
    }
    return null;
  } finally {
    setBusy(false);
  }
}

async function handleVoiceTranscript(text) {
  const pending = state.session.pendingClarification;
  const response = pending
    ? await runBackendResume(text, () => resumeClarificationFromVoice(text))
    : await runBackendInput(text, () => runLocalFallbackForInput(text));

  return response?.summary?.message || state.session.lastSummary?.message || state.voiceStatus;
}

async function resumeClarificationFromVoice(answer) {
  const pending = state.session.pendingClarification;
  const option = resolveClarificationOption(answer, pending?.options || []);
  if (!option) {
    state.voiceStatus = "我还不能确定你指的是哪一个，请换一种说法";
    render();
    return;
  }
  resumeClarification(option.value || option.elementId || option.id);
}

async function runLocalFallbackForInput(input) {
  if (input.includes("箭头")) {
    await runArrowDemoLocal();
  } else if (input.includes("标题") || input.includes("它")) {
    await runClarificationDemoLocal();
  } else if (input.includes("导出")) {
    await runExportDemoLocal();
  } else {
    await runStoryboardDemoLocal();
  }
}

function runStoryboardDemo() {
  return runBackendInput(COMMAND_BINDINGS[0].userInput, runStoryboardDemoLocal);
}

function runArrowDemoLocal() {
  return runArrowDemo();
}

function runClarificationDemoLocal() {
  return runClarificationDemo();
}

function runExportDemoLocal() {
  return runExportDemo();
}

function runStoryboardDemoLocal() {
  const input = COMMAND_BINDINGS[0].userInput;
  beginSession(input);
  const commands = [
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "先展示主图镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_hook" }
    },
    {
      id: makeId("cmd"),
      type: "ADD_ELEMENT",
      source: "ai",
      reason: "补充新品上市标签",
      createdAt: nowIso(),
      payload: {
        sceneId: "scene_hook",
        element: {
          name: "新品上市标签",
          type: "text",
          text: "新品上市",
          x: 606,
          y: 88,
          width: 170,
          height: 52,
          zIndex: 5,
          style: {
            fontSize: 28,
            fontWeight: "bold",
            color: "#173b2c",
            align: "center",
            backgroundColor: "#f6c453"
          }
        }
      }
    },
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "继续展示卖点镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_product" }
    }
  ];

  playEvents([
    {
      run: () => publishStage("understanding", "识别到三镜头带货分镜")
    },
    {
      run: () => {
        state.session.taskPlan = {
          goal: "生成低糖奶茶带货分镜",
          tasks: [
            { id: "task_1", title: "确认主图钩子", status: "completed", relatedSceneId: "scene_hook" },
            { id: "task_2", title: "补充新品标签", status: "in_progress", relatedSceneId: "scene_hook" },
            { id: "task_3", title: "切到卖点镜头", status: "pending", relatedSceneId: "scene_product" }
          ]
        };
        state.session.progress = {
          completedSteps: 1,
          totalSteps: 3,
          message: "正在补充关键卖点"
        };
        publishStage("planning", "拆成镜头、元素、卖点三步");
        pushEvent({
          type: "PROGRESS",
          sessionId: state.session.id,
          progress: state.session.progress
        });
      }
    },
    {
      run: () => {
        publishStage("executing", "通过 CommandExecutor 执行画布命令");
        commands.slice(0, 2).forEach(executeCommand);
        state.session.progress = {
          completedSteps: 2,
          totalSteps: 3,
          message: "主图已补充新品标签"
        };
      }
    },
    {
      run: () => {
        executeCommand(commands[2]);
        state.session.progress = {
          completedSteps: 3,
          totalSteps: 3,
          message: "已切换到卖点镜头"
        };
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: input,
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "updated",
              targetType: "scene",
              targetName: "主图",
              description: "补充新品上市标签"
            },
            {
              type: "updated",
              targetType: "scene",
              targetName: "卖点",
              description: "切换为当前编辑镜头"
            }
          ]
        };
        publishStage("completed", "本轮变更已完成");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runArrowDemo() {
  const input = COMMAND_BINDINGS[1].userInput;
  beginSession(input);
  const commands = [
    {
      id: makeId("cmd"),
      type: "SWITCH_SCENE",
      source: "ai",
      reason: "定位到第二镜头",
      createdAt: nowIso(),
      payload: { sceneId: "scene_product" }
    },
    {
      id: makeId("cmd"),
      type: "ADD_ELEMENT",
      source: "ai",
      reason: "从奶茶产品指向低糖标签",
      createdAt: nowIso(),
      payload: {
        sceneId: "scene_product",
        element: {
          name: "核心卖点箭头",
          type: "connector",
          connectorType: "arrow",
          from: { elementId: "el_product_cup", anchor: "right" },
          to: { elementId: "el_low_sugar_tag", anchor: "left" },
          text: "核心卖点",
          x: 555,
          y: 174,
          width: 118,
          height: 22,
          zIndex: 5,
          style: {
            stroke: "#f15b4a",
            strokeWidth: 4,
            arrowEnd: true
          }
        }
      }
    }
  ];

  playEvents([
    {
      run: () => publishStage("understanding", "目标元素已匹配：奶茶产品、低糖标签")
    },
    {
      run: () => {
        publishStage("executing", "执行 SWITCH_SCENE 和 ADD_ELEMENT");
        commands.forEach(executeCommand);
      }
    },
    {
      run: () => {
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: input,
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "created",
              targetType: "element",
              targetName: "核心卖点箭头",
              description: "新增从奶茶产品到低糖标签的箭头"
            }
          ]
        };
        publishStage("completed", "箭头已添加");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

function runClarificationDemo() {
  const input = COMMAND_BINDINGS[2].userInput;
  beginSession(input);
  playEvents([
    {
      run: () => publishStage("understanding", "发现多个标题候选")
    },
    {
      run: () => {
        state.session.status = "WAITING_FOR_USER";
        state.session.stage = "waiting_for_user";
        state.session.pendingClarification = {
          id: makeId("clarification"),
          originalInput: input,
          question: "当前有主标题、低糖标签和优惠标签，你想移动哪一个？",
          expectedAnswerType: "element_selection",
          options: [
            { id: "el_title_hook", label: "主标题", value: "el_title_hook" },
            { id: "el_low_sugar_tag", label: "低糖标签", value: "el_low_sugar_tag" },
            { id: "el_offer", label: "优惠标签", value: "el_offer" }
          ],
          createdAt: nowIso()
        };
        pushEvent({
          type: "CLARIFICATION_REQUESTED",
          sessionId: state.session.id,
          question: state.session.pendingClarification.question,
          options: state.session.pendingClarification.options
        });
      }
    }
  ]);
}

function resumeClarification(elementId) {
  if (!state.session.pendingClarification) return;

  const targetScene = state.project.scenes.find((scene) => scene.elements.some((element) => element.id === elementId));
  const command = {
    id: makeId("cmd"),
    type: "UPDATE_ELEMENT",
    source: "ai",
    reason: "恢复澄清后移动目标标题",
    createdAt: nowIso(),
    payload: {
      sceneId: targetScene.id,
      elementId,
      patch: {
        y: 36,
        zIndex: 8
      }
    }
  };

  beginSession(`澄清回答：${elementId}`);
  playEvents([
    {
      run: () => publishStage("executing", "恢复原任务并执行 UPDATE_ELEMENT")
    },
    {
      run: () => {
        executeCommand({
          id: makeId("cmd"),
          type: "SWITCH_SCENE",
          source: "ai",
          reason: "定位到目标元素所在镜头",
          createdAt: nowIso(),
          payload: { sceneId: targetScene.id }
        });
        executeCommand(command);
        state.session.status = "COMPLETED";
        state.session.lastSummary = {
          userInput: "把标题放上面",
          completed: true,
          stage: "completed",
          changes: [
            {
              type: "updated",
              targetType: "element",
              targetName: targetScene.elements.find((element) => element.id === elementId).name,
              description: "已移动到画布顶部"
            }
          ]
        };
        publishStage("completed", "澄清任务已恢复完成");
        pushEvent({
          type: "TURN_SUMMARY",
          sessionId: state.session.id,
          summary: state.session.lastSummary
        });
      }
    }
  ]);
}

async function runExportDemo() {
  return runDirectProjectExport();
}

async function runDirectProjectExport() {
  const input = COMMAND_BINDINGS[3].userInput;
  beginSession(input);
  publishStage("executing", "调用 Exporter 导出 Project JSON");

  try {
    exportProjectFile(state.project);
    completeExportSession(input, "Project JSON", "已导出可再次载入的项目文件");
  } catch (error) {
    appendBackendError(state, error);
  }

  render();
}

async function runDirectSceneImageExport() {
  const input = "导出当前分镜图片";
  beginSession(input);
  publishStage("executing", "导出当前分镜图片");

  try {
    await exportSceneImage(state.project, { sceneId: state.project.activeSceneId });
    completeExportSession(input, "PNG 图片", "已导出当前分镜图片");
  } catch (error) {
    appendBackendError(state, error);
  }

  render();
}

function completeExportSession(userInput, targetName, description) {
  state.session.status = "COMPLETED";
  state.session.stage = "completed";
  state.session.progress = {
    completedSteps: 1,
    totalSteps: 1,
    message: "导出完成"
  };
  state.session.lastSummary = {
    userInput,
    completed: true,
    stage: "completed",
    message: "导出完成",
    changes: [
      {
        type: "exported",
        targetType: "export",
        targetName,
        description
      }
    ]
  };
  publishStage("completed", "导出完成");
  pushEvent({
    type: "EXPORT_COMPLETED",
    sessionId: state.session.id,
    message: description
  });
  pushEvent({
    type: "TURN_SUMMARY",
    sessionId: state.session.id,
    summary: state.session.lastSummary
  });
}

async function runProjectAction(action) {
  state.settingsOpen = false;

  if (action === "new") {
    await createNewProject();
  }

  if (action === "load") {
    openProjectFilePicker();
  }

  if (action === "export-image") {
    await runDirectSceneImageExport();
  }

  render();
}

async function createNewProject() {
  const title = "未命名项目";
  setBusy(true);
  state.voiceStatus = "正在新建项目";
  render();

  try {
    const response = await createProjectState({ title, mode: "storyboard" });
    applyBackendResponse(state, response, { userInput: "新建项目" });
    state.backend.projectId = response.project.id;
    state.backend.connected = true;
    state.backend.lastError = null;
    state.voiceStatus = "项目已新建";
  } catch (error) {
    const project = createLocalBlankProject(title);
    state.project = project;
    state.history = [];
    state.session = structuredClone(initialSession);
    state.backend.projectId = project.id;
    state.backend.connected = false;
    state.backend.lastError = error.message || String(error);
    appendBackendError(state, error);
    state.voiceStatus = "后端不可用，已创建本地空白项目";
    pushEvent({
      type: "PROJECT_CREATED",
      sessionId: state.session.id,
      projectId: project.id,
      message: "已创建本地空白项目"
    });
  } finally {
    setBusy(false);
  }
}

function openProjectFilePicker() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,.voicecanvas.json,application/json";
  input.addEventListener(
    "change",
    async () => {
      const file = input.files?.[0];
      if (file) await loadProjectFromFile(file);
    },
    { once: true }
  );
  input.click();
}

async function loadProjectFromFile(file) {
  try {
    const imported = await importProjectFile(file);
    try {
      const response = await importProjectState(imported.payload);
      applyBackendResponse(state, response);
      state.backend.projectId = response.project.id;
      state.backend.connected = true;
      state.backend.lastError = null;
    } catch (error) {
      state.project = structuredClone(imported.project);
      state.history = [];
      state.backend.connected = false;
      state.backend.lastError = error.message || String(error);
    }
    state.voiceStatus = "项目已载入";
    pushEvent({
      type: "PROJECT_IMPORTED",
      sessionId: state.session.id,
      projectId: state.project.id,
      message: "项目已载入"
    });
  } catch (error) {
    appendBackendError(state, error);
  }

  render();
}

function runCustomInput() {
  const input = $("#voiceInput").value.trim();
  if (!input) return;

  let fallback = runStoryboardDemoLocal;
  if (input.includes("箭头")) {
    fallback = runArrowDemoLocal;
  } else if (input.includes("标题") || input.includes("它")) {
    fallback = runClarificationDemoLocal;
  } else if (input.includes("导出")) {
    fallback = runExportDemoLocal;
  }

  runBackendInput(input, fallback);
}

function startVoiceRecording() {
  getVoiceController().start();
}

function finishVoiceRecording() {
  getVoiceController().stop();
}

function runVoiceInputDemo() {
  if (getVoiceController().isActive()) {
    finishVoiceRecording();
    return;
  }

  startVoiceRecording();
}

function getVoiceController() {
  if (voiceController) return voiceController;

  voiceController = new VoiceSessionController({
    recognition: new BrowserSpeechRecognitionAdapter(),
    feedback: new BrowserVoiceFeedbackAdapter(),
    submitTranscript: handleVoiceTranscript,
    onStatusChange: (message) => {
      state.voiceStatus = message;
      state.voiceSessionActive = Boolean(voiceController?.isActive());
      render();
    },
    onListeningChange: (isListening) => {
      state.voiceSessionActive = getVoiceController().isActive();
      state.voiceListening = isListening;
      state.voiceRecording = isListening ? { sessionId: state.session.id } : null;
      if (isListening) {
        publishStage("listening", "持续语音监听中");
      }
      render();
    },
    onPartialTranscript: (text) => {
      const sessionId = state.session.id || makeId("session");
      state.session.currentUserInput = text;
      $("#voiceInput").value = text;
      pushEvent({
        type: "TRANSCRIPT_PARTIAL",
        sessionId,
        text
      });
      render();
    },
    onFinalTranscript: (text) => {
      const sessionId = state.session.id || makeId("session");
      $("#voiceInput").value = text;
      state.session.currentUserInput = text;
      pushEvent({
        type: "TRANSCRIPT_FINAL",
        sessionId,
        text
      });
      render();
    }
  });
  return voiceController;
}

function switchScene(sceneId) {
  const scene = state.project.scenes.find((item) => item.id === sceneId);
  if (!scene) return;

  const displayNumber = sceneDisplayNumber(state.project.scenes, sceneId) || scene.order;
  const orderText = ["零", "一", "二", "三", "四", "五"][displayNumber] || String(displayNumber);
  runBackendInput(`切换到第${orderText}镜头`, () => switchSceneLocal(sceneId));
}

function switchSceneLocal(sceneId) {
  executeCommand({
    id: makeId("cmd"),
    type: "SWITCH_SCENE",
    source: "user_ui",
    reason: "用户从镜头历史区选择",
    createdAt: nowIso(),
    payload: { sceneId }
  });
  render();
}

function selectElement(elementId) {
  state.selectedElementId = elementId;
  render();
}

async function openMemoryPanel() {
  state.settingsOpen = false;
  state.memory.panelOpen = true;
  state.memory.error = null;
  render();
  await refreshUserMemories();
}

function closeMemoryPanel() {
  state.memory.panelOpen = false;
  state.memory.editingId = null;
  state.memory.error = null;
  render();
}

async function refreshUserMemories() {
  state.memory.loading = true;
  state.memory.error = null;
  render();

  try {
    const response = await listUserMemories(DEFAULT_USER_ID, true);
    state.memory.memories = response?.memories || [];
  } catch (error) {
    state.memory.error = error.message || "长期记忆加载失败";
  } finally {
    state.memory.loading = false;
    render();
  }
}

async function createMemoryFromPanel() {
  const content = $("#memoryContentInput").value.trim();
  if (!content) {
    state.memory.error = "请先填写长期记忆内容";
    renderMemoryPanel();
    return;
  }

  state.memory.loading = true;
  state.memory.error = null;
  renderMemoryPanel();

  try {
    await createUserMemory(DEFAULT_USER_ID, {
      kind: $("#memoryKindInput").value,
      content,
      scope: $("#memoryScopeInput").value
    });
    $("#memoryContentInput").value = "";
    await refreshUserMemories();
  } catch (error) {
    state.memory.error = error.message || "长期记忆新增失败";
    state.memory.loading = false;
    renderMemoryPanel();
  }
}

function startMemoryEdit(memoryId) {
  state.memory.editingId = memoryId;
  state.memory.error = null;
  renderMemoryPanel();
}

function cancelMemoryEdit() {
  state.memory.editingId = null;
  state.memory.error = null;
  renderMemoryPanel();
}

async function saveMemoryEdit(memoryId) {
  const row = document.querySelector(`[data-memory-row="${CSS.escape(memoryId)}"]`);
  if (!row) return;

  const content = row.querySelector("[data-memory-edit='content']").value.trim();
  if (!content) {
    state.memory.error = "长期记忆内容不能为空";
    renderMemoryPanel();
    return;
  }

  state.memory.loading = true;
  state.memory.error = null;
  renderMemoryPanel();

  try {
    await updateUserMemory(memoryId, {
      kind: row.querySelector("[data-memory-edit='kind']").value,
      content,
      scope: row.querySelector("[data-memory-edit='scope']").value
    });
    state.memory.editingId = null;
    await refreshUserMemories();
  } catch (error) {
    state.memory.error = error.message || "长期记忆保存失败";
    state.memory.loading = false;
    renderMemoryPanel();
  }
}

async function updateMemoryStatus(memoryId, status) {
  state.memory.loading = true;
  state.memory.error = null;
  renderMemoryPanel();

  try {
    await updateUserMemory(memoryId, { status });
    await refreshUserMemories();
  } catch (error) {
    state.memory.error = error.message || "长期记忆状态更新失败";
    state.memory.loading = false;
    renderMemoryPanel();
  }
}

async function deleteMemoryFromPanel(memoryId) {
  const confirmed = window.confirm("确定删除这条长期记忆吗？删除后无法恢复。");
  if (!confirmed) return;

  state.memory.loading = true;
  state.memory.error = null;
  renderMemoryPanel();

  try {
    await deleteUserMemory(memoryId);
    if (state.memory.editingId === memoryId) state.memory.editingId = null;
    await refreshUserMemories();
  } catch (error) {
    state.memory.error = error.message || "长期记忆删除失败";
    state.memory.loading = false;
    renderMemoryPanel();
  }
}

function render() {
  renderHeader();
  renderHistory();
  renderCanvas();
  renderAIPanel();
  renderMemoryPanel();
}

function renderHeader() {
  $("#projectTitle").textContent = state.project.title;
  $("#projectMeta").textContent = `${state.project.mode} · ${state.project.scenes.length} 个镜头 · ${stageLabels[state.session.stage] || state.session.stage}`;
  $("#settingsButton").setAttribute("aria-expanded", String(state.settingsOpen));
  $("#settingsMenu").hidden = !state.settingsOpen;
}

function renderMemoryPanel() {
  const overlay = $("#memoryOverlay");
  if (!overlay) return;

  overlay.hidden = !state.memory.panelOpen;
  renderMemorySelectOptions();

  const error = $("#memoryError");
  error.hidden = !state.memory.error;
  error.textContent = state.memory.error || "";

  const list = $("#memoryList");
  if (state.memory.loading && !state.memory.memories.length) {
    list.innerHTML = `<p class="memory-empty">正在读取长期记忆...</p>`;
    return;
  }

  if (!state.memory.memories.length) {
    list.innerHTML = `<p class="memory-empty">暂无长期记忆</p>`;
    return;
  }

  list.innerHTML = state.memory.memories.map(renderMemoryItem).join("");
}

function renderMemorySelectOptions() {
  const kindInput = $("#memoryKindInput");
  const scopeInput = $("#memoryScopeInput");
  if (!kindInput || !scopeInput) return;

  kindInput.innerHTML = renderOptions(memoryKindLabels, "style_preference");
  scopeInput.innerHTML = renderOptions(memoryScopeLabels, "global");
}

function renderOptions(labels, selectedValue) {
  return Object.entries(labels)
    .map(([value, label]) => {
      const selected = value === selectedValue ? " selected" : "";
      return `<option value="${escapeAttribute(value)}"${selected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function renderMemoryItem(memory) {
  if (state.memory.editingId === memory.id) return renderEditableMemoryItem(memory);

  return `
    <article class="memory-item" data-memory-row="${escapeAttribute(memory.id)}" data-status="${escapeAttribute(memory.status)}">
      <div class="memory-item-main">
        <p>${escapeHtml(memory.content)}</p>
        <div class="memory-meta">
          <span>${escapeHtml(memoryKindLabels[memory.kind] || memory.kind)}</span>
          <span>${escapeHtml(memoryScopeLabels[memory.scope] || memory.scope)}</span>
          <span>${escapeHtml(memoryStatusLabels[memory.status] || memory.status)}</span>
          <span>${formatDateTime(memory.updatedAt)}</span>
        </div>
      </div>
      <div class="memory-actions">
        ${renderMemoryStatusActions(memory)}
        <button type="button" data-memory-action="edit" data-memory-id="${escapeAttribute(memory.id)}">编辑</button>
        <button type="button" data-memory-action="delete" data-memory-id="${escapeAttribute(memory.id)}">删除</button>
      </div>
    </article>
  `;
}

function renderEditableMemoryItem(memory) {
  return `
    <article class="memory-item is-editing" data-memory-row="${escapeAttribute(memory.id)}" data-status="${escapeAttribute(memory.status)}">
      <textarea data-memory-edit="content" rows="3">${escapeHtml(memory.content)}</textarea>
      <div class="memory-form-row">
        <label>
          类型
          <select data-memory-edit="kind">${renderOptions(memoryKindLabels, memory.kind)}</select>
        </label>
        <label>
          范围
          <select data-memory-edit="scope">${renderOptions(memoryScopeLabels, memory.scope)}</select>
        </label>
      </div>
      <div class="memory-actions">
        <button type="button" data-memory-action="save" data-memory-id="${escapeAttribute(memory.id)}">保存</button>
        <button type="button" data-memory-action="cancel-edit">取消</button>
      </div>
    </article>
  `;
}

function renderMemoryStatusActions(memory) {
  if (memory.status === "candidate") {
    return `
      <button type="button" data-memory-action="status" data-memory-id="${escapeAttribute(memory.id)}" data-memory-status="active">激活</button>
      <button type="button" data-memory-action="status" data-memory-id="${escapeAttribute(memory.id)}" data-memory-status="rejected">拒绝</button>
    `;
  }
  if (memory.status === "active") {
    return `<button type="button" data-memory-action="status" data-memory-id="${escapeAttribute(memory.id)}" data-memory-status="archived">归档</button>`;
  }
  if (memory.status === "archived" || memory.status === "rejected") {
    return `<button type="button" data-memory-action="status" data-memory-id="${escapeAttribute(memory.id)}" data-memory-status="active">重新激活</button>`;
  }
  return "";
}

function formatDateTime(value) {
  if (!value) return "未更新";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function renderHistory() {
  const sceneList = $("#sceneList");
  sceneList.innerHTML = visibleSceneEntries(state.project.scenes)
    .map(({ scene, displayNumber }) => {
      const active = scene.id === state.project.activeSceneId ? "is-active" : "";
      return `
        <button class="scene-row ${active}" data-scene="${scene.id}">
          <span class="scene-order">${displayNumber}</span>
          <span>
            <strong>${scene.name}</strong>
            <small>${scene.description}</small>
          </span>
        </button>
      `;
    })
    .join("");

  const timeline = $("#operationTimeline");
  timeline.innerHTML = state.history
    .slice()
    .reverse()
    .slice(0, 8)
    .map((entry) => `
      <li>
        <span>${commandSummaries[entry.command.type] || entry.command.type}</span>
        <strong>${entry.summary}</strong>
      </li>
    `)
    .join("");

  $("#undoState").textContent = state.history.length > 0 ? "可撤销上一条命令" : "暂无可撤销命令";
}

function renderCanvas() {
  const scene = activeScene();
  $("#activeSceneName").textContent = scene.name;
  $("#activeSceneDescription").textContent = scene.description || "当前镜头由后端 Project State 驱动";
  $("#activeSceneNarration").textContent = scene.narration || "等待旁白";
  $("#sceneDuration").textContent = scene.durationMs ? `${(scene.durationMs / 1000).toFixed(1)}s` : "未设置";

  const canvas = $("#canvasSurface");
  canvas.style.background = scene.canvas?.background?.type === "solid" ? scene.canvas.background.color : "#ffffff";
  const elements = scene.elements
    .slice()
    .sort((left, right) => getLayer(left).zIndex - getLayer(right).zIndex);
  const layoutIndex = createElementLayoutIndex(scene);
  canvas.innerHTML = [
    ...elements.filter((element) => element.type !== "connector").map(renderElement),
    renderConnectorLayer(scene, elements, layoutIndex)
  ].join("");
}

function createElementLayoutIndex(scene) {
  return Object.fromEntries(
    scene.elements.map((element) => {
      const transform = getTransform(element);
      return [
        element.id,
        {
          id: element.id,
          bounds: transform,
          connectableAnchors: ["top", "right", "bottom", "left", "center"]
        }
      ];
    })
  );
}

function renderElement(element) {
  if (element.type === "text") return renderTextElement(element);
  if (element.type === "shape") return renderShapeElement(element);
  if (element.type === "image") return renderImageElement(element);
  if (element.type === "generated_asset") return renderGeneratedAssetElement(element);
  if (element.type === "group") return renderGroupElement(element);
  return renderUnknownElement(element);
}

function renderTextElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const text = getTextElementContent(element);
  return `<button class="canvas-element text-element ${selected}" data-element="${element.id}" style="${elementBoxStyle(element)};${textElementStyle(element, text)}">${escapeHtml(text)}</button>`;
}

function renderShapeElement(element) {
  const illustration = renderSemanticIllustrationElement(element);
  if (illustration) return illustration;

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const fill = resolvePaint(element.style?.fill, "#ffffff");
  const stroke = resolveStroke(element.style?.stroke, element.style?.strokeWidth, "#243b53");
  const shapeStyle = [
    `background:${fill}`,
    `border:${stroke.width}px solid ${stroke.color}`,
    `border-radius:${getShapeRadius(element)}px`
  ].join(";");
  const label = getContent(element).label || element.label || "";
  return `
    <button class="canvas-element shape-element ${selected}" data-shape="${getShapeKind(element)}" data-element="${element.id}" style="${elementBoxStyle(element)};${shapeStyle}">
      ${label ? `<span>${escapeHtml(label)}</span>` : ""}
    </button>
  `;
}

function renderImageElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const content = getContent(element);
  const radius = element.style?.radius ?? element.style?.borderRadius ?? 8;
  return `
    <button class="canvas-element image-element ${selected}" data-element="${element.id}" style="${elementBoxStyle(element)};border-radius:${radius}px">
      ${content.url ? `<img src="${escapeAttribute(content.url)}" alt="${escapeAttribute(content.alt || element.name || "")}">` : `<span>${escapeHtml(content.alt || element.name || "图片")}</span>`}
    </button>
  `;
}

function renderGeneratedAssetElement(element) {
  const catalogAsset = resolveCatalogAssetForElement(element);
  if (catalogAsset) {
    return renderCatalogAssetElement(element, catalogAsset);
  }

  const illustration = renderSemanticIllustrationElement(element);
  if (illustration) return illustration;

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const content = getContent(element);
  const status = element.asset?.status || "pending";
  if (status === "ready" && content.url) {
    return `
      <button class="canvas-element generated-asset-element ${selected}" data-element="${element.id}" data-status="ready" style="${elementBoxStyle(element)}">
        <img src="${escapeAttribute(content.url)}" alt="${escapeAttribute(content.alt || element.name || "")}">
      </button>
    `;
  }

  const placeholderStyle = [
    `background:${element.placeholderStyle?.fill || "#ffffff"}`,
    `border:${element.placeholderStyle?.strokeWidth || 1}px dashed ${element.placeholderStyle?.stroke || "#243b53"}`,
    `border-radius:${element.placeholderStyle?.radius || 8}px`
  ].join(";");
  return `
    <button class="canvas-element generated-asset-element ${selected}" data-element="${element.id}" data-status="${status}" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(element.name || element.asset?.kind || "生成素材")}</span>
    </button>
  `;
}

function renderCatalogAssetElement(element, catalogAsset) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const content = getContent(element);
  const status = catalogAsset.status;
  const label = content.alt || element.name || catalogAsset.displayName || "素材";
  if (status === "ready" && catalogAsset.url) {
    return `
      <button class="canvas-element generated-asset-element ${selected}" data-element="${element.id}" data-status="ready" data-asset-provider="minio" style="${elementBoxStyle(element)}">
        <img src="${escapeAttribute(catalogAsset.url)}" alt="${escapeAttribute(label)}" data-asset-path="${escapeAttribute(catalogAsset.path)}" loading="lazy">
      </button>
    `;
  }

  const placeholderStyle = [
    `background:${element.placeholderStyle?.fill || "#ffffff"}`,
    `border:${element.placeholderStyle?.strokeWidth || 1}px dashed ${element.placeholderStyle?.stroke || "#243b53"}`,
    `border-radius:${element.placeholderStyle?.radius || 8}px`
  ].join(";");
  const message = status === "failed" ? `${label} 素材加载失败` : `${label} 素材加载中`;
  return `
    <button class="canvas-element generated-asset-element ${selected}" data-element="${element.id}" data-status="${status}" data-asset-provider="minio" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(message)}</span>
    </button>
  `;
}

function renderGroupElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  return `
    <button class="canvas-element group-element ${selected}" data-element="${element.id}" style="${elementBoxStyle(element)}">
      <span>${escapeHtml(element.name || "组合")}</span>
    </button>
  `;
}

function renderUnknownElement(element) {
  const illustration = renderSemanticIllustrationElement(element);
  if (illustration) return illustration;

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const placeholderStyle = [
    `background:${element.placeholderStyle?.fill || "#ffffff"}`,
    `border:${element.placeholderStyle?.strokeWidth || 1}px dashed ${element.placeholderStyle?.stroke || "#243b53"}`,
    `border-radius:${element.placeholderStyle?.radius || 8}px`
  ].join(";");
  return `
    <button class="canvas-element unknown-element ${selected}" data-element="${element.id}" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(element.label || element.name || "未知元素")}</span>
    </button>
  `;
}

function renderSemanticIllustrationElement(element) {
  const spec = semanticIllustrationSpec(element);
  if (!spec) return "";

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const label = getElementLabel(element);
  return `
    <button class="canvas-element illustration-element ${selected}" data-illustration="${spec.renderKey || spec.kind}" data-variant="${spec.variant || ""}" data-element="${element.id}" style="${elementBoxStyle(element)}">
      ${renderIllustrationSvg(spec, label)}
    </button>
  `;
}

function semanticIllustrationSpec(element) {
  return semanticSpecFromCatalog(element);

  const renderHint = element.metadata?.renderHint;
  if (renderHint === "character" || renderHint === "girl") {
    return { kind: "character", variant: normalizeCharacterVariant(element.metadata?.renderVariant || (renderHint === "girl" ? "female" : "")) };
  }
  if (["cat", "table"].includes(renderHint)) return { kind: renderHint };

  const subjectSpec = semanticSpecFromSubject(element.subject);
  if (subjectSpec) return subjectSpec;

  const declaredText = [
    element.name,
    element.text,
    element.label,
    getContent(element).label,
    getContent(element).alt,
    element.asset?.kind,
    ...(element.semantic?.tags || [])
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return semanticSpecFromText(declaredText);
}

function semanticSpecFromCatalog(element) {
  const metadata = element.metadata || {};
  const explicitRenderKey = metadata.renderKey || metadata.renderHint;
  const explicitSpec = catalogSpecFromRenderKey(explicitRenderKey, metadata.renderVariant);
  if (explicitSpec) return explicitSpec;

  const subjectSpec = catalogSpecFromSubject(element.subject);
  if (subjectSpec) return subjectSpec;

  const declaredText = [
    element.name,
    element.text,
    element.label,
    getContent(element).label,
    getContent(element).alt,
    element.asset?.kind,
    ...(element.semantic?.tags || [])
  ]
    .filter(Boolean)
    .join(" ");
  return catalogSpecFromText(declaredText);
}

function resolveCatalogAssetForElement(element) {
  const catalogItem = catalogItemForElement(element);
  const assetPath = element.metadata?.assetPath || catalogItem?.assetPath;
  if (!assetPath) return null;

  if (catalogAssetState.urls.has(assetPath)) {
    return {
      path: assetPath,
      displayName: catalogItem?.displayName,
      url: catalogAssetState.urls.get(assetPath),
      status: "ready"
    };
  }
  if (catalogAssetState.failed.has(assetPath)) {
    return {
      path: assetPath,
      displayName: catalogItem?.displayName,
      url: null,
      status: "failed"
    };
  }

  loadCatalogAssetUrl(assetPath);
  return {
    path: assetPath,
    displayName: catalogItem?.displayName,
    url: null,
    status: "loading"
  };
}

function catalogItemForElement(element) {
  const metadata = element.metadata || {};
  const explicitKey = metadata.renderKey || metadata.renderHint;
  if (explicitKey && renderCatalogState.byKey.has(explicitKey)) {
    return renderCatalogState.byKey.get(explicitKey);
  }

  const subjectItem = catalogItemFromSubject(element.subject);
  if (subjectItem) return subjectItem;

  const text = [
    element.name,
    element.text,
    element.label,
    getContent(element).label,
    getContent(element).alt,
    element.asset?.kind,
    ...(element.semantic?.tags || [])
  ]
    .filter(Boolean)
    .join(" ");
  return catalogItemFromText(text);
}

function catalogItemFromSubject(subject) {
  if (!subject || typeof subject !== "object") return null;
  for (const subjectValue of Object.values(subject)) {
    if (!subjectValue || typeof subjectValue !== "object") continue;
    if (subjectValue.renderKey && renderCatalogState.byKey.has(subjectValue.renderKey)) {
      return renderCatalogState.byKey.get(subjectValue.renderKey);
    }
    const text = [
      subjectValue.category,
      subjectValue.role,
      subjectValue.gender,
      subjectValue.variant,
      ...(subjectValue.keyFeatures || [])
    ]
      .filter(Boolean)
      .join(" ");
    const textItem = catalogItemFromText(text);
    if (textItem) return textItem;
  }
  return null;
}

function catalogItemFromText(text) {
  const normalizedText = normalizeCatalogText(text);
  if (!normalizedText) return null;

  let bestRule = null;
  let bestScore = 0;
  for (const rule of renderCatalogState.aliasRules) {
    const alias = normalizeCatalogText(rule.alias);
    if (!alias) continue;
    const score = alias === normalizedText ? 1000 + alias.length : normalizedText.includes(alias) ? 100 + alias.length : 0;
    if (score > bestScore) {
      bestScore = score;
      bestRule = rule;
    }
  }
  return bestRule ? renderCatalogState.byKey.get(bestRule.renderKey) || null : null;
}

async function loadCatalogAssetUrl(assetPath) {
  if (catalogAssetState.pending.has(assetPath)) return;
  catalogAssetState.pending.add(assetPath);
  try {
    const asset = await resolveCatalogAssetUrl(assetPath);
    catalogAssetState.urls.set(assetPath, asset.url);
    catalogAssetState.failed.delete(assetPath);
  } catch (error) {
    console.warn("Catalog 素材解析失败，使用占位渲染", error);
    catalogAssetState.failed.add(assetPath);
  } finally {
    catalogAssetState.pending.delete(assetPath);
    render();
  }
}

function catalogSpecFromSubject(subject) {
  if (!subject || typeof subject !== "object") return null;
  for (const subjectValue of Object.values(subject)) {
    if (!subjectValue || typeof subjectValue !== "object") continue;
    const explicitSpec = catalogSpecFromRenderKey(subjectValue.renderKey, subjectValue.variant || subjectValue.gender);
    if (explicitSpec) return explicitSpec;
    const text = [
      subjectValue.category,
      subjectValue.role,
      subjectValue.gender,
      subjectValue.variant,
      ...(subjectValue.keyFeatures || [])
    ]
      .filter(Boolean)
      .join(" ");
    const textSpec = catalogSpecFromText(text);
    if (textSpec) return textSpec;
  }
  return null;
}

function catalogSpecFromRenderKey(renderKey, variant) {
  if (!renderKey) return null;
  const normalizedKey = renderKey === "girl" ? "character" : renderKey;
  const item = renderCatalogState.byKey.get(normalizedKey);
  if (!item || !item.directRender || !getIllustrationRenderer(item.renderKey)) return null;
  return {
    renderKey: item.renderKey,
    kind: item.renderKey,
    variant: normalizeCatalogVariant(item, variant || (renderKey === "girl" ? "female" : null))
  };
}

function catalogSpecFromText(text) {
  const normalizedText = normalizeCatalogText(text);
  if (!normalizedText) return null;

  let bestRule = null;
  let bestScore = 0;
  for (const rule of renderCatalogState.aliasRules) {
    const alias = normalizeCatalogText(rule.alias);
    if (!alias) continue;
    const score = alias === normalizedText ? 1000 + alias.length : normalizedText.includes(alias) ? 100 + alias.length : 0;
    if (score > bestScore) {
      bestScore = score;
      bestRule = rule;
    }
  }
  if (!bestRule) return null;
  return catalogSpecFromRenderKey(bestRule.renderKey, bestRule.variant);
}

function normalizeCatalogText(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeCatalogVariant(item, variant) {
  if (!variant) return item.renderKey === "character" ? "neutral" : "";
  const normalizedVariant = item.renderKey === "character" ? normalizeCharacterVariant(variant) : String(variant);
  const variants = item.variants || [];
  if (!variants.length) return normalizedVariant;
  return variants.some((entry) => entry.key === normalizedVariant) ? normalizedVariant : variants[0]?.key || "";
}

function semanticSpecFromSubject(subject) {
  if (!subject || typeof subject !== "object") return null;
  const character = subject.character;
  if (character && typeof character === "object") {
    const text = [character.category, character.role, character.gender, ...(character.keyFeatures || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return semanticSpecFromText(text) || { kind: "character", variant: normalizeCharacterVariant(character.gender) };
  }
  const product = subject.product;
  if (product && typeof product === "object") {
    const text = [product.category, product.brand, ...(product.keyFeatures || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return semanticSpecFromText(text);
  }
  return null;
}

function semanticSpecFromText(text) {
  if (text.includes("男生") || text.includes("男孩") || text.includes("男人") || text.includes("男性") || text.includes("boy") || text.includes("man")) {
    return { kind: "character", variant: "male" };
  }
  if (text.includes("女生") || text.includes("女孩") || text.includes("女人") || text.includes("女性") || text.includes("girl") || text.includes("woman")) {
    return { kind: "character", variant: "female" };
  }
  if (text.includes("人物") || text.includes("人像") || text.includes("person") || text.includes("character")) {
    return { kind: "character", variant: "neutral" };
  }
  if (text.includes("猫") || text.includes("cat") || text.includes("小猫")) return { kind: "cat" };
  if (text.includes("桌") || text.includes("table") || text.includes("desk")) return { kind: "table" };
  return null;
}

function normalizeCharacterVariant(value) {
  if (value === "male" || value === "男" || value === "男生" || value === "男性") return "male";
  if (value === "female" || value === "女" || value === "女生" || value === "女性") return "female";
  return "neutral";
}

function getElementLabel(element) {
  return getContent(element).label || getContent(element).alt || element.label || element.name || "";
}

function catIllustrationSvg(label) {
  return `
    <svg class="object-illustration cat-illustration" viewBox="0 0 240 180" role="img" aria-label="${escapeAttribute(label || "猫")}">
      <ellipse class="cat-shadow" cx="126" cy="154" rx="78" ry="12"></ellipse>
      <path class="cat-tail" d="M178 116 C218 92 216 48 181 54 C163 57 163 83 181 84"></path>
      <ellipse class="cat-body" cx="124" cy="112" rx="58" ry="42"></ellipse>
      <circle class="cat-head" cx="92" cy="74" r="38"></circle>
      <path class="cat-ear" d="M63 49 L66 12 L91 42 Z"></path>
      <path class="cat-ear" d="M100 41 L129 16 L127 54 Z"></path>
      <circle class="cat-eye" cx="80" cy="72" r="4"></circle>
      <circle class="cat-eye" cx="104" cy="72" r="4"></circle>
      <path class="cat-nose" d="M90 82 L96 82 L93 87 Z"></path>
      <path class="cat-mouth" d="M93 88 C88 94 80 94 76 90 M93 88 C98 94 106 94 110 90"></path>
      <path class="cat-whisker" d="M60 79 L22 70 M61 88 L23 91 M124 79 L160 68 M123 88 L160 92"></path>
      <path class="cat-leg" d="M91 142 L87 164 M123 146 L123 166 M153 142 L159 164"></path>
    </svg>
  `;
}

function renderIllustrationSvg(spec, label) {
  const renderer = getIllustrationRenderer(spec.renderKey || spec.kind);
  return renderer ? renderer(label, spec) : "";
}

function getIllustrationRenderer(renderKey) {
  const renderers = {
    character: (label, spec) => characterIllustrationSvg(label, spec.variant),
    cat: (label) => catIllustrationSvg(label),
    table: (label) => tableIllustrationSvg(label)
  };
  return renderers[renderKey] || null;
}

function characterIllustrationSvg(label, variant = "neutral") {
  const normalizedVariant = normalizeCharacterVariant(variant);
  const isFemale = normalizedVariant === "female";
  const isMale = normalizedVariant === "male";
  return `
    <svg class="object-illustration character-illustration is-${normalizedVariant}" viewBox="0 0 220 220" role="img" aria-label="${escapeAttribute(label || "人物")}">
      <ellipse class="character-shadow" cx="110" cy="198" rx="56" ry="10"></ellipse>
      <path class="character-hair-back" d="${isFemale ? "M61 85 C56 41 82 18 111 18 C146 18 166 45 159 91 C155 119 66 118 61 85 Z" : "M70 67 C73 35 91 21 111 21 C139 21 153 40 150 70 C130 53 94 51 70 67 Z"}"></path>
      <circle class="character-face" cx="110" cy="75" r="39"></circle>
      <path class="character-hair-front" d="${isFemale ? "M73 64 C83 34 121 25 148 55 C130 50 113 48 92 61 C85 66 79 68 73 64 Z" : "M73 61 C89 35 125 34 149 59 C130 55 105 54 83 68 Z"}"></path>
      <circle class="character-eye" cx="97" cy="78" r="4"></circle>
      <circle class="character-eye" cx="123" cy="78" r="4"></circle>
      <path class="character-smile" d="M99 93 C106 101 117 101 124 93"></path>
      <path class="character-neck" d="M101 112 H119 L123 130 H97 Z"></path>
      ${isFemale ? `<path class="character-dress" d="M84 128 H136 L154 190 H66 Z"></path>` : `<path class="character-shirt" d="M78 128 H142 L150 188 H70 Z"></path><path class="character-pants" d="M86 188 H134 L128 211 H114 L110 195 L106 211 H92 Z"></path>`}
      <path class="character-arm" d="M84 137 C61 148 56 165 66 177 M136 137 C160 148 165 165 154 177"></path>
      ${isFemale ? `<path class="character-leg" d="M94 190 L88 211 M126 190 L132 211"></path>` : ""}
      <path class="character-shoe" d="M78 211 H94 M126 211 H142"></path>
    </svg>
  `;
}

function tableIllustrationSvg(label) {
  return `
    <svg class="object-illustration table-illustration" viewBox="0 0 260 180" role="img" aria-label="${escapeAttribute(label || "桌子")}">
      <ellipse class="table-shadow" cx="132" cy="160" rx="92" ry="10"></ellipse>
      <path class="table-top" d="M42 55 C44 43 55 36 70 36 H190 C207 36 218 44 220 58 L228 92 H34 Z"></path>
      <path class="table-front" d="M34 92 H228 L213 112 H49 Z"></path>
      <path class="table-leg" d="M63 109 H83 L76 158 H55 Z"></path>
      <path class="table-leg" d="M177 109 H198 L207 158 H186 Z"></path>
      <path class="table-grain" d="M66 62 H195 M74 78 H184"></path>
      <rect class="table-object" x="112" y="18" width="38" height="32" rx="8"></rect>
    </svg>
  `;
}

function renderConnectorLayer(scene, elements, layoutIndex) {
  const connectors = elements.filter((element) => element.type === "connector");
  return `
    <svg class="connector-layer" viewBox="0 0 ${scene.canvas.width} ${scene.canvas.height}" aria-hidden="true">
      <defs>
        ${connectors.map(renderConnectorMarker).join("")}
      </defs>
      ${connectors.map((element) => renderConnectorElement(element, layoutIndex)).join("")}
    </svg>
  `;
}

function renderConnectorElement(element, layoutIndex) {
  const connector = getConnectorConfig(element);
  const from = resolveEndpoint(connector.from, connector.to, layoutIndex);
  const to = resolveEndpoint(connector.to, connector.from, layoutIndex);
  if (!from || !to) return "";

  const stroke = resolveStroke(element.style?.stroke, element.style?.strokeWidth, "#f15b4a");
  const markerEnd = getMarkerEnd(element) ? `marker-end="url(#${connectorMarkerId(element)})"` : "";
  const dash = Array.isArray(stroke.dash) ? `stroke-dasharray="${stroke.dash.join(" ")}"` : "";
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const label = getContent(element).label || element.text || "";
  const labelPoint = pointOnConnectorLabel(from, to, connector);

  return `
    <g class="connector-item ${selected}" data-element="${element.id}">
      <path d="${buildConnectorPath(from, to, connector)}" fill="none" stroke="${escapeAttribute(stroke.color)}" stroke-width="${stroke.width}" stroke-linecap="round" stroke-linejoin="round" ${dash} ${markerEnd}></path>
      ${label ? `<text x="${labelPoint.x}" y="${labelPoint.y}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
    </g>
  `;
}

function renderConnectorMarker(element) {
  const stroke = resolveStroke(element.style?.stroke, element.style?.strokeWidth, "#f15b4a");
  const size = element.style?.markerEnd?.size || 8;
  return `
    <marker id="${connectorMarkerId(element)}" markerWidth="${size}" markerHeight="${size}" refX="${size - 1}" refY="${size / 2}" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L${size},${size / 2} L0,${size} Z" fill="${escapeAttribute(element.style?.markerEnd?.fill || stroke.color)}"></path>
    </marker>
  `;
}

function connectorMarkerId(element) {
  return `arrow-${element.id}`;
}

function getMarkerEnd(element) {
  if (element.style?.markerEnd?.type === "none") return false;
  return element.style?.arrowEnd !== false;
}

function buildConnectorPath(from, to, connector) {
  const routing = connector.routing || (connector.kind === "curve" ? "bezier" : "straight");
  if (routing === "bezier" || connector.kind === "curve") {
    const delta = Math.max(48, Math.abs(to.x - from.x) * 0.36);
    return `M ${from.x} ${from.y} C ${from.x + delta} ${from.y}, ${to.x - delta} ${to.y}, ${to.x} ${to.y}`;
  }

  if (routing === "orthogonal" || connector.kind === "elbow") {
    const midX = (from.x + to.x) / 2;
    return `M ${from.x} ${from.y} L ${midX} ${from.y} L ${midX} ${to.y} L ${to.x} ${to.y}`;
  }

  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

function pointOnConnectorLabel(from, to, connector) {
  if (connector.routing === "orthogonal" || connector.kind === "elbow") {
    return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 10 };
  }
  return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 12 };
}

function resolveEndpoint(endpoint, oppositeEndpoint, layoutIndex) {
  if (!endpoint) return null;
  const target = endpoint.target || (endpoint.elementId ? { type: "element", elementId: endpoint.elementId } : null);
  if (!target) return null;
  if (target.type === "point") return target.point;

  const layout = layoutIndex[target.elementId];
  if (!layout) return null;
  const opposite = oppositeEndpoint ? resolveEndpointCenter(oppositeEndpoint, layoutIndex) : null;
  return anchorPoint(layout.bounds, endpoint.anchor || "auto", opposite);
}

function resolveEndpointCenter(endpoint, layoutIndex) {
  const target = endpoint.target || (endpoint.elementId ? { type: "element", elementId: endpoint.elementId } : null);
  if (!target) return null;
  if (target.type === "point") return target.point;
  const layout = layoutIndex[target.elementId];
  if (!layout) return null;
  return {
    x: layout.bounds.x + layout.bounds.width / 2,
    y: layout.bounds.y + layout.bounds.height / 2
  };
}

function anchorPoint(bounds, anchor, opposite) {
  const normalized = normalizeAnchor(anchor, bounds, opposite);
  if (typeof normalized === "object") {
    const ratio = Math.min(1, Math.max(0, normalized.ratio ?? 0.5));
    if (normalized.side === "top") return { x: bounds.x + bounds.width * ratio, y: bounds.y };
    if (normalized.side === "right") return { x: bounds.x + bounds.width, y: bounds.y + bounds.height * ratio };
    if (normalized.side === "bottom") return { x: bounds.x + bounds.width * ratio, y: bounds.y + bounds.height };
    return { x: bounds.x, y: bounds.y + bounds.height * ratio };
  }

  if (normalized === "top") return { x: bounds.x + bounds.width / 2, y: bounds.y };
  if (normalized === "right") return { x: bounds.x + bounds.width, y: bounds.y + bounds.height / 2 };
  if (normalized === "bottom") return { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height };
  if (normalized === "left") return { x: bounds.x, y: bounds.y + bounds.height / 2 };
  return { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
}

function normalizeAnchor(anchor, bounds, opposite) {
  if (anchor !== "auto" || !opposite) return anchor;
  const center = {
    x: bounds.x + bounds.width / 2,
    y: bounds.y + bounds.height / 2
  };
  const dx = opposite.x - center.x;
  const dy = opposite.y - center.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "right" : "left";
  return dy >= 0 ? "bottom" : "top";
}

function getConnectorConfig(element) {
  if (element.connector) return element.connector;
  return {
    kind: element.connectorType || "line",
    from: normalizeLegacyEndpoint(element.from),
    to: normalizeLegacyEndpoint(element.to),
    routing: element.connectorType === "curve" ? "bezier" : "straight"
  };
}

function normalizeLegacyEndpoint(endpoint) {
  if (!endpoint || endpoint.target) return endpoint;
  return {
    target: { type: "element", elementId: endpoint.elementId },
    anchor: endpoint.anchor
  };
}

function elementBoxStyle(element) {
  const transform = getTransform(element);
  const layer = getLayer(element);
  return [
    `left:${scaleX(transform.x)}%`,
    `top:${scaleY(transform.y)}%`,
    `width:${scaleX(transform.width)}%`,
    `height:${scaleY(transform.height)}%`,
    `z-index:${layer.zIndex}`,
    transform.rotation ? `transform:rotate(${transform.rotation}deg)` : "",
    transform.opacity !== undefined ? `opacity:${transform.opacity}` : ""
  ]
    .filter(Boolean)
    .join(";");
}

function textElementStyle(element, text) {
  const baseFontSize = Math.max(12, getStyleNumber(element.style?.fontSize, 28) * 0.42);
  const fittedFontSize = fitTextFontSize({
    text,
    baseFontSize,
    transform: getTransform(element)
  });

  return [
    `font-size:${fittedFontSize}px`,
    `color:${element.style?.color || "#173b2c"}`,
    `background:${element.boxStyle?.fill?.color || element.style?.backgroundColor || "transparent"}`,
    `font-weight:${element.style?.fontWeight || "normal"}`,
    `text-align:${element.style?.align || "left"}`
  ].join(";");
}

function getTextElementContent(element) {
  const content = getContent(element);
  return content.text || element.text || "";
}

function getTransform(element) {
  return {
    x: element.transform?.x ?? element.x ?? 0,
    y: element.transform?.y ?? element.y ?? 0,
    width: element.transform?.width ?? element.width ?? 1,
    height: element.transform?.height ?? element.height ?? 1,
    rotation: element.transform?.rotation ?? element.rotation,
    opacity: element.transform?.opacity ?? element.opacity
  };
}

function getLayer(element) {
  return {
    zIndex: element.layer?.zIndex ?? element.zIndex ?? 0
  };
}

function getContent(element) {
  return element.content || {};
}

function getShapeKind(element) {
  return element.shape?.kind || element.shape || "rectangle";
}

function getShapeRadius(element) {
  return element.shape?.cornerRadius ?? element.style?.radius ?? (getShapeKind(element) === "circle" ? 999 : 8);
}

function resolvePaint(paint, fallback) {
  if (!paint) return fallback;
  if (typeof paint === "string") return paint;
  if (paint.type === "solid") return paint.color;
  if (paint.color) return paint.color;
  if (paint.type === "linear_gradient") {
    return `linear-gradient(${paint.angle || 90}deg, ${paint.from}, ${paint.to})`;
  }
  return fallback;
}

function resolveStroke(stroke, legacyWidth, fallbackColor) {
  if (typeof stroke === "string") {
    return { color: stroke, width: legacyWidth || 1 };
  }
  return {
    color: stroke?.color || fallbackColor,
    width: stroke?.width || legacyWidth || 1,
    dash: stroke?.dash
  };
}

function getStyleNumber(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function scaleX(value) {
  return (value / (activeScene()?.canvas?.width || 960)) * 100;
}

function scaleY(value) {
  return (value / (activeScene()?.canvas?.height || 540)) * 100;
}

function renderAIPanel() {
  $("#voiceStatus").textContent = state.voiceStatus;
  $("#voiceStatus").classList.toggle("is-ready", state.voiceDraftReady);
  const voiceButton = document.querySelector("[data-run='voice']");
  const voiceActive = Boolean(state.voiceSessionActive || state.voiceRecording);
  voiceButton?.setAttribute("aria-pressed", String(voiceActive));
  const voiceButtonLabel = voiceButton?.querySelector("strong");
  if (voiceButtonLabel) {
    voiceButtonLabel.textContent = voiceActive ? "结束创作" : "开始语音创作";
  }

  const stage = $("#stageIndicator");
  stage.dataset.stage = state.session.stage;
  stage.querySelector("strong").textContent = stageLabels[state.session.stage] || state.session.stage;
  stage.querySelector("span").textContent = state.session.progress?.message || "等待输入";

  const progress = state.session.progress || { completedSteps: 0, totalSteps: 0 };
  const percent = progress.totalSteps ? Math.round((progress.completedSteps / progress.totalSteps) * 100) : 0;
  $("#progressBar").style.width = `${percent}%`;
  $("#progressText").textContent = `${progress.completedSteps || 0}/${progress.totalSteps || 0}`;

  const clarification = $("#clarificationCard");
  if (state.session.pendingClarification) {
    clarification.hidden = false;
    clarification.querySelector("p").textContent = state.session.pendingClarification.question;
    clarification.querySelector(".option-list").innerHTML = state.session.pendingClarification.options
      .map((option) => `<button data-resume="${option.value}">${option.label}</button>`)
      .join("");
  } else {
    clarification.hidden = true;
  }

  const summary = $("#turnSummary");
  if (state.session.lastSummary?.changes?.length) {
    summary.innerHTML = state.session.lastSummary.changes
      .map((change) => `<li><span>${change.targetName || change.targetType}</span>${change.description}</li>`)
      .join("");
  } else if (state.session.lastSummary?.message) {
    summary.innerHTML = `<li><span>后端总结</span>${state.session.lastSummary.message}</li>`;
  } else {
    summary.innerHTML = "<li><span>待开始</span>暂无本轮变更</li>";
  }

  $("#eventLog").innerHTML = state.eventLog
    .map((event) => `
      <li>
        <span>${event.type}</span>
        <strong>${event.message || event.export?.filename || event.stage || event.question || event.patch?.type || event.text || "事件已接收"}</strong>
      </li>
    `)
    .join("");
}

function bindEvents() {
  const voiceButton = document.querySelector("[data-run='voice']");
  voiceButton?.setAttribute("data-bound", "true");
  voiceButton?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state.settingsOpen = false;
    runVoiceInputDemo();
  });

  const sendButton = document.querySelector("[data-run='custom']");
  sendButton?.setAttribute("data-bound", "true");
  sendButton?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    submitVoiceDraft();
  });

  document.addEventListener("click", (event) => {
    const sceneButton = event.target.closest("[data-scene]");
    if (sceneButton) switchScene(sceneButton.dataset.scene);

    const elementButton = event.target.closest("[data-element]");
    if (elementButton) selectElement(elementButton.dataset.element);

    const resumeButton = event.target.closest("[data-resume]");
    if (resumeButton) resumeClarification(resumeButton.dataset.resume);

    const memoryActionButton = event.target.closest("[data-memory-action]");
    if (memoryActionButton) {
      const action = memoryActionButton.dataset.memoryAction;
      const memoryId = memoryActionButton.dataset.memoryId;
      if (action === "open") openMemoryPanel();
      if (action === "close") closeMemoryPanel();
      if (action === "create") createMemoryFromPanel();
      if (action === "edit") startMemoryEdit(memoryId);
      if (action === "save") saveMemoryEdit(memoryId);
      if (action === "cancel-edit") cancelMemoryEdit();
      if (action === "status") updateMemoryStatus(memoryId, memoryActionButton.dataset.memoryStatus);
      if (action === "delete") deleteMemoryFromPanel(memoryId);
      return;
    }

    if (state.memory.panelOpen && event.target.id === "memoryOverlay") {
      closeMemoryPanel();
      return;
    }

    const menuButton = event.target.closest("[data-menu-toggle='settings']");
    if (menuButton) {
      state.settingsOpen = !state.settingsOpen;
      renderHeader();
      return;
    }

    if (state.settingsOpen && !event.target.closest(".settings-menu")) {
      state.settingsOpen = false;
      renderHeader();
    }

    const projectActionButton = event.target.closest("[data-project-action]");
    if (projectActionButton) {
      runProjectAction(projectActionButton.dataset.projectAction);
      return;
    }

    const runButton = event.target.closest("[data-run]");
    if (runButton) {
      state.settingsOpen = false;
      if (runButton.dataset.run === "voice") runVoiceInputDemo();
      if (runButton.dataset.run === "storyboard") runStoryboardDemo();
      if (runButton.dataset.run === "arrow") runArrowDemo();
      if (runButton.dataset.run === "clarification") runClarificationDemo();
      if (runButton.dataset.run === "export") runExportDemo();
      if (runButton.dataset.run === "custom") submitVoiceDraft();
    }

  });

  $("#voiceInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") submitVoiceDraft();
  });

  document.addEventListener("error", handleCatalogAssetImageError, true);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.memory.panelOpen) {
      closeMemoryPanel();
      return;
    }

    if (event.key === "Escape" && state.settingsOpen) {
      state.settingsOpen = false;
      renderHeader();
      return;
    }

    if (!isVoiceShortcut(event) || event.repeat) return;
    if (isTypingTarget(event.target)) return;

    event.preventDefault();
    state.settingsOpen = false;
    runVoiceInputDemo();
  });
}

function handleCatalogAssetImageError(event) {
  const image = event.target instanceof HTMLImageElement ? event.target : null;
  const assetPath = image?.dataset.assetPath;
  if (!assetPath) return;
  catalogAssetState.urls.delete(assetPath);
  catalogAssetState.failed.add(assetPath);
  render();
}

function isVoiceShortcut(event) {
  return event.altKey && event.code === "KeyV";
}

function isTypingTarget(target) {
  const element = target instanceof HTMLElement ? target : null;
  if (!element) return false;

  return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
}

bindEvents();
render();
hydrateRenderCatalog().then(render);
hydrateBackendState();
