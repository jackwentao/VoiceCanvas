export const DEFAULT_PROJECT_ID = "project_demo_voicecanvas";
export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function apiBaseUrl() {
  return window.VOICECANVAS_API_BASE_URL || DEFAULT_API_BASE_URL;
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

  return response.json();
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

export function startOrchestration(projectId, userInput) {
  return requestJson("/api/orchestrations", {
    method: "POST",
    body: JSON.stringify({
      projectId,
      userInput
    })
  });
}
