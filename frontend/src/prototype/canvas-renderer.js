// 画布投影：只读取后端快照，选中状态和素材加载缓存属于临时 UI 状态。
import { fitTextFontSize } from "./text-layout.js";
import { getElementShapeKind, shapeToInlineSvg } from "./shape-renderer.js";
import { resolveCatalogAssetUrl } from "./backend-client.js";
const state = { project: null, selectedElementId: null };
const renderCatalogState = { byKey: new Map() };
const catalogAssetState = { urls: new Map(), pending: new Set(), failed: new Set() };
let refresh = () => {};
function render() { refresh(); }
function activeScene() { return state.project.scenes.find(s => s.id === state.project.activeSceneId); }
export function markCatalogAssetFailed(path) { catalogAssetState.failed.add(path); }
export function setRenderCatalog(catalog) {
  renderCatalogState.byKey = new Map((catalog.items || []).map(item => [item.renderKey, item]));
}
export function renderSceneMarkup(project, scene, selectedElementId = null, onLoad = () => {}) {
  state.project = { ...project, activeSceneId: scene.id };
  state.selectedElementId = selectedElementId;
  refresh = onLoad;
  const elements = [...scene.elements].filter(e => e.transform?.visible !== false)
    .sort((a, b) => getLayer(a).zIndex - getLayer(b).zIndex);
  return elements.filter(e => e.type !== "connector").map(renderElement).join("") +
    renderConnectorLayer(scene, elements, createElementLayoutIndex(scene));
}
export function renderSceneThumbnailMarkup(project, scene, onLoad) {
  // 缩略图处于镜头按钮内部，使用静态节点避免嵌套 button 破坏 DOM。
  return renderSceneMarkup(project, scene, null, onLoad)
    .replaceAll("<button ", "<div ").replaceAll("</button>", "</div>");
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
  return `
    <button class="canvas-element text-element ${selected}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)};${textElementStyle(element, text)}">
      <span>${escapeHtml(text)}</span>
      ${renderElementDescription(element)}
    </button>
  `;
}

function renderShapeElement(element) {
  const illustration = renderSemanticIllustrationElement(element);
  if (illustration) return illustration;

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const transform = getTransform(element);
  const shapeKind = getElementShapeKind(element);
  const fill = resolvePaint(element.style?.fill, "#ffffff");
  const stroke = resolveStroke(element.style?.stroke, element.style?.strokeWidth, "#243b53");
  const geometry = shapeToInlineSvg({
    kind: shapeKind,
    width: transform.width,
    height: transform.height,
    fill,
    stroke: stroke.color,
    strokeWidth: stroke.width,
    dash: stroke.dash,
    cornerRadius: getShapeRadius(element)
  });
  const label = getContent(element).label || element.label || "";
  return `
    <button class="canvas-element shape-element ${selected}" data-shape="${shapeKind}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)}">
      ${geometry}
      ${label ? `<span class="shape-label">${escapeHtml(label)}</span>` : ""}
      ${renderElementDescription(element)}
    </button>
  `;
}

function renderImageElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const content = getContent(element);
  const radius = element.style?.radius ?? element.style?.borderRadius ?? 8;
  return `
    <button class="canvas-element image-element ${selected}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)};border-radius:${radius}px">
      ${content.url ? `<img src="${escapeAttribute(content.url)}" alt="${escapeAttribute(content.alt || element.name || "")}">` : `<span>${escapeHtml(content.alt || element.name || "图片")}</span>`}
      ${renderElementDescription(element)}
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
      <button class="canvas-element generated-asset-element ${selected}" data-element="${escapeAttribute(element.id)}" data-status="ready" style="${elementBoxStyle(element)}">
        <img src="${escapeAttribute(content.url)}" alt="${escapeAttribute(content.alt || element.name || "")}">
        ${renderElementDescription(element)}
      </button>
    `;
  }

  const placeholderStyle = [
    `background:${element.placeholderStyle?.fill || "#ffffff"}`,
    `border:${element.placeholderStyle?.strokeWidth || 1}px dashed ${element.placeholderStyle?.stroke || "#243b53"}`,
    `border-radius:${element.placeholderStyle?.radius || 8}px`
  ].join(";");
  return `
    <button class="canvas-element generated-asset-element ${selected}" data-element="${escapeAttribute(element.id)}" data-status="${status}" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(element.name || element.asset?.kind || "生成素材")}</span>
      ${renderElementDescription(element)}
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
      <button class="canvas-element generated-asset-element ${selected}" data-element="${escapeAttribute(element.id)}" data-status="ready" data-asset-provider="minio" style="${elementBoxStyle(element)}">
        <img src="${escapeAttribute(catalogAsset.url)}" alt="${escapeAttribute(label)}" data-asset-path="${escapeAttribute(catalogAsset.path)}" loading="lazy">
        ${renderElementDescription(element)}
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
    <button class="canvas-element generated-asset-element ${selected}" data-element="${escapeAttribute(element.id)}" data-status="${status}" data-asset-provider="minio" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(message)}</span>
      ${renderElementDescription(element)}
    </button>
  `;
}

function renderGroupElement(element) {
  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  return `
    <button class="canvas-element group-element ${selected}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)}">
      <span>${escapeHtml(element.name || "组合")}</span>
      ${renderElementDescription(element)}
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
    <button class="canvas-element unknown-element ${selected}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)};${placeholderStyle}">
      <span>${escapeHtml(element.label || element.name || "未知元素")}</span>
      ${renderElementDescription(element)}
    </button>
  `;
}

function renderSemanticIllustrationElement(element) {
  const spec = semanticIllustrationSpec(element);
  if (!spec) return "";

  const selected = state.selectedElementId === element.id ? "is-selected" : "";
  const label = getElementLabel(element);
  return `
    <button class="canvas-element illustration-element ${selected}" data-illustration="${spec.renderKey || spec.kind}" data-variant="${spec.variant || ""}" data-element="${escapeAttribute(element.id)}" style="${elementBoxStyle(element)}">
      ${renderIllustrationSvg(spec, label)}
      ${renderElementDescription(element)}
    </button>
  `;
}

function renderElementDescription(element) {
  if (!element.description) return "";
  return `<small class="element-description">${escapeHtml(element.description)}</small>`;
}

function semanticIllustrationSpec(element) {
  return catalogSpecFromRenderKey(element.metadata?.renderKey || element.metadata?.renderHint,
    element.metadata?.renderVariant);
}

function resolveCatalogAssetForElement(element) {
  const catalogItem = catalogItemForElement(element);
  const assetPath = element.metadata?.assetPath || catalogItem?.assetPath;
  if (!assetPath) return null;

  if (!catalogAssetState.failed.has(assetPath) && catalogAssetState.urls.has(assetPath)) {
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
  return renderCatalogState.byKey.get(element.metadata?.renderKey || element.metadata?.renderHint);
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

function normalizeCatalogVariant(item, variant) {
  if (!variant) return item.renderKey === "character" ? "neutral" : "";
  const normalizedVariant = item.renderKey === "character" ? normalizeCharacterVariant(variant) : String(variant);
  const variants = item.variants || [];
  if (!variants.length) return normalizedVariant;
  return variants.some((entry) => entry.key === normalizedVariant) ? normalizedVariant : variants[0]?.key || "";
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
  const description = element.description || "";

  return `
    <g class="connector-item ${selected}" data-element="${escapeAttribute(element.id)}">
      <path d="${buildConnectorPath(from, to, connector)}" fill="none" stroke="${escapeAttribute(stroke.color)}" stroke-width="${stroke.width}" stroke-linecap="round" stroke-linejoin="round" ${dash} ${markerEnd}></path>
      ${label ? `<text x="${labelPoint.x}" y="${labelPoint.y}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
      ${description ? `<text class="connector-description" x="${labelPoint.x}" y="${labelPoint.y + 18}" text-anchor="middle">${escapeHtml(description)}</text>` : ""}
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
  return `arrow-${escapeAttribute(element.id)}`;
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
  const baseFontSize = Math.max(12, getStyleNumber(element.style?.fontSize, 28));
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
  return getElementShapeKind(element);
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

