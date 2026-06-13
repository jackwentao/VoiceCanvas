const TRANSFORM_FIELDS = ["x", "y", "width", "height"];

export function mergeElementPatch(element, patch) {
  const merged = { ...element };

  for (const [key, value] of Object.entries(patch || {})) {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = { ...merged[key], ...value };
    } else {
      merged[key] = value;
    }
  }

  syncTransformMirror(merged, patch || {});
  syncLayerMirror(merged, patch || {});
  syncContentMirror(merged, patch || {});
  return merged;
}

function syncTransformMirror(merged, patch) {
  const transform = { ...(merged.transform || {}) };

  for (const field of TRANSFORM_FIELDS) {
    if (field in patch) transform[field] = patch[field];
  }

  if (isPlainObject(patch.transform)) {
    for (const field of TRANSFORM_FIELDS) {
      if (field in patch.transform) merged[field] = patch.transform[field];
    }
  }

  if (Object.keys(transform).length > 0) merged.transform = transform;
}

function syncLayerMirror(merged, patch) {
  const layer = { ...(merged.layer || {}) };

  if ("zIndex" in patch) layer.zIndex = patch.zIndex;
  if (isPlainObject(patch.layer) && "zIndex" in patch.layer) merged.zIndex = patch.layer.zIndex;

  if (Object.keys(layer).length > 0) merged.layer = layer;
}

function syncContentMirror(merged, patch) {
  const content = { ...(merged.content || {}) };

  if ("text" in patch) content.text = patch.text;
  if ("label" in patch) content.label = patch.label;

  if (isPlainObject(patch.content)) {
    if ("text" in patch.content) merged.text = patch.content.text;
    if ("label" in patch.content) merged.label = patch.content.label;
  }

  if (Object.keys(content).length > 0) merged.content = content;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
