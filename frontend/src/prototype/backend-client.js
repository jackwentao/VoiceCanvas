export const DEFAULT_PROJECT_ID = "project_demo_voicecanvas";
export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
export const DEFAULT_USER_ID = "user_1";

function apiBaseUrl() {
  const queryBaseUrl = new URLSearchParams(window.location.search).get("apiBaseUrl");
  return window.VOICECANVAS_API_BASE_URL || queryBaseUrl || DEFAULT_API_BASE_URL;
}

function streamStepDelayMs() {
  const queryDelay = new URLSearchParams(window.location.search).get("streamStepDelayMs");
  const configuredDelay = window.VOICECANVAS_STREAM_STEP_DELAY_MS ?? queryDelay ?? 80;
  const delay = Number(configuredDelay);
  return Number.isFinite(delay) && delay >= 0 ? delay : 80;
}

async function requestJson(path, options = {}) {
  if (typeof fetch !== "function") {
    return requestJsonWithXhr(path, options);
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {})
    }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`后端请求失败：${response.status} ${body || response.statusText}`);
  }

  if (response.status === 204) return null;
  const body = await response.text();
  return body ? JSON.parse(body) : null;
}

function requestJsonWithXhr(path, options = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || "GET", `${apiBaseUrl()}${path}`);
    xhr.setRequestHeader("content-type", "application/json");

    for (const [key, value] of Object.entries(options.headers || {})) {
      xhr.setRequestHeader(key, value);
    }

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`后端请求失败：${xhr.status} ${xhr.responseText || xhr.statusText}`));
        return;
      }

      if (xhr.status === 204 || !xhr.responseText) {
        resolve(null);
        return;
      }

      try {
        resolve(JSON.parse(xhr.responseText));
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new Error("后端请求失败：网络不可用"));
    xhr.send(options.body || null);
  });
}

export function loadProjectState(projectId = DEFAULT_PROJECT_ID) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}`);
}

export function createProjectState(payload = {}) {
  return requestJson("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function exportProjectState(projectId = DEFAULT_PROJECT_ID, payload = {}) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/export`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function importProjectState(payload) {
  return requestJson("/api/projects/import", {
    method: "POST",
    body: JSON.stringify({ payload })
  });
}

export function startOrchestration(projectId, userInput) {
  return requestJson("/api/orchestrations", {
    method: "POST",
    body: JSON.stringify({
      projectId,
      userInput
    })
  });
}

export async function startOrchestrationStream(projectId, userInput, handlers = {}) {
  if (typeof fetch !== "function" || typeof ReadableStream === "undefined") {
    return startOrchestration(projectId, userInput);
  }

  const response = await fetch(`${apiBaseUrl()}/api/orchestrations/stream`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      projectId,
      userInput
    })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`后端请求失败：${response.status} ${body || response.statusText}`);
  }

  if (!response.body?.getReader) {
    return startOrchestration(projectId, userInput);
  }

  return readSseStream(response.body, handlers);
}

export function resumeOrchestration(projectId, sessionId, answer) {
  return requestJson(`/api/orchestrations/${encodeURIComponent(sessionId)}/resume`, {
    method: "POST",
    body: JSON.stringify({
      projectId,
      answer
    })
  });
}

export function listUserMemories(userId = DEFAULT_USER_ID, includeInactive = true) {
  const params = new URLSearchParams({
    includeInactive: String(includeInactive)
  });
  return requestJson(`/api/users/${encodeURIComponent(userId)}/memories?${params.toString()}`);
}

export function createUserMemory(userId = DEFAULT_USER_ID, payload) {
  return requestJson(`/api/users/${encodeURIComponent(userId)}/memories`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateUserMemory(memoryId, patch) {
  return requestJson(`/api/memories/${encodeURIComponent(memoryId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export function deleteUserMemory(memoryId) {
  return requestJson(`/api/memories/${encodeURIComponent(memoryId)}`, {
    method: "DELETE"
  });
}

async function readSseStream(body, handlers) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      finalResult = (await dispatchSseBlock(block, handlers)) || finalResult;
    }

    if (done) break;
  }

  if (buffer.trim()) {
    finalResult = (await dispatchSseBlock(buffer, handlers)) || finalResult;
  }

  return finalResult;
}

async function dispatchSseBlock(block, handlers) {
  const message = parseSseBlock(block);
  if (!message) return null;

  if (message.event === "orchestration.event") {
    await handlers.onEvent?.(message.data);
    await yieldToBrowserPaint();
    return null;
  }

  if (message.event === "orchestration.result") {
    await handlers.onResult?.(message.data);
    await yieldToBrowserPaint();
    return message.data;
  }

  return null;
}

async function yieldToBrowserPaint() {
  if (typeof requestAnimationFrame === "function") {
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }

  const delay = streamStepDelayMs();
  if (delay > 0) {
    await new Promise((resolve) => window.setTimeout(resolve, delay));
  }
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (!dataLines.length) return null;
  return {
    event,
    data: JSON.parse(dataLines.join("\n"))
  };
}
