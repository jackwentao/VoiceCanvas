"""用本机 Chromium 确定性渲染可信 SVG；浏览器路径由部署配置提供。"""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from voicecanvas.application.shot_service import ShotModelError
from voicecanvas.domain.shot_preview import png_dimensions
from voicecanvas.domain.svg_document import validate_svg


def find_browser() -> str | None:
    configured = os.getenv("VOICECANVAS_RENDER_BROWSER_PATH")
    if configured:
        return configured if Path(configured).is_file() else None
    for command in ("chromium", "chromium-browser", "google-chrome", "msedge", "chrome"):
        if result := shutil.which(command):
            return result
    for base in (os.getenv("PROGRAMFILES(X86)"), os.getenv("PROGRAMFILES")):
        if base:
            path = Path(base) / "Microsoft/Edge/Application/msedge.exe"
            if path.is_file():
                return str(path)
    return None


class ChromiumShotRenderer:
    identity = "chromium-svg-1280x720-v1"

    def __init__(self, temporary_root: Path, browser_path: str | None = None):
        self.temporary_root = temporary_root
        self.browser_path = browser_path or find_browser()

    def render(self, svg: str) -> bytes:
        svg = validate_svg(svg)
        if not self.browser_path:
            raise ShotModelError("未找到渲染浏览器，请配置 VOICECANVAS_RENDER_BROWSER_PATH")
        self.temporary_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="render-", dir=self.temporary_root) as folder:
            root = Path(folder)
            source, output = root / "shot.html", root / "shot.png"
            source.write_text(
                '<!doctype html><meta charset="utf-8">'
                '<meta http-equiv="Content-Security-Policy" '
                "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
                "<style>html,body{margin:0;width:1280px;height:720px;overflow:hidden;"
                "background:white}svg{display:block;width:1280px;height:720px}</style>" + svg,
                encoding="utf-8",
            )
            command = [
                self.browser_path,
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--disable-background-networking",
                "--disable-component-update",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--window-size=1280,720",
                "--virtual-time-budget=1000",
                f"--user-data-dir={root / 'profile'}",
                f"--screenshot={output}",
                source.as_uri(),
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            check=False,
                        )
                    else:
                        import signal

                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    raise ShotModelError("镜头渲染超时，画面未被修改") from None
                if process.returncode or not output.is_file():
                    raise ShotModelError("浏览器渲染失败，画面未被修改")
                if output.stat().st_size > 8_000_000:
                    raise ShotModelError("预览图片超过 8 MB，未向模型提交图片")
                png = output.read_bytes()
                if png_dimensions(png) != (1280, 720):
                    raise ShotModelError("渲染尺寸不符，未向模型提交图片")
                return png
            except OSError as error:
                raise ShotModelError("无法启动渲染浏览器，请检查服务端浏览器配置") from error
