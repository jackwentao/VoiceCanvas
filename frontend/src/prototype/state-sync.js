const CANVAS_PATCH_EVENT = "CANVAS_PATCH_APPLIED";
const CLARIFICATION_EVENT = "CLARIFICATION_REQUESTED";

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
    state.session = createSession(response, options.userInput, events);
    state.voiceStatus = summaryMessage(response.summary);
    state.voiceDraftReady = false;
  }

  if (events.length) {
    state.eventLog = [...events].reverse().concat(state.eventLog).slice(0, 14);
  }
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
