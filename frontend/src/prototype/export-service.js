const PROJECT_BUNDLE_TYPE = "voicecanvas.project";
const PROJECT_SCHEMA_VERSION = 1;

export function exportProjectFile(project) {
  const bundle = createProjectBundle(project);
  const content = JSON.stringify(bundle, null, 2);
  downloadBlob(content, `${safeFilename(project.title)}.voicecanvas.json`, "application/json");
  return bundle;
}

export async function exportSceneImage(project, options = {}) {
  const scene = selectScene(project, options.sceneId);
  const svg = sceneToSvg(scene);
  const filename = `${safeFilename(project.title)}-${safeFilename(scene.name)}.png`;
  await downloadSvgAsPng(svg, filename, scene.canvas?.width || 960, scene.canvas?.height || 540);
  return { format: "png", sceneId: scene.id, filename };
}

export async function exportFromBackendResult(exportResult, project) {
  if (!exportResult) return null;

  if (exportResult.format === "json" || exportResult.mimeType === "application/json") {
    downloadBlob(exportResult.content, exportResult.filename, "application/json");
    return exportResult;
  }

  if (exportResult.format === "png" && exportResult.mimeType === "image/svg+xml") {
    const scene = selectScene(project, exportResult.sceneId);
    await downloadSvgAsPng(
      exportResult.content,
      exportResult.filename,
      scene.canvas?.width || 960,
      scene.canvas?.height || 540
    );
    return exportResult;
  }

  downloadBlob(exportResult.content, exportResult.filename, exportResult.mimeType || "image/svg+xml");
  return exportResult;
}

export async function importProjectFile(file) {
  const text = await file.text();
  const payload = JSON.parse(text);
  const project = payload.type === PROJECT_BUNDLE_TYPE ? payload.project : payload;
  if (!project?.id || !Array.isArray(project.scenes) || !project.activeSceneId) {
    throw new Error("项目文件格式不正确");
  }
  return { payload, project };
}

function createProjectBundle(project) {
  return {
    type: PROJECT_BUNDLE_TYPE,
    schemaVersion: PROJECT_SCHEMA_VERSION,
    exportedAt: new Date().toISOString(),
    project: structuredClone(project)
  };
}

function selectScene(project, sceneId) {
  const targetSceneId = sceneId || project.activeSceneId;
  const scene = project.scenes.find((item) => item.id === targetSceneId);
  if (!scene) throw new Error("导出目标镜头不存在");
  return scene;
}

function sceneToSvg(scene) {
  const width = scene.canvas?.width || 960;
  const height = scene.canvas?.height || 540;
  const background = scene.canvas?.background?.color || "#ffffff";
  const elements = [...(scene.elements || [])].sort((left, right) => getZIndex(left) - getZIndex(right));
  const body = elements.map(elementToSvg).join("\n");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <rect width="100%" height="100%" fill="${escapeAttribute(background)}"/>
    ${body}
  </svg>`;
}

function elementToSvg(element) {
  const transform = getTransform(element);
  if (element.type === "text") {
    const text = escapeHtml(element.content?.text || element.text || element.name || "");
    const fontSize = Number(element.style?.fontSize || 28);
    const background = element.boxStyle?.fill?.color || element.style?.backgroundColor;
    const backgroundRect = background
      ? `<rect x="${transform.x}" y="${transform.y}" width="${transform.width}" height="${transform.height}" rx="8" fill="${escapeAttribute(background)}"/>`
      : "";
    return `${backgroundRect}<text x="${transform.x + 12}" y="${transform.y + transform.height / 2 + fontSize / 3}" font-size="${fontSize}" fill="${escapeAttribute(element.style?.color || "#111827")}" font-family="Arial, sans-serif">${text}</text>`;
  }

  if (element.type === "connector") {
    return "";
  }

  const style = element.placeholderStyle || element.style || {};
  const fill = style.fill || "#ffffff";
  const stroke = style.stroke || "#243b53";
  const strokeWidth = style.strokeWidth || style.stroke?.width || 2;
  const radius = style.radius || element.style?.radius || 8;
  const label = escapeHtml(element.content?.label || element.label || element.text || element.name || "");
  return `<rect x="${transform.x}" y="${transform.y}" width="${transform.width}" height="${transform.height}" rx="${radius}" fill="${escapeAttribute(fill)}" stroke="${escapeAttribute(stroke)}" stroke-width="${strokeWidth}"/>
    ${label ? `<text x="${transform.x + transform.width / 2}" y="${transform.y + transform.height / 2}" text-anchor="middle" font-size="24" fill="#111827">${label}</text>` : ""}`;
}

async function downloadSvgAsPng(svg, filename, width, height) {
  if (typeof Image === "undefined" || typeof document === "undefined") {
    downloadBlob(svg, filename.replace(/\.png$/i, ".svg"), "image/svg+xml");
    return;
  }

  const svgUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const image = await loadImage(svgUrl);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("PNG 导出失败");
    downloadBlob(blob, filename, "image/png");
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片导出渲染失败"));
    image.src = url;
  });
}

function downloadBlob(content, filename, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function getTransform(element) {
  return {
    x: element.transform?.x ?? element.x ?? 0,
    y: element.transform?.y ?? element.y ?? 0,
    width: element.transform?.width ?? element.width ?? 1,
    height: element.transform?.height ?? element.height ?? 1
  };
}

function getZIndex(element) {
  return element.layer?.zIndex ?? element.zIndex ?? 0;
}

function safeFilename(value) {
  return String(value || "voicecanvas")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
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
