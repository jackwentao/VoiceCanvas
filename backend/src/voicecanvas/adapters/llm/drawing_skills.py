"""加载随应用发布的作画知识；不执行第三方脚本，不从用户输入选择文件。"""

from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

SkillStage = Literal["draw", "edit"]
MAX_STAGE_CHARS = 4000
BUILTIN_SKILLS = {"svg-illustration": "svg_illustration"}


@dataclass(frozen=True)
class DrawingSkill:
    name: str
    draw: str
    edit: str

    def instructions(self, stage: SkillStage) -> str:
        return self.draw if stage == "draw" else self.edit


def load_drawing_skill(name: str) -> DrawingSkill | None:
    """只允许已审阅的内置 skill；显式 none 回退到原有基础提示。"""
    if name == "none":
        return None
    directory = BUILTIN_SKILLS.get(name)
    if directory is None:
        raise ValueError("未知单镜头绘图 skill，可选 svg-illustration 或 none")
    try:
        source = (
            files("voicecanvas.adapters.llm")
            .joinpath("skills", directory, "SKILL.md")
            .read_text(encoding="utf-8")
        )
    except (OSError, ModuleNotFoundError) as error:
        raise ValueError("内置绘图 skill 文件缺失，请检查后端安装包") from error
    sections = {}
    for stage in ("draw", "edit"):
        start, end = f"<!-- runtime:{stage} -->", f"<!-- /runtime:{stage} -->"
        if source.count(start) != 1 or source.count(end) != 1:
            raise ValueError("内置绘图 skill 的阶段标记无效")
        before, after = source.index(start) + len(start), source.index(end)
        text = source[before:after].strip()
        if before >= after or not text or len(text) > MAX_STAGE_CHARS:
            raise ValueError("内置绘图 skill 的指令为空或超过长度限制")
        sections[stage] = text
    return DrawingSkill(name=name, draw=sections["draw"], edit=sections["edit"])


def compose_drawing_prompt(base: str, skill: DrawingSkill | None, stage: SkillStage) -> str:
    if skill is None:
        return base
    return (
        f"已加载绘图技能 {skill.name}（{stage} 阶段）：\n"
        f"{skill.instructions(stage)}\n\n"
        "技能提供作画方法；用户明确的风格与题材优先。"
        "当前只具备文本生成能力，没有渲染器、看图工具或文件系统工具；"
        "不得声称已经渲染、看图检查或完成视觉自审，不要输出工具调用。\n"
        "以下基础协议决定输出格式、资源约束与修改范围，必须遵守：\n"
        f"{base}"
    )
