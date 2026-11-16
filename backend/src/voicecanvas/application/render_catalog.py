"""语义渲染能力目录。

这个模块把“VoiceCanvas 原型现在到底能直接画什么”从 LLM prompt、
命令归一化和前端 renderer 中解耦出来。目录是数据，匹配/提示词是能力。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderCatalogMatch:
    render_key: str
    display_name: str
    asset_kind: str
    subject_type: str
    direct_render: bool
    variant: str | None = None
    variant_label: str | None = None
    category: str | None = None
    asset_provider: str | None = None
    asset_path: str | None = None
    style_family: str | None = None
    attributes: dict[str, list[str]] | None = None


class RenderCatalog:
    """查询前后端共享的本地绘制能力。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.items: list[dict[str, Any]] = list(data.get("items", []))

    @classmethod
    def load_default(cls) -> RenderCatalog:
        catalog_path = Path(__file__).resolve().parents[1] / "resources" / "render-catalog.json"
        with catalog_path.open("r", encoding="utf-8") as file:
            return cls(json.load(file))

    def resolve(self, text: str | None) -> RenderCatalogMatch | None:
        normalized_text = _normalize_text(text)
        if not normalized_text:
            return None

        best: RenderCatalogMatch | None = None
        best_score = 0
        for item in self.items:
            item_match = self._match_item(item, normalized_text)
            if item_match is None:
                continue
            score, match = item_match
            if score > best_score:
                best = match
                best_score = score
        return best

    def prompt_manifest(self) -> str:
        """给 LLM 的紧凑能力清单，避免它臆造前端能直接绘制的对象。"""

        lines: list[str] = []
        for item in self.items:
            variants = item.get("variants") or []
            variant_text = ""
            if variants:
                variant_text = "；variants=" + ",".join(
                    str(variant.get("key")) for variant in variants
                )
            mode = "direct" if item.get("directRender") else "placeholder"
            if item.get("assetProvider") and item.get("assetPath"):
                mode = str(item.get("assetProvider"))
            aliases = ",".join(str(alias) for alias in item.get("aliases", [])[:6])
            asset_path = f"; assetPath={item.get('assetPath')}" if item.get("assetPath") else ""
            lines.append(
                f"- {item.get('renderKey')}({item.get('displayName')}): "
                f"{mode}{variant_text}{asset_path}; aliases={aliases}"
            )
        return "\n".join(lines)

    def _match_item(self, item: dict[str, Any], text: str) -> tuple[int, RenderCatalogMatch] | None:
        base_aliases = [item.get("renderKey"), item.get("displayName"), *item.get("aliases", [])]
        base_score = _best_alias_score(text, base_aliases)
        variant_score = 0
        variant_key: str | None = None
        variant_label: str | None = None
        for variant in item.get("variants", []) or []:
            score = _best_alias_score(
                text,
                [variant.get("key"), variant.get("displayName"), *variant.get("aliases", [])],
            )
            if score > variant_score:
                variant_score = score
                variant_key = str(variant.get("key")) if variant.get("key") else None
                variant_label = (
                    str(variant.get("displayName")) if variant.get("displayName") else None
                )

        score = max(base_score, variant_score)
        if score <= 0:
            return None

        return score, RenderCatalogMatch(
            render_key=str(item.get("renderKey")),
            display_name=variant_label or str(item.get("displayName") or item.get("renderKey")),
            asset_kind=str(item.get("assetKind") or "illustration"),
            subject_type=str(item.get("subjectType") or "object"),
            direct_render=bool(item.get("directRender")),
            variant=variant_key,
            variant_label=variant_label,
            category=str(item.get("category")) if item.get("category") else None,
            asset_provider=str(item.get("assetProvider")) if item.get("assetProvider") else None,
            asset_path=str(item.get("assetPath")) if item.get("assetPath") else None,
            style_family=str(item.get("styleFamily")) if item.get("styleFamily") else None,
            attributes=_extract_supported_attributes(text, item),
        )


@lru_cache(maxsize=1)
def get_render_catalog() -> RenderCatalog:
    return RenderCatalog.load_default()


def _normalize_text(text: str | None) -> str:
    return str(text or "").strip().lower()


def _best_alias_score(text: str, aliases: list[Any]) -> int:
    score = 0
    for alias in aliases:
        normalized_alias = _normalize_text(str(alias or ""))
        if not normalized_alias:
            continue
        if normalized_alias == text:
            score = max(score, 1000 + len(normalized_alias))
        elif normalized_alias in text:
            score = max(score, 100 + len(normalized_alias))
    return score


def _extract_supported_attributes(text: str, item: dict[str, Any]) -> dict[str, list[str]]:
    attributes: dict[str, list[str]] = {}
    for attribute in item.get("supportedAttributes", []) or []:
        if not isinstance(attribute, dict):
            continue
        key = str(attribute.get("key") or "").strip()
        if not key:
            continue
        matches: list[str] = []
        for alias in attribute.get("aliases", []) or []:
            normalized_alias = _normalize_text(str(alias or ""))
            if normalized_alias and normalized_alias in text:
                matches.append(str(alias))
        if matches:
            attributes[key] = matches
    return attributes
