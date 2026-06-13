from typing import Any

TRANSFORM_FIELDS = {"x", "y", "width", "height"}


def merge_element_patch(before: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """合并元素补丁，并保持结构化字段与旧字段镜像同步。"""
    merged = dict(before)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    _sync_transform_mirror(merged, patch)
    _sync_layer_mirror(merged, patch)
    _sync_content_mirror(merged, patch)
    return merged


def _sync_transform_mirror(merged: dict[str, Any], patch: dict[str, Any]) -> None:
    transform = dict(merged.get("transform") or {})

    for field_name in TRANSFORM_FIELDS:
        if field_name in patch:
            transform[field_name] = patch[field_name]

    patch_transform = patch.get("transform")
    if isinstance(patch_transform, dict):
        for field_name in TRANSFORM_FIELDS:
            if field_name in patch_transform:
                merged[field_name] = patch_transform[field_name]

    if transform:
        merged["transform"] = transform


def _sync_layer_mirror(merged: dict[str, Any], patch: dict[str, Any]) -> None:
    layer = dict(merged.get("layer") or {})

    if "zIndex" in patch:
        layer["zIndex"] = patch["zIndex"]

    patch_layer = patch.get("layer")
    if isinstance(patch_layer, dict) and "zIndex" in patch_layer:
        merged["zIndex"] = patch_layer["zIndex"]

    if layer:
        merged["layer"] = layer


def _sync_content_mirror(merged: dict[str, Any], patch: dict[str, Any]) -> None:
    content = dict(merged.get("content") or {})

    if "text" in patch:
        content["text"] = patch["text"]
    if "label" in patch:
        content["label"] = patch["label"]

    patch_content = patch.get("content")
    if isinstance(patch_content, dict):
        if "text" in patch_content:
            merged["text"] = patch_content["text"]
        if "label" in patch_content:
            merged["label"] = patch_content["label"]

    if content:
        merged["content"] = content
