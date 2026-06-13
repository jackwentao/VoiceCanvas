import json
import os
from dataclasses import asdict, dataclass

from voicecanvas.application.orchestration_service import OrchestrationService
from voicecanvas.application.planner_factory import create_planner_from_env


@dataclass
class CrudStep:
    name: str
    user_input: str


STEPS = [
    CrudStep("创建", "创建一个三镜头的珍珠奶茶带货分镜，主打低糖和新品上市"),
    CrudStep("读取/切换", "切换到第二镜头"),
    CrudStep("新增", "加一个优惠标签，写第二杯半价"),
    CrudStep("修改", "把标题改成低糖也好喝"),
    CrudStep("删除元素", "删除标题"),
    CrudStep("删除镜头", "删除最后一个镜头"),
    CrudStep("撤销", "撤销上一步"),
    CrudStep("重做", "重做刚才那一步"),
]


def run_smoke() -> list[dict]:
    os.environ["VOICECANVAS_PLANNER"] = os.getenv("VOICECANVAS_PLANNER", "llm")
    service = OrchestrationService(planner=create_planner_from_env())
    project_id = os.getenv("VOICECANVAS_SMOKE_PROJECT_ID", "project_real_llm_crud_smoke")
    report = []

    for step in STEPS:
        response = service.handle_user_input(project_id, step.user_input)
        active_scene = next(
            scene
            for scene in response.project.scenes
            if scene.id == response.project.active_scene_id
        )
        report.append(
            {
                **asdict(step),
                "status": response.status,
                "stage": response.stage,
                "summary": response.summary.message,
                "commandCount": response.summary.command_count,
                "sceneCount": len(response.project.scenes),
                "activeScene": active_scene.name,
                "activeElementCount": len(active_scene.elements),
                "patchTypes": [patch.type.value for patch in response.patches],
                "historyCount": len(response.history),
                "eventTypes": [event.get("type") for event in response.events],
                "nextAction": response.next_action,
            }
        )

    return report


if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))
