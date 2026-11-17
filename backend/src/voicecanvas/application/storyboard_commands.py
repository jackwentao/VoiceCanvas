"""只路由完整的编排指令；自由画面描述继续交给现有绘图 Agent。"""

import re
from dataclasses import dataclass

from voicecanvas.domain.storyboard import Storyboard

NUMBER = r"[0-9零〇一二两三四五六七八九十]+"
UNIT = r"(?:个)?(?:分镜|镜头)"
TARGET = rf"(?:第?{NUMBER}{UNIT}|当前{UNIT}|这个{UNIT}|最后(?:一)?{UNIT})"


def number(value: str) -> int:
    if value.isascii() and value.isdigit():
        return int(value)
    digits = {ch: n for n, ch in enumerate("零一二三四五六七八九")}
    value = value.replace("两", "二").replace("〇", "零")
    if "十" in value:
        a, b = value.split("十", 1)
        if (a and a not in digits) or (b and b not in digits):
            raise ValueError("无法识别镜头编号")
        return (digits[a] if a else 1) * 10 + (digits[b] if b else 0)
    if len(value) != 1 or value not in digits:
        raise ValueError("无法识别镜头编号")
    return digits[value]


@dataclass
class BoardCommand:
    action: str
    target_id: str | None = None
    title: str | None = None
    position: int | None = None
    count: int = 1
    instruction: str | None = None


def _target(board: Storyboard, mention: str | None) -> str:
    if not mention or mention.startswith(("当前", "这个")):
        return board.active_id
    if mention.startswith("最后"):
        return board.state.shots[-1].id
    match = re.search(NUMBER, mention)
    if not match:
        raise ValueError("请说明镜头编号")
    position = number(match.group())
    if not 1 <= position <= len(board.state.shots):
        raise ValueError(f"当前只有 {len(board.state.shots)} 个镜头，没有第 {position} 个")
    return board.state.shots[position - 1].id


def parse_board_command(transcript: str, board: Storyboard) -> BoardCommand:
    text = transcript.strip().strip("。！!？?，,；; \n")
    text = re.sub(r"^(?:请|帮我|麻烦)(?:帮我)?", "", text).strip()
    if not text:
        raise ValueError("请说出要执行的指令")
    if text in {"取消", "取消删除", "不要删除", "算了"}:
        return BoardCommand("cancel")
    if text in {"确认删除", "确定删除"}:
        return BoardCommand("confirm")
    if text in {"新建分镜项目", "新建项目", "新建一个分镜项目"}:
        return BoardCommand("new_project")
    if text in {"导出当前镜头", "导出PNG", "导出 PNG", "导出图片"}:
        return BoardCommand("export_png")
    if text in {"导出SVG", "导出 SVG"}:
        return BoardCommand("export_svg")
    if text in {"撤销分镜操作", "撤销分镜管理", "撤销删除镜头", "恢复删除的镜头"}:
        return BoardCommand("undo")
    if text in {"重做分镜操作", "重做分镜管理"}:
        return BoardCommand("redo")
    if text in {"撤销", "撤销画面", "撤销修改"}:
        return BoardCommand("undo_shot")
    if text in {"重做", "重做画面", "重做修改"}:
        return BoardCommand("redo_shot")
    if text in {"查看分镜", "列出分镜", "有哪些镜头", "查看所有镜头"}:
        return BoardCommand("list")
    if text in {"下一个镜头", "下一个分镜", "上一镜头", "上一个镜头", "上一个分镜", "下一镜头"}:
        current = next(i for i, shot in enumerate(board.state.shots) if shot.id == board.active_id)
        position = current + (-1 if text.startswith("上") else 1)
        if not 0 <= position < len(board.state.shots):
            raise ValueError("已经是第一个镜头" if position < 0 else "已经是最后一个镜头")
        return BoardCommand("switch", board.state.shots[position].id)
    match = re.fullmatch(rf"(?:切换到?|打开|回到|选择|看)(?P<target>{TARGET})", text)
    if match:
        return BoardCommand("switch", _target(board, match["target"]))
    match = re.fullmatch(
        rf"(?:再)?(?:创建|新建|新增|添加|增加|加)(?P<count>{NUMBER})?{UNIT}"
        rf"(?:[，,:：]?(?:叫做?|命名为)(?P<title>.+))?",
        text,
    )
    if match:
        return BoardCommand(
            "add", title=match["title"], count=number(match["count"]) if match["count"] else 1
        )
    match = re.fullmatch(rf"(?:新建|新增|添加)(?:一)?{UNIT}[，,:：](?P<instruction>.+)", text)
    if match:
        return BoardCommand("add", instruction=match["instruction"])
    match = re.fullmatch(
        rf"(?:把|将)?(?P<target>{TARGET})?(?:重命名为|改名为|改名叫|命名为)(?P<title>.+)", text
    )
    if match:
        return BoardCommand(
            "rename", _target(board, match["target"]), title=match["title"].strip('“”"')
        )
    match = re.fullmatch(
        r"(?:把|将)?(?:项目|分镜项目)(?:重命名为|改名为|命名为)(?P<title>.+)", text
    )
    if match:
        return BoardCommand("rename_project", title=match["title"].strip('“”"'))
    match = re.fullmatch(
        rf"(?:把|将)?(?P<target>{TARGET})(?:移到|移至|放到|移动到)第?(?P<position>{NUMBER})(?:位|个位置|个镜头|个分镜|镜头|分镜)",
        text,
    )
    if match:
        return BoardCommand(
            "move", _target(board, match["target"]), position=number(match["position"])
        )
    match = re.fullmatch(rf"(?:把|将)?(?P<target>{TARGET})(?:前移|后移)(?:一位|一个位置)?", text)
    if match:
        target = _target(board, match["target"])
        index = next(i for i, shot in enumerate(board.state.shots) if shot.id == target)
        return BoardCommand("move", target, position=index + (0 if "前移" in text else 2))
    match = re.fullmatch(rf"(?P<action>复制|删除)(?P<target>{TARGET})?", text)
    if match:
        return BoardCommand(
            "duplicate" if match["action"] == "复制" else "request_delete",
            _target(board, match["target"]),
        )
    match = re.fullmatch(
        rf"(?:把|将)?(?P<target>第?{NUMBER}{UNIT})(?:的)?[，,:：]?"
        rf"(?P<instruction>(?:画|绘制|生成|改成|改为|修改).+)",
        text,
    )
    if match:
        return BoardCommand(
            "draw", _target(board, match["target"]), instruction=match["instruction"]
        )
    # 编排意图未识别时不误交给绘图模型，更不猜测删除目标。
    if re.match(
        r"^(?:创建|新建|新增|添加|删除|复制|切换|重命名|确认删除|移动|撤销分镜|重做分镜|导出)", text
    ) or re.match(rf"^(?:把|将)?第?{NUMBER}{UNIT}", text):
        raise ValueError("请分开说一条分镜指令，例如“切换到第二个镜头”或“删除当前镜头”")
    return BoardCommand("draw", board.active_id, instruction=transcript.strip())
