/**
 * 基础图形统一渲染器。
 *
 * 画布预览与 SVG 导出必须复用这里的几何定义，避免同一种 shape.kind
 * 在不同出口被渲染成不同图形。新增图形时只需要扩展 SHAPE_BUILDERS 和别名表。
 */

export const BASIC_SHAPE_KINDS = Object.freeze([
  "rectangle",
  "rounded_rectangle",
  "square",
  "circle",
  "ellipse",
  "triangle",
  "diamond",
  "pentagon",
  "hexagon",
  "heptagon",
  "octagon",
  "nonagon",
  "decagon",
  "hendecagon",
  "dodecagon",
  "star",
  "line",
  "pill",
  "badge",
  "trapezoid",
  "parallelogram",
  "arrow"
]);

const SHAPE_KIND_ALIASES = Object.freeze({
  rect: "rectangle",
  long_rectangle: "rectangle",
  round_rectangle: "rounded_rectangle",
  rounded_rect: "rounded_rectangle",
  round_rect: "rounded_rectangle",
  oval: "ellipse",
  rhombus: "diamond",
  five_point_star: "star",
  fivepoint_star: "star",
  seal: "badge",
  capsule: "pill",
  straight_line: "line",
  right_arrow: "arrow",
  三角形: "triangle",
  长方形: "rectangle",
  矩形: "rectangle",
  圆角矩形: "rounded_rectangle",
  正方形: "square",
  圆形: "circle",
  椭圆形: "ellipse",
  菱形: "diamond",
  五边形: "pentagon",
  六边形: "hexagon",
  七边形: "heptagon",
  八边形: "octagon",
  九边形: "nonagon",
  十边形: "decagon",
  十一边形: "hendecagon",
  十二边形: "dodecagon",
  星形: "star",
  直线: "line",
  胶囊: "pill",
  徽章: "badge",
  梯形: "trapezoid",
  平行四边形: "parallelogram",
  箭头: "arrow"
});

const SUPPORTED_SHAPE_KINDS = new Set(BASIC_SHAPE_KINDS);

export function normalizeShapeKind(value) {
  const normalized = String(value || "rectangle")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return SHAPE_KIND_ALIASES[normalized] || normalized;
}

export function getElementShapeKind(element) {
  const rawShape = element?.shape;
  const normalized = normalizeShapeKind(rawShape?.kind || rawShape || "rectangle");
  if (!["polygon", "regular_polygon", "regularpolygon"].includes(normalized)) {
    return normalized;
  }

  return inferPolygonKind({
    sides: rawShape?.sides ?? rawShape?.sideCount ?? element?.sides,
    text: [
      element?.name,
      element?.content?.label,
      element?.label,
      element?.description
    ].filter(Boolean).join(" ")
  }) || normalized;
}

export function isBasicShapeKind(kind) {
  return SUPPORTED_SHAPE_KINDS.has(normalizeShapeKind(kind));
}

export function shapeToInlineSvg(options = {}) {
  const width = positiveNumber(options.width, 100);
  const height = positiveNumber(options.height, 100);
  const kind = normalizeShapeKind(options.kind);
  const supported = isBasicShapeKind(kind);
  const className = options.className || "shape-geometry";
  const geometry = shapeGeometryToSvg({
    ...options,
    kind,
    x: 0,
    y: 0,
    width,
    height
  });

  return `<svg class="${escapeAttribute(className)}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true" focusable="false" data-shape-kind="${escapeAttribute(kind)}" data-shape-supported="${supported}">
    ${geometry}
  </svg>`;
}

export function shapeGeometryToSvg(options = {}) {
  const kind = normalizeShapeKind(options.kind);
  const bounds = {
    x: finiteNumber(options.x, 0),
    y: finiteNumber(options.y, 0),
    width: positiveNumber(options.width, 100),
    height: positiveNumber(options.height, 100)
  };
  const appearance = {
    fill: escapeAttribute(options.fill || "#ffffff"),
    stroke: escapeAttribute(options.stroke || "#243b53"),
    strokeWidth: positiveNumber(options.strokeWidth, 1),
    dash: normalizeDash(options.dash),
    cornerRadius: Math.max(0, finiteNumber(options.cornerRadius, 8))
  };
  const builder = SHAPE_BUILDERS[kind];
  if (!builder) return unsupportedShapeToSvg(bounds, appearance, kind);
  return builder(bounds, appearance);
}

const SHAPE_BUILDERS = Object.freeze({
  rectangle: (bounds, appearance) =>
    rectToSvg(bounds, appearance, 0),
  rounded_rectangle: (bounds, appearance) =>
    rectToSvg(
      bounds,
      appearance,
      Math.min(
        appearance.cornerRadius || Math.min(bounds.width, bounds.height) * 0.12,
        Math.min(bounds.width, bounds.height) / 2
      )
    ),
  square: (bounds, appearance) => {
    const square = centeredSquare(bounds);
    return rectToSvg(square, appearance, 0);
  },
  circle: (bounds, appearance) => {
    const radius = Math.max(0, Math.min(bounds.width, bounds.height) / 2 - shapePadding(bounds));
    return `<circle cx="${bounds.x + bounds.width / 2}" cy="${bounds.y + bounds.height / 2}" r="${radius}" ${paintAttributes(appearance)}/>`;
  },
  ellipse: (bounds, appearance) => {
    const padding = shapePadding(bounds);
    return `<ellipse cx="${bounds.x + bounds.width / 2}" cy="${bounds.y + bounds.height / 2}" rx="${Math.max(0, bounds.width / 2 - padding)}" ry="${Math.max(0, bounds.height / 2 - padding)}" ${paintAttributes(appearance)}/>`;
  },
  triangle: (bounds, appearance) =>
    polygonToSvg(
      [
        [bounds.x + bounds.width / 2, bounds.y + shapePadding(bounds)],
        [bounds.x + bounds.width - shapePadding(bounds), bounds.y + bounds.height - shapePadding(bounds)],
        [bounds.x + shapePadding(bounds), bounds.y + bounds.height - shapePadding(bounds)]
      ],
      appearance
    ),
  diamond: (bounds, appearance) =>
    polygonToSvg(
      [
        [bounds.x + bounds.width / 2, bounds.y + shapePadding(bounds)],
        [bounds.x + bounds.width - shapePadding(bounds), bounds.y + bounds.height / 2],
        [bounds.x + bounds.width / 2, bounds.y + bounds.height - shapePadding(bounds)],
        [bounds.x + shapePadding(bounds), bounds.y + bounds.height / 2]
      ],
      appearance
    ),
  pentagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 5),
  hexagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 6),
  heptagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 7),
  octagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 8),
  nonagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 9),
  decagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 10),
  hendecagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 11),
  dodecagon: (bounds, appearance) => regularPolygonToSvg(bounds, appearance, 12),
  star: (bounds, appearance) => starPolygonToSvg(bounds, appearance, 5, 0.44),
  line: (bounds, appearance) => {
    const padding = shapePadding(bounds);
    return `<line x1="${bounds.x + padding}" y1="${bounds.y + bounds.height / 2}" x2="${bounds.x + bounds.width - padding}" y2="${bounds.y + bounds.height / 2}" ${strokeAttributes(appearance)} stroke-linecap="round"/>`;
  },
  pill: (bounds, appearance) =>
    rectToSvg(bounds, appearance, Math.min(bounds.width, bounds.height) / 2),
  badge: (bounds, appearance) => starPolygonToSvg(bounds, appearance, 12, 0.82),
  trapezoid: (bounds, appearance) => {
    const padding = shapePadding(bounds);
    return polygonToSvg(
      [
        [bounds.x + bounds.width * 0.25, bounds.y + padding],
        [bounds.x + bounds.width * 0.75, bounds.y + padding],
        [bounds.x + bounds.width - padding, bounds.y + bounds.height - padding],
        [bounds.x + padding, bounds.y + bounds.height - padding]
      ],
      appearance
    );
  },
  parallelogram: (bounds, appearance) => {
    const padding = shapePadding(bounds);
    const skew = Math.min(bounds.width * 0.22, bounds.height * 0.45);
    return polygonToSvg(
      [
        [bounds.x + padding + skew, bounds.y + padding],
        [bounds.x + bounds.width - padding, bounds.y + padding],
        [bounds.x + bounds.width - padding - skew, bounds.y + bounds.height - padding],
        [bounds.x + padding, bounds.y + bounds.height - padding]
      ],
      appearance
    );
  },
  arrow: (bounds, appearance) => {
    const padding = shapePadding(bounds);
    const left = bounds.x + padding;
    const right = bounds.x + bounds.width - padding;
    const top = bounds.y + padding;
    const bottom = bounds.y + bounds.height - padding;
    const middle = bounds.y + bounds.height / 2;
    const neck = bounds.x + bounds.width * 0.58;
    return polygonToSvg(
      [
        [left, bounds.y + bounds.height * 0.34],
        [neck, bounds.y + bounds.height * 0.34],
        [neck, top],
        [right, middle],
        [neck, bottom],
        [neck, bounds.y + bounds.height * 0.66],
        [left, bounds.y + bounds.height * 0.66]
      ],
      appearance
    );
  }
});

function rectToSvg(bounds, appearance, radius) {
  const padding = shapePadding(bounds);
  return `<rect x="${bounds.x + padding}" y="${bounds.y + padding}" width="${Math.max(0, bounds.width - padding * 2)}" height="${Math.max(0, bounds.height - padding * 2)}" rx="${radius}" ry="${radius}" ${paintAttributes(appearance)}/>`;
}

function regularPolygonToSvg(bounds, appearance, sides) {
  return polygonToSvg(radialPoints(bounds, sides, 1), appearance);
}

function starPolygonToSvg(bounds, appearance, points, innerRatio) {
  return polygonToSvg(radialPoints(bounds, points * 2, innerRatio), appearance);
}

function radialPoints(bounds, count, innerRatio) {
  const padding = shapePadding(bounds);
  const radiusX = Math.max(0, bounds.width / 2 - padding);
  const radiusY = Math.max(0, bounds.height / 2 - padding);
  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count;
    const radiusRatio = count % 2 === 0 && index % 2 === 1 ? innerRatio : 1;
    return [
      centerX + Math.cos(angle) * radiusX * radiusRatio,
      centerY + Math.sin(angle) * radiusY * radiusRatio
    ];
  });
}

function polygonToSvg(points, appearance) {
  const serialized = points.map(([x, y]) => `${round(x)},${round(y)}`).join(" ");
  return `<polygon points="${serialized}" ${paintAttributes(appearance)} stroke-linejoin="round"/>`;
}

function unsupportedShapeToSvg(bounds, appearance, kind) {
  const fallback = {
    ...appearance,
    fill: "none",
    dash: appearance.dash || "8 6"
  };
  const padding = shapePadding(bounds);
  return `<g data-unsupported-shape="${escapeAttribute(kind)}">
    <rect x="${bounds.x + padding}" y="${bounds.y + padding}" width="${Math.max(0, bounds.width - padding * 2)}" height="${Math.max(0, bounds.height - padding * 2)}" rx="6" ${paintAttributes(fallback)}/>
    <path d="M ${bounds.x + bounds.width * 0.32} ${bounds.y + bounds.height * 0.32} L ${bounds.x + bounds.width * 0.68} ${bounds.y + bounds.height * 0.68} M ${bounds.x + bounds.width * 0.68} ${bounds.y + bounds.height * 0.32} L ${bounds.x + bounds.width * 0.32} ${bounds.y + bounds.height * 0.68}" ${strokeAttributes(appearance)} stroke-linecap="round"/>
  </g>`;
}

function paintAttributes(appearance) {
  return `fill="${appearance.fill}" ${strokeAttributes(appearance)}`;
}

function strokeAttributes(appearance) {
  const dash = appearance.dash ? ` stroke-dasharray="${escapeAttribute(appearance.dash)}"` : "";
  return `stroke="${appearance.stroke}" stroke-width="${appearance.strokeWidth}" vector-effect="non-scaling-stroke"${dash}`;
}

function centeredSquare(bounds) {
  const size = Math.min(bounds.width, bounds.height);
  return {
    x: bounds.x + (bounds.width - size) / 2,
    y: bounds.y + (bounds.height - size) / 2,
    width: size,
    height: size
  };
}

function shapePadding(bounds) {
  return Math.max(1, Math.min(bounds.width, bounds.height) * 0.025);
}

function normalizeDash(value) {
  if (Array.isArray(value)) return value.map((item) => finiteNumber(item, 0)).join(" ");
  return value ? String(value) : "";
}

function inferPolygonKind({ sides, text }) {
  const sideCount = Number(sides);
  const kindBySides = {
    3: "triangle",
    4: "square",
    5: "pentagon",
    6: "hexagon",
    7: "heptagon",
    8: "octagon",
    9: "nonagon",
    10: "decagon",
    11: "hendecagon",
    12: "dodecagon"
  };
  if (kindBySides[sideCount]) return kindBySides[sideCount];

  const normalizedText = String(text || "").toLowerCase().replace(/[\s_-]+/g, "");
  if (!normalizedText) return null;
  if (/(五角星|五星|5pointstar|fivepointstar|star)/.test(normalizedText)) return "star";
  if (/(三角形|三边形|3边形|3sided|triangle)/.test(normalizedText)) return "triangle";
  if (/(四边形|正四边形|4边形|4sided|quadrilateral)/.test(normalizedText)) return "square";
  if (/(五边形|五角形|5边形|5sided|pentagon|pentagonal)/.test(normalizedText)) return "pentagon";
  if (/(六边形|六角形|6边形|6sided|hexagon|hexagonal)/.test(normalizedText)) return "hexagon";
  if (/(七边形|七角形|7边形|7sided|heptagon|heptagonal)/.test(normalizedText)) return "heptagon";
  if (/(八边形|八角形|8边形|8sided|octagon|octagonal)/.test(normalizedText)) return "octagon";
  if (/(九边形|九角形|9边形|9sided|nonagon|nonagonal)/.test(normalizedText)) return "nonagon";
  if (/(十边形|十角形|10边形|10sided|decagon|decagonal)/.test(normalizedText)) return "decagon";
  if (/(十一边形|11边形|11sided|hendecagon|undecagon)/.test(normalizedText)) return "hendecagon";
  if (/(十二边形|12边形|12sided|dodecagon)/.test(normalizedText)) return "dodecagon";
  if (/(菱形|钻石形|diamond|rhombus)/.test(normalizedText)) return "diamond";
  return null;
}

function positiveNumber(value, fallback) {
  const number = finiteNumber(value, fallback);
  return number > 0 ? number : fallback;
}

function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function round(value) {
  return Math.round(value * 1000) / 1000;
}

function escapeAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
