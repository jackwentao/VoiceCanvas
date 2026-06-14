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
  validateProjectJsonFile(file);
  const text = await file.text();
  const payload = JSON.parse(text);
  const project = payload.type === PROJECT_BUNDLE_TYPE ? payload.project : payload;
  if (!project?.id || !Array.isArray(project.scenes) || !project.activeSceneId) {
    throw new Error("项目文件格式不正确");
  }
  return { payload, project };
}

function validateProjectJsonFile(file) {
  const name = String(file?.name || "").toLowerCase();
  const type = String(file?.type || "").toLowerCase();
  const hasJsonExtension = name.endsWith(".json") || name.endsWith(".voicecanvas.json");
  const hasJsonMime = type === "application/json" || type.endsWith("+json");

  if (name ? !hasJsonExtension : !hasJsonMime) {
    throw new Error("只能载入 JSON 项目文件");
  }

  if (type && !hasJsonMime && !hasJsonExtension) {
    throw new Error("只能载入 JSON 项目文件");
  }
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

export function sceneToSvg(scene) {
  const width = scene.canvas?.width || 960;
  const height = scene.canvas?.height || 540;
  const background = scene.canvas?.background?.color || "#ffffff";
  const elements = [...(scene.elements || [])].sort((left, right) => getZIndex(left) - getZIndex(right));
  const renderedElements = elements.map(elementToSvg);
  const body = renderedElements.join("\n");
  const illustrationStyles = renderedElements.some((item) => item.includes("object-illustration"))
    ? `<style>${ILLUSTRATION_SVG_STYLES}</style>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    ${illustrationStyles}
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

  const imageHref = getElementImageHref(element);
  if (imageHref) {
    return imageElementToSvg(element, transform, imageHref);
  }

  const illustration = illustrationElementToSvg(element, transform);
  if (illustration) return illustration;

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

  const exportSvg = await inlineSvgImageHrefs(svg);
  const svgUrl = URL.createObjectURL(new Blob([exportSvg], { type: "image/svg+xml" }));
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

async function inlineSvgImageHrefs(svg) {
  if (
    typeof DOMParser === "undefined" ||
    typeof XMLSerializer === "undefined" ||
    typeof fetch !== "function"
  ) {
    return svg;
  }

  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  const imageNodes = [...parsed.querySelectorAll("image")];
  await Promise.all(
    imageNodes.map(async (node) => {
      const href = node.getAttribute("href") || node.getAttribute("xlink:href");
      if (!href || href.startsWith("data:") || href.startsWith("blob:")) return;
      const dataUrl = await imageUrlToDataUrl(href);
      node.setAttribute("href", dataUrl);
      node.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", dataUrl);
    })
  );
  return new XMLSerializer().serializeToString(parsed.documentElement);
}

async function imageUrlToDataUrl(url) {
  const response = await fetch(url, { mode: "cors", credentials: "omit" });
  if (!response.ok) {
    throw new Error(`图片导出失败：${url} 返回 ${response.status}`);
  }

  const blob = await response.blob();
  if (typeof FileReader !== "undefined") {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error(`图片导出失败：无法读取 ${url}`));
      reader.readAsDataURL(blob);
    });
  }

  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `data:${blob.type || "application/octet-stream"};base64,${btoa(binary)}`;
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

function getContent(element) {
  return element.content || {};
}

function getElementImageHref(element) {
  const content = getContent(element);
  if (element.type === "image") {
    return content.url || element.image?.url || element.url || null;
  }

  if (element.type === "generated_asset" && element.asset?.status === "ready") {
    return content.url || element.asset?.url || element.image?.url || element.url || null;
  }

  return null;
}

function imageElementToSvg(element, transform, href) {
  const radius = Number(element.style?.radius ?? element.style?.borderRadius ?? 8);
  const clipId = `clip-${safeSvgId(element.id || element.name || href)}`;
  return `<defs><clipPath id="${clipId}"><rect x="${transform.x}" y="${transform.y}" width="${transform.width}" height="${transform.height}" rx="${radius}"/></clipPath></defs>
    <image href="${escapeAttribute(href)}" xlink:href="${escapeAttribute(href)}" x="${transform.x}" y="${transform.y}" width="${transform.width}" height="${transform.height}" preserveAspectRatio="xMidYMid slice" clip-path="url(#${clipId})"/>`;
}

function illustrationElementToSvg(element, transform) {
  const spec = semanticIllustrationSpec(element);
  if (!spec) return "";
  const label = getContent(element).label || getContent(element).alt || element.label || element.name || "";
  const svg = renderIllustrationSvg(spec, label);
  if (!svg) return "";
  return `<g transform="translate(${transform.x} ${transform.y})">${svg.replace(
    "<svg ",
    `<svg width="${transform.width}" height="${transform.height}" `
  )}</g>`;
}

function semanticIllustrationSpec(element) {
  const metadata = element.metadata || {};
  const explicitRenderKey = metadata.renderKey || metadata.renderHint;
  if (explicitRenderKey === "girl") {
    return { kind: "character", variant: "female" };
  }
  if (["character", "cat", "table"].includes(explicitRenderKey)) {
    return {
      kind: explicitRenderKey,
      variant: normalizeCharacterVariant(metadata.renderVariant)
    };
  }

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
    .join(" ");
  return semanticSpecFromText(declaredText);
}

function semanticSpecFromSubject(subject) {
  if (!subject || typeof subject !== "object") return null;
  const character = subject.character;
  if (character && typeof character === "object") {
    const text = [character.category, character.role, character.gender, ...(character.keyFeatures || [])]
      .filter(Boolean)
      .join(" ");
    return semanticSpecFromText(text) || {
      kind: "character",
      variant: normalizeCharacterVariant(character.gender)
    };
  }

  const product = subject.product;
  if (product && typeof product === "object") {
    const text = [product.category, product.brand, ...(product.keyFeatures || [])]
      .filter(Boolean)
      .join(" ");
    return semanticSpecFromText(text);
  }
  return null;
}

function semanticSpecFromText(text) {
  const normalized = String(text || "").toLowerCase();
  if (includesAny(normalized, ["男生", "男孩", "男人", "男性", "boy", "man"])) {
    return { kind: "character", variant: "male" };
  }
  if (includesAny(normalized, ["女生", "女孩", "女人", "女性", "girl", "woman"])) {
    return { kind: "character", variant: "female" };
  }
  if (includesAny(normalized, ["人物", "人像", "person", "character"])) {
    return { kind: "character", variant: "neutral" };
  }
  if (includesAny(normalized, ["猫", "小猫", "cat"])) return { kind: "cat" };
  if (includesAny(normalized, ["桌", "桌子", "table", "desk"])) return { kind: "table" };
  return null;
}

function includesAny(value, needles) {
  return needles.some((needle) => value.includes(needle));
}

function normalizeCharacterVariant(value) {
  if (["male", "男", "男生", "男性"].includes(value)) return "male";
  if (["female", "女", "女生", "女性"].includes(value)) return "female";
  return "neutral";
}

function renderIllustrationSvg(spec, label) {
  if ((spec.renderKey || spec.kind) === "character") return characterIllustrationSvg(label, spec.variant);
  if ((spec.renderKey || spec.kind) === "cat") return catIllustrationSvg(label);
  if ((spec.renderKey || spec.kind) === "table") return tableIllustrationSvg(label);
  return "";
}

function characterIllustrationSvg(label, variant = "neutral") {
  const normalizedVariant = normalizeCharacterVariant(variant);
  const isFemale = normalizedVariant === "female";
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

function safeSvgId(value) {
  return (
    String(value || "image")
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-|-$/g, "") || "image"
  );
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

const ILLUSTRATION_SVG_STYLES = `
.object-illustration{overflow:visible}
.character-shadow,.cat-shadow,.table-shadow{fill:rgba(27,43,52,.12)}
.character-hair-back,.character-hair-front{fill:#3b2417;stroke:#25150d;stroke-width:5;stroke-linejoin:round}
.character-face,.character-neck{fill:#ffd2ad;stroke:#8a4b2a;stroke-width:4}
.character-eye,.cat-eye,.cat-nose{fill:#1b2b34}
.character-smile,.character-arm,.character-leg,.character-shoe{fill:none;stroke:#8a4b2a;stroke-width:5;stroke-linecap:round;stroke-linejoin:round}
.character-dress{fill:#f15b8a;stroke:#8b2450;stroke-width:5;stroke-linejoin:round}
.character-shirt{fill:#2d6cdf;stroke:#173f8a;stroke-width:5;stroke-linejoin:round}
.character-pants{fill:#243b53;stroke:#1b2b34;stroke-width:5;stroke-linejoin:round}
.character-illustration.is-neutral .character-shirt{fill:#1f8a5b;stroke:#176146}
.character-illustration.is-neutral .character-hair-back,.character-illustration.is-neutral .character-hair-front{fill:#5a3825}
.cat-body,.cat-head,.cat-ear{fill:#f6b25f;stroke:#7c3f15;stroke-width:5;stroke-linejoin:round}
.cat-tail,.cat-mouth,.cat-whisker,.cat-leg{fill:none;stroke:#7c3f15;stroke-width:5;stroke-linecap:round}
.table-top{fill:#9a5424;stroke:#5d2d12;stroke-width:5;stroke-linejoin:round}
.table-front,.table-leg{fill:#7d3f18;stroke:#5d2d12;stroke-width:5;stroke-linejoin:round}
.table-grain{fill:none;stroke:#d7a46c;stroke-width:5;stroke-linecap:round;opacity:.8}
.table-object{fill:#f6c453;stroke:#b7791f;stroke-width:4}
`;
