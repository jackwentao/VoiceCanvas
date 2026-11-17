// 首页只读取画廊，不接入结构化项目或命令接口。
function apiBaseUrl() {
  return (window.VOICECANVAS_API_BASE_URL || new URLSearchParams(location.search).get("apiBaseUrl") || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export function resolveBackendUrl(path) {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function loadShowcase(category = "") {
  const response = await fetch(resolveBackendUrl(`/api/showcase${category ? `?category=${encodeURIComponent(category)}` : ""}`));
  if (!response.ok) throw new Error(`画廊请求失败：${response.status}`);
  return response.json();
}
