"""SVG 文字块的确定性修改；字体测量与界面留在浏览器边界。"""

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from voicecanvas.domain.svg_document import SVG_NS, validate_svg

TEXT = f"{{{SVG_NS}}}text"
TSPAN = f"{{{SVG_NS}}}tspan"
HIDDEN_CONTAINERS = {f"{{{SVG_NS}}}{tag}" for tag in ("defs", "symbol", "clipPath", "mask")}


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px)?", value):
        return None
    number = float(value.removesuffix("px"))
    return number if math.isfinite(number) else None


def _lines(node: ET.Element) -> list[str]:
    if not len(node):
        return [(node.text or "").replace("\r", "")]
    lines = [node.text] if node.text and node.text.strip() else []
    for child in node:
        value = "".join(child.itertext())
        new_line = any(key in child.attrib for key in ("x", "y")) or (
            _number(child.get("dy")) not in (None, 0)
        )
        if new_line or not lines:
            lines.append(value)
        else:
            lines[-1] += value
        if child.tail and child.tail.strip():
            lines[-1] += child.tail
    return lines or [""]


def _reason(node: ET.Element, parents: dict[ET.Element, ET.Element], references: set[str]) -> str:
    ancestor: ET.Element | None = node
    while ancestor is not None:
        if ancestor.get("id") in references:
            return "此文字被其他对象共享引用，请通过自然语言修改"
        if ancestor.tag in HIDDEN_CONTAINERS:
            return "共享定义中的文字，请通过自然语言修改"
        if ancestor.get("display") == "none" or ancestor.get("visibility") == "hidden":
            return "此文字当前不可见"
        ancestor = parents.get(ancestor)
    if any(key in node.attrib for key in ("textLength", "lengthAdjust")):
        return "此文字使用特殊字距布局，请通过自然语言修改"
    for child in node:
        if child.tag != TSPAN or len(child) or set(child.attrib) - {"x", "y", "dx", "dy"}:
            return "此文字包含混合字形或样式，请通过自然语言修改"
        if _number(child.get("dx")) not in (None, 0):
            return "此文字使用独立字符定位，请通过自然语言修改"
        if any(_number(value) is None for value in child.attrib.values()):
            return "此文字使用特殊坐标，请通过自然语言修改"
    for name in ("x", "y", "dx", "dy"):
        if name in node.attrib and _number(node.get(name)) is None:
            return "此文字使用特殊坐标，请通过自然语言修改"
    return ""


@dataclass
class TextBlock:
    index: int
    nodes: list[ET.Element]
    lines: list[str]
    reason: str


def _blocks(root: ET.Element) -> list[TextBlock]:
    parents = {child: node for node in root.iter() for child in node}
    nodes = [node for node in root.iter() if node.tag == TEXT]
    references = set()
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.endswith("href"):
                references.add(value.removeprefix("#"))
            references.update(re.findall(r"url\(['\"]?#([\w.-]+)", value))
    blocks: list[TextBlock] = []
    for index, node in enumerate(nodes):
        reason = _reason(node, parents, references)
        # 只合并同一父节点内连续、同样式、同横向锚点的无 id 文本行。
        # 其余文本保持独立，避免把联系人、时间、正文误合成一个段落。
        previous = blocks[-1].nodes[-1] if blocks else None
        merge = False
        if previous is not None and not reason and not blocks[-1].reason:
            parent = parents.get(node)
            if parent is not None and parents.get(previous) is parent:
                children = list(parent)
                a, b = _number(previous.get("y")), _number(node.get("y"))
                x1, x2 = _number(previous.get("x", "0")), _number(node.get("x", "0"))

                def attrs(el: ET.Element) -> dict[str, str]:
                    return {k: v for k, v in el.attrib.items() if k not in {"x", "y"}}

                size = _number(node.get("font-size")) or 16
                merge = (
                    not len(previous)
                    and not len(node)
                    and not previous.get("id")
                    and not node.get("id")
                    and children.index(node) == children.index(previous) + 1
                    and attrs(previous) == attrs(node)
                    and a is not None
                    and b is not None
                    and 0.7 * size <= b - a <= 3.5 * size
                    and x1 is not None
                    and x2 is not None
                    and abs(x1 - x2) <= 2
                )
        if merge:
            blocks[-1].nodes.append(node)
            blocks[-1].lines.extend(_lines(node))
        else:
            blocks.append(TextBlock(index, [node], _lines(node), reason))
    return blocks


def list_text_blocks(source: str | None) -> list[dict]:
    if not source:
        return []
    root = ET.fromstring(source)
    return [
        {
            "index": block.index,
            "indices": [i for i, n in enumerate(root.iter(TEXT)) if n in block.nodes],
            "text": "\n".join(block.lines),
            "editable": not block.reason,
            "reason": block.reason,
        }
        for block in _blocks(root)
    ]


def replace_text_block(
    source: str,
    index: int,
    lines: list[str],
    font_size: float,
    line_height: float,
    y: float,
) -> str:
    if not 1 <= len(lines) <= 100 or not all(isinstance(line, str) for line in lines):
        raise ValueError("文字行数必须在 1–100 行之间")
    if sum(len(line) for line in lines) > 2000 or not "".join(lines).strip():
        raise ValueError("请输入 1–2000 字的文字")
    if any("\n" in line or "\r" in line for line in lines):
        raise ValueError("请按行提交文字")
    if not all(math.isfinite(v) for v in (font_size, line_height, y)):
        raise ValueError("文字布局参数必须是有限数值")
    if not 8 <= font_size <= 160 or not 1 <= line_height <= 3 or not -10000 <= y <= 10000:
        raise ValueError("字号或行距超出可编辑范围")
    root = ET.fromstring(validate_svg(source))
    block = next((block for block in _blocks(root) if block.index == index), None)
    if block is None or block.reason:
        raise ValueError(block.reason if block else "文字目标不存在，请刷新后重试")
    node = block.nodes[0]
    x = node.get("x", "0")
    if len(node) and node[0].get("x") is not None:
        x = node[0].attrib["x"]
    for child in list(node):
        node.remove(child)
    node.text = None
    # style 的 font-size 优先于同名 SVG 属性，只移除该项，保留其余绘图样式。
    if "style" in node.attrib:
        style = ";".join(
            part
            for part in node.attrib["style"].split(";")
            if part.partition(":")[0].strip().lower() != "font-size"
        )
        node.set("style", style)
    node.set("font-size", f"{font_size:g}")
    node.set("x", x)
    node.set("y", f"{y:g}")
    for row, line in enumerate(lines):
        span = ET.SubElement(
            node, TSPAN, {"x": x, "dy": "0" if row == 0 else f"{font_size * line_height:g}"}
        )
        span.text = line
    parents = {child: parent for parent in root.iter() for child in parent}
    for extra in block.nodes[1:]:
        parents[extra].remove(extra)
    result = validate_svg(ET.tostring(root, encoding="unicode"))
    if result == source:
        raise ValueError("本次没有产生文字修改")
    return result
