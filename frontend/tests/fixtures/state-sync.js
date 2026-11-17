import { mergeElementPatch } from "./element-patch.js";

const CANVAS_PATCH_EVENT = "CANVAS_PATCH_APPLIED";
const CLARIFICATION_EVENT = "CLARIFICATION_REQUESTED";
const EXPORT_EVENT = "EXPORT_COMPLETED";

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeEvent(event) {
  return {
    id: event.id || makeId("event"),
    createdAt: event.createdAt || nowIso(),
    ...event
  };
}

function latestEvent(events, type) {
  return [...events].reverse().find((event) => event.type === type);
}

function summaryMessage(summary) {
  if (!summary) return "等待后端事件";
  if (typeof summary === "string") return summary;
  return summary.message || "本轮状态已同步";
}

function summaryCommandCount(summary, patches) {
  if (summary && typeof summary === "object" && Number.isFinite(summary.commandCount)) {
    return summary.commandCount;
  }
  return patches?.length || 0;
}

function normalizeTokenUsage(summary) {
  const usage = summary && typeof summary === "object" ? summary.tokenUsage : null;
  return {
    promptTokens: nonNegativeInteger(usage?.promptTokens),
    completionTokens: nonNegativeInteger(usage?.completionTokens),
    totalTokens: nonNegativeInteger(usage?.totalTokens)
  };
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value > 0 ? value : 0;
}

function recordTokenUsage(state, summary, sessionId) {
  if (!state.telemetry) return;
  const usage = normalizeTokenUsage(summary);
  state.telemetry.lastTurnTokenUsage = usage;
  if (!sessionId || state.telemetry.lastCountedSessionId === sessionId) return;
  state.telemetry.totalTokenUsage = addTokenUsage(state.telemetry.totalTokenUsage, usage);
  state.telemetry.lastCountedSessionId = sessionId;
}

function addTokenUsage(left = {}, right = {}) {
  return {
    promptTokens: nonNegativeInteger(left.promptTokens) + nonNegativeInteger(right.promptTokens),
    completionTokens: nonNegativeInteger(left.completionTokens) + nonNegativeInteger(right.completionTokens),
    totalTokens: nonNegativeInteger(left.totalTokens) + nonNegativeInteger(right.totalTokens)
  };
}

function createPatchChange(patch) {
  const targetName =
    patch.element?.name || patch.scene?.name || patch.elementId || patch.sceneId || patch.type;

  return {
    type: patch.type,
    targetType: patch.elementId || patch.element ? "element" : "scene",
    targetName,
    description: patch.type
  };
}

function normalizeSummary(summary, patches, userInput, stage) {
  return {
    userInput,
    completed: Boolean(summary?.completed ?? stage === "completed"),
    stage,
    message: summaryMessage(summary),
    commandCount: summaryCommandCount(summary, patches),
    changes: patches?.map(createPatchChange) || []
  };
}

function pendingClarificationFrom(response, events) {
  const event = latestEvent(events, CLARIFICATION_EVENT);
  const nextAction = response.nextAction;

  if (!event && !nextAction) return null;

  const options = nextAction?.options || event?.options || [];
  return {
    id: nextAction?.id || makeId("clarification"),
    originalInput: response.originalUserInput || "",
    question: nextAction?.question || event?.question || "需要进一步确认",
    expectedAnswerType: nextAction?.expectedAnswerType || "selection",
    options: options.map((option) => ({
      id: option.id || option.value || option.label,
      label: option.label || option.value || option.id,
      value: option.value || option.elementId || option.id || option.label,
      elementId: option.elementId || option.value || option.id,
      sceneId: option.sceneId,
      bounds: option.bounds
    })),
    resumePolicy: nextAction?.resumePolicy,
    createdAt: event?.createdAt || nowIso()
  };
}

function createSession(response, userInput, events) {
  const stageEvent = latestEvent(events, "STAGE_CHANGED");
  const summaryEvent = latestEvent(events, "TURN_SUMMARY");
  const summary = response.summary || summaryEvent?.summary;
  const stage = response.stage || stageEvent?.stage || "completed";
  const commandCount = summaryCommandCount(summary, response.patches);
  const completedSteps = response.status === "COMPLETED" ? commandCount : 0;

  return {
    id: response.sessionId || "session_backend_state",
    status: response.status || "COMPLETED",
    stage,
    originalUserInput: userInput || "",
    currentUserInput: userInput || "",
    progress: {
      completedSteps,
      totalSteps: Math.max(commandCount, response.patches?.length || 0),
      message: summaryMessage(summary) || stageEvent?.message
    },
    taskPlan: null,
    pendingClarification: pendingClarificationFrom(response, events),
    lastSummary: normalizeSummary(summary, response.patches || [], userInput || "", stage)
  };
}

export function createBackendPendingSession(sessionId, userInput) {
  return {
    id: sessionId,
    status: "RUNNING",
    stage: "understanding",
    originalUserInput: userInput,
    currentUserInput: userInput,
    progress: {
      completedSteps: 0,
      totalSteps: 1,
      message: "已提交后端编排"
    },
    taskPlan: null,
    pendingClarification: null,
    lastSummary: null
  };
}

export function applyBackendResponse(state, response, options = {}) {
  const events = (response.events || []).map(normalizeEvent);

  if (response.project) {
    state.project = structuredClone(response.project);
  }

  if (Array.isArray(response.history)) {
    state.history = structuredClone(response.history);
  }

  if (response.sessionId || response.summary || response.nextAction) {
    recordTokenUsage(state, response.summary, response.sessionId);
    state.session = createSession(response, options.userInput, events);
    state.voiceStatus = summaryMessage(response.summary);
    state.voiceDraftReady = false;
  }

  if (events.length) {
    state.eventLog = [...events].reverse().concat(state.eventLog).slice(0, 14);
  }
}

export function applyBackendEvent(state, event, options = {}) {
  const normalized = normalizeEvent(event);
  if (normalized.sessionId) {
    state.session.id = normalized.sessionId;
  }

  if (normalized.type === "STAGE_CHANGED") {
    state.session.stage = normalized.stage || state.session.stage;
    state.session.status = normalized.stage === "failed" ? "FAILED" : "RUNNING";
    state.session.progress = {
      ...(state.session.progress || {}),
      message: normalized.message || state.session.progress?.message || "正在处理后端事件"
    };
    state.voiceStatus = normalized.message || state.voiceStatus;
  }

  if (normalized.type === CANVAS_PATCH_EVENT && normalized.patch) {
    applyCanvasPatch(state.project, normalized.patch);
    state.session.progress = {
      ...(state.session.progress || {}),
      completedSteps: (state.session.progress?.completedSteps || 0) + 1,
      totalSteps: Math.max(
        state.session.progress?.totalSteps || 0,
        (state.session.progress?.completedSteps || 0) + 1
      ),
      message: normalized.patch.type
    };
  }

  if (normalized.type === CLARIFICATION_EVENT) {
    state.session.status = "WAITING_FOR_USER";
    state.session.stage = "waiting_for_user";
    state.session.pendingClarification = pendingClarificationFrom(
      { sessionId: normalized.sessionId },
      [normalized]
    );
    state.voiceStatus = normalized.question || "需要进一步确认";
  }

  if (normalized.type === EXPORT_EVENT) {
    state.session.progress = {
      completedSteps: 1,
      totalSteps: 1,
      message: normalized.export?.filename || "导出完成"
    };
    state.voiceStatus = "导出完成";
  }

  if (normalized.type === "TURN_SUMMARY") {
    recordTokenUsage(state, normalized.summary, normalized.sessionId);
    state.session.lastSummary = normalizeSummary(
      normalized.summary,
      [],
      options.userInput || state.session.currentUserInput || "",
      state.session.stage
    );
    state.voiceStatus = summaryMessage(normalized.summary);
  }

  state.eventLog = [normalized].concat(state.eventLog).slice(0, 14);
}

export function appendBackendError(state, error) {
  state.eventLog.unshift(
    normalizeEvent({
      type: "BACKEND_REQUEST_FAILED",
      message: error.message || String(error)
    })
  );
  state.eventLog = state.eventLog.slice(0, 14);
  state.voiceStatus = "后端不可用，已切换本地演示";
}

function applyCanvasPatch(project, patch) {
  if (!patch || !project?.scenes) return;

  if (patch.type === "PROJECT_UPDATED") {
    Object.assign(project, patch.patch || {});
  }

  if (patch.type === "SCENE_CREATED" && patch.scene) {
    if (!project.scenes.some((scene) => scene.id === patch.scene.id)) {
      project.scenes.push(structuredClone(patch.scene));
    }
    if (!findScene(project, project.activeSceneId)) {
      project.activeSceneId = patch.scene.id;
    }
  }

  if (patch.type === "SCENE_UPDATED") {
    const scene = findScene(project, patch.sceneId);
    if (scene) Object.assign(scene, patch.patch || {});
  }

  if (patch.type === "SCENE_DELETED") {
    const deletedScene = findScene(project, patch.sceneId) || patch.scene;
    project.scenes = project.scenes.filter((scene) => scene.id !== patch.sceneId);
    if (project.activeSceneId === patch.sceneId || !findScene(project, project.activeSceneId)) {
      const fallbackScene = chooseNeighborScene(project.scenes, deletedScene);
      if (fallbackScene) {
        project.activeSceneId = fallbackScene.id;
      }
    }
  }

  if (patch.type === "SCENE_CLEARED") {
    const scene = findScene(project, patch.sceneId);
    if (scene) {
      scene.elements = [];
      scene.description = null;
    }
  }

  if (patch.type === "ACTIVE_SCENE_CHANGED" && patch.sceneId) {
    project.activeSceneId = patch.sceneId;
  }

  if (patch.type === "ELEMENT_ADDED" && patch.element) {
    const scene = findScene(project, patch.sceneId);
    if (scene && !scene.elements.some((element) => element.id === patch.element.id)) {
      scene.elements.push(structuredClone(patch.element));
    }
  }

  if (patch.type === "ELEMENT_UPDATED") {
    const scene = findScene(project, patch.sceneId);
    const element = scene?.elements.find((item) => item.id === patch.elementId);
    if (element) Object.assign(element, mergeElementPatch(element, patch.patch || {}));
  }

  if (patch.type === "ELEMENT_DELETED") {
    const scene = findScene(project, patch.sceneId);
    if (scene) {
      scene.elements = scene.elements.filter((element) => element.id !== patch.elementId);
    }
  }
}

function findScene(project, sceneId) {
  return project.scenes.find((scene) => scene.id === sceneId);
}

function chooseNeighborScene(scenes, deletedScene) {
  if (!scenes.length) return null;
  const deletedOrder = Number.isFinite(deletedScene?.order) ? deletedScene.order : null;
  if (deletedOrder === null) {
    return orderedScenes(scenes)[0];
  }

  const before = scenes.filter((scene) => Number.isFinite(scene.order) && scene.order < deletedOrder);
  if (before.length) {
    return orderedScenes(before).at(-1);
  }
  return orderedScenes(scenes)[0];
}

function orderedScenes(scenes) {
  return [...scenes].sort((left, right) => {
    const leftOrder = Number.isFinite(left.order) ? left.order : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(right.order) ? right.order : Number.MAX_SAFE_INTEGER;
    return leftOrder - rightOrder;
  });
}
