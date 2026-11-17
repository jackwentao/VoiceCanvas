"""浏览器集成验收专用服务：真实路由/SQLite，固定 SVG，无在线模型调用。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from voicecanvas.api import main
from voicecanvas.application.shot_service import ShotService
from voicecanvas.infrastructure.sqlite_shot_repository import SQLiteShotRepository

# 可通过环境变量将临时数据库放在 D 盘；进程退出后由 TemporaryDirectory 清理。
_data = TemporaryDirectory(prefix="voicecanvas-browser-", dir=os.getenv("VOICECANVAS_E2E_DATA_DIR"))
os.environ["VOICECANVAS_SHOT_DB_PATH"] = str(Path(_data.name) / "shots.sqlite3")
os.environ["VOICECANVAS_PROJECT_DB_PATH"] = str(Path(_data.name) / "projects.sqlite3")
os.environ["VOICECANVAS_ASSET_PROVIDER"] = "local"


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
app = main.create_app()
