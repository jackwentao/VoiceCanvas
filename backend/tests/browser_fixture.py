"""浏览器集成验收专用服务：真实路由/SQLite，固定 SVG，无在线模型调用。"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from voicecanvas.api import main
from voicecanvas.application.shot_service import ShotService
from voicecanvas.application.storyboard_agent_service import StoryboardAgentService
from voicecanvas.domain.storyboard_agent import AgentDecision, AgentToolCall
from voicecanvas.infrastructure.sqlite_agent_run_repository import SQLiteAgentRunRepository
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository

# 可通过环境变量将临时数据库放在 D 盘；进程退出后由 TemporaryDirectory 清理。
_data = TemporaryDirectory(prefix="voicecanvas-browser-", dir=os.getenv("VOICECANVAS_E2E_DATA_DIR"))
os.environ["VOICECANVAS_SHOT_DB_PATH"] = str(Path(_data.name) / "shots.sqlite3")


class FixtureGenerator:
    def generate(self, instruction, current_svg):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#243b36"/>'
            '<text x="100" y="200" fill="white" font-size="48">到家了吗？</text></svg>'
        )
        return current_svg or svg, {}, "browser-fixture"


main.create_shot_service = lambda: ShotService(
    SQLiteShotRepository(Path(os.environ["VOICECANVAS_SHOT_DB_PATH"])), FixtureGenerator()
)


class FixtureAgent:
    """仅供既有浏览器脚本的明确测试样例；不是生产自然语言路由或降级。"""

    def decide(self, messages, tools):
        initial = json.loads(messages[1]["content"])
        text, board = initial["request"], initial["storyboard"]
        if len(messages) > 2:
            name, args = "finish_task", {"summary": "测试操作已执行"}
            if text == "画一个雨夜镜头":
                args.update(shotIds=[board["activeId"]], expectedCount=1)
        elif text == "新建两个镜头":
            name, args = "manage_storyboard", {"action": "add", "count": 2}
        elif text in {"切换到第一个镜头", "切换到第二个镜头"}:
            index = 0 if text == "切换到第一个镜头" else 1
            name, args = (
                "manage_storyboard",
                {"action": "switch", "shotId": board["shots"][index]["id"]},
            )
        elif text == "把第二个镜头移到第一位":
            name, args = (
                "manage_storyboard",
                {"action": "move", "shotId": board["shots"][1]["id"], "position": 1},
            )
        elif text in {"删除当前镜头", "确认删除"}:
            target = (
                initial["previous"]["pendingDelete"]["shotId"]
                if text == "确认删除"
                else board["activeId"]
            )
            name, args = "delete_shot", {"shotId": target}
        elif text == "画一个雨夜镜头":
            name, args = (
                "draw_shot",
                {"shotId": board["activeId"], "instruction": text, "reason": "离线测试"},
            )
        else:
            raise ValueError("浏览器替身仅接受脚本明确列出的样例")
        return AgentDecision(
            calls=[AgentToolCall(id=f"fixture_{len(messages)}", name=name, arguments=args)]
        ), {}


main.create_storyboard_agent_service = lambda: StoryboardAgentService(
    main.create_storyboard_service(),
    main.create_shot_service(),
    FixtureAgent(),
    SQLiteAgentRunRepository(Path(os.environ["VOICECANVAS_SHOT_DB_PATH"])),
)
app = main.create_app()
