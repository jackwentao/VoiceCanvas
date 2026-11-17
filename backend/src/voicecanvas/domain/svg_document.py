"""完整 SVG 是镜头源文档；保留自由路径、渐变、裁剪和语义分组。"""

import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 1_000_000
TAGS = set(
    """svg g defs path rect circle ellipse line polyline polygon text tspan title desc
linearGradient radialGradient stop clipPath mask pattern symbol use filter feGaussianBlur
feOffset feFlood feComposite feMerge feMergeNode feColorMatrix feBlend feTurbulence
feDisplacementMap feComponentTransfer feFuncR feFuncG feFuncB feFuncA feMorphology""".split()
)
ATTRS = set(
    """id x y x1 y1 x2 y2 cx cy r rx ry width height viewBox preserveAspectRatio d
points transform opacity fill fill-opacity fill-rule stroke stroke-width stroke-opacity
stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset
clip-path clip-rule mask filter color style offset stop-color stop-opacity gradientUnits
gradientTransform spreadMethod fx fy fr href font-size font-family font-weight font-style
text-anchor dominant-baseline letter-spacing word-spacing dx dy textLength lengthAdjust
patternUnits patternContentUnits patternTransform clipPathUnits maskUnits maskContentUnits
filterUnits primitiveUnits in in2 result stdDeviation flood-color flood-opacity operator
k1 k2 k3 k4 mode type values scale xChannelSelector yChannelSelector baseFrequency
numOctaves seed stitchTiles slope intercept amplitude exponent tableValues radius
vector-effect paint-order visibility display color-interpolation-filters""".split()
)
ET.register_namespace("", SVG_NS)
STYLE_PROPERTIES = set(
    """fill fill-opacity fill-rule stroke stroke-width stroke-opacity
stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset
opacity color stop-color stop-opacity font-family font-size font-weight font-style
text-anchor dominant-baseline letter-spacing word-spacing paint-order visibility display
clip-path clip-rule mask filter vector-effect color-interpolation-filters""".split()
)


def validate_svg(source: str) -> str:
    """拒绝活动内容和外部资源；合法绘图保留为可重现的自包含 SVG。"""
    if len(source.encode("utf-8")) > MAX_SVG_BYTES:
        raise ValueError("SVG 超过 1 MB，请减少细节后重试")
    if re.search(r"<!|<\?", source):
        # 不接受 DTD、实体或处理指令；普通模型注释可以安全删除。
        source = re.sub(r"<!--[\s\S]*?-->", "", source)
        if re.search(r"<!|<\?", source):
            raise ValueError("SVG 不能包含文档声明或实体")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        raise ValueError("模型没有返回完整、合法的 SVG，请重试") from error
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("镜头必须是带 SVG 命名空间的完整文档")
    try:
        view_box = [float(n) for n in re.split(r"[\s,]+", root.attrib["viewBox"].strip())]
    except (KeyError, ValueError) as error:
        raise ValueError("SVG 必须提供 1280×720 的 viewBox") from error
    if view_box != [0, 0, 1280, 720] or not all(math.isfinite(n) for n in view_box):
        raise ValueError("镜头画布必须是 1280×720")
    ids: set[str] = set()
    references: set[str] = set()
    stack = [(root, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 10_000 or depth > 64:
            raise ValueError("SVG 结构过于复杂")
        tag = node.tag.removeprefix(f"{{{SVG_NS}}}")
        if tag not in TAGS or node.tag != f"{{{SVG_NS}}}{tag}":
            raise ValueError("SVG 包含不支持的内容，只允许自包含矢量绘图")
        for raw_name, value in node.attrib.items():
            name = raw_name.replace("{http://www.w3.org/1999/xlink}", "")
            if name not in ATTRS or "\\" in value or re.search(r"[<>]|[\x00-\x08]", value):
                raise ValueError("SVG 包含不支持的属性")
            if "/*" in value or re.search(
                r"@|javascript:|data:|https?:|file:|expression\s*\(", value, re.I
            ):
                raise ValueError("SVG 不能访问外部资源或执行代码")
            if name == "style":
                for declaration in value.split(";"):
                    if not declaration.strip():
                        continue
                    property_name, separator, css_value = declaration.partition(":")
                    if not separator or property_name.strip().lower() not in STYLE_PROPERTIES:
                        raise ValueError("SVG 行内样式只允许绘图属性")
                    functions = re.findall(r"([\w-]+)\s*\(", css_value)
                    if "/*" in css_value or any(
                        f.lower() not in {"url", "rgb", "rgba", "hsl", "hsla"} for f in functions
                    ):
                        raise ValueError("SVG 行内样式包含不支持的表达式")
            for match in re.finditer(r"url\s*\((.*?)\)", value, re.I | re.S):
                reference = match.group(1).strip(" \t\r\n\"'")
                if not re.fullmatch(r"#[A-Za-z_][\w.-]*", reference):
                    raise ValueError("SVG 只能引用文档内部资源")
                references.add(reference[1:])
            if name == "href":
                if not re.fullmatch(r"#[A-Za-z_][\w.-]*", value):
                    raise ValueError("SVG 只能引用文档内部对象")
                references.add(value[1:])
            if name == "id":
                if value in ids or not re.fullmatch(r"[A-Za-z_][\w.-]*", value):
                    raise ValueError("SVG 对象 id 重复或无效")
                ids.add(value)
        stack.extend((child, depth + 1) for child in node)
    if references - ids:
        raise ValueError("SVG 引用了不存在的对象")
    if not any(
        n.tag.split("}")[-1]
        in {"path", "rect", "circle", "ellipse", "text", "polygon", "polyline", "line", "use"}
        for n in root.iter()
    ):
        raise ValueError("SVG 没有可绘制内容")
    root.set("width", "1280")
    root.set("height", "720")
    return ET.tostring(root, encoding="unicode")


def apply_source_edits(source: str, edits: list[dict[str, str]]) -> str:
    """整批源码替换成功并校验后再提交；失败时不写入任何中间结果。"""
    if not edits or len(edits) > 20:
        raise ValueError("模型未返回有效修改，请换一种描述重试")
    result = source
    for edit in edits:
        old, new = edit.get("old"), edit.get("new")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ValueError("模型返回的修改格式不正确")
        if result.count(old) != 1:
            raise ValueError("修改目标不唯一，已保留原画面，请重试")
        result = result.replace(old, new, 1)
    validated = validate_svg(result)
    if validated == source:
        raise ValueError("本次没有产生画面修改")
    return validated
