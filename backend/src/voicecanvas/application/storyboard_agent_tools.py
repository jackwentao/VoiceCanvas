"""向 Agent 暴露受校验的能力；此处没有自然语言句式或预设执行顺序。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ShotDescription(ToolArgs):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1600)
    duration_seconds: float | None = Field(default=None, alias="durationSeconds", gt=0, le=180)
    camera: str = Field(default="", max_length=200)


class CreateShots(ToolArgs):
    shots: list[ShotDescription] = Field(min_length=1, max_length=12)


class SetContext(ToolArgs):
    context: str = Field(min_length=1, max_length=2000)


class Target(ToolArgs):
    shot_id: str = Field(alias="shotId", min_length=1, max_length=100)


class ReviewShot(Target):
    focus: str = Field(default="", max_length=500)


class DescribeShot(ShotDescription, Target):
    pass


class DrawShot(Target):
    instruction: str = Field(min_length=1, max_length=1800)
    reason: str = Field(min_length=1, max_length=300)


class Manage(ToolArgs):
    action: Literal[
        "add", "switch", "rename", "rename_project", "move", "duplicate", "undo", "redo"
    ]
    shot_id: str | None = Field(default=None, alias="shotId", max_length=100)
    title: str | None = Field(default=None, max_length=100)
    position: int | None = Field(default=None, ge=1, le=40)
    count: int = Field(default=1, ge=1, le=12)


class MoveHistory(Target):
    direction: Literal["undo", "redo"]


class ExportShots(ToolArgs):
    shot_ids: list[str] = Field(alias="shotIds", min_length=1, max_length=40)
    format: Literal["png", "svg"]


class FinishTask(ToolArgs):
    summary: str = Field(min_length=1, max_length=1800)
    shot_ids: list[str] = Field(default_factory=list, alias="shotIds", max_length=40)
    expected_count: int = Field(default=0, alias="expectedCount", ge=0, le=40)
    expected_duration: float | None = Field(default=None, alias="expectedDuration", gt=0, le=7200)
    unresolved: list[str] = Field(default_factory=list, max_length=12)


TOOL_SPECS = {
    "get_storyboard": (ToolArgs, "读取实际镜头顺序、共用设定、每镜说明/时长和画面状态。"),
    "set_context": (SetContext, "保存项目共用角色外观、服装、场景和画风；后续绘图自动携带。"),
    "create_shots": (CreateShots, "按你自主决定的拆镜方案创建独立镜头；初始唯一空镜头会被复用。"),
    "describe_shot": (DescribeShot, "保存或修订指定镜头的拍摄说明、时长、景别，不重画。"),
    "manage_storyboard": (Manage, "按稳定镜头 id 新增、切换、重命名、移动、复制或撤销结构。"),
    "inspect_shot": (Target, "读取某镜 SVG 源码与文字，供必要的源码检查；这不代表看到了画面。"),
    "render_shot": (
        Target,
        "把指定镜头的当前 SVG 用确定性浏览器渲染为真实 PNG，供视觉模型检查；不会修改画面。",
    ),
    "review_shot": (
        ReviewShot,
        "让同一个模型查看当前镜头 PNG，并对照本镜要求指出可观察的动作、构图、文字和外观偏差；"
        "不能把评审当成自动通过。无需先调用 render_shot；会复用或生成当前版本的预览。",
    ),
    "draw_shot": (DrawShot, "自由生成或局部改画指定镜头；已有图则修改；必须说明本次原因。"),
    "move_shot_history": (MoveHistory, "撤销或重做指定镜头的画面版本。"),
    "delete_shot": (Target, "提出删除，绑定镜头与版本等待用户确认；模型不能自行授予确认。"),
    "export_shots": (ExportShots, "请求浏览器下载指定镜头，支持单镜或多镜；浏览器执行后才算下载。"),
    "finish_task": (
        FinishTask,
        "确认交付：列出本次输出的镜头 id、需求数量和总时长；服务端核实画面存在与数量时长。"
        "尚有疑问填 unresolved，不得把保存成功说成动作已通过视觉验收。",
    ),
}


def agent_tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": model.model_json_schema(),
            },
        }
        for name, (model, description) in TOOL_SPECS.items()
    ]
