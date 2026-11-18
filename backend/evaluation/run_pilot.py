"""使用生产 Agent 服务运行两个固定用例，记录快照、工具和产物。"""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

from dotenv import load_dotenv

from voicecanvas.api.storyboards import present_storyboard
from voicecanvas.application.shot_service import ShotModelError
from voicecanvas.infrastructure.shot_factory import create_storyboard_agent_service


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_case(service, source, case, out):
    historical = json.loads(source.read_text(encoding="utf-8"))
    board = service.boards.create(case)
    if case == "VC-02":
        svg = (source.parent / "before.svg").read_text(encoding="utf-8")
        board = service.boards.import_svg(board.id, board.version, "递接热咖啡", svg)
        member = historical["board"]["shots"][0]
        fields = {key: member[key] for key in ("title", "description", "camera", "durationSeconds")}
        board = service.boards.describe(
            board.id, board.version, entries=[fields], target_id=board.active_id
        )
        (out / "before.svg").write_text(svg, encoding="utf-8")
        (out / "before.png").write_bytes(service.visuals.renderer.render(svg))
    initial = present_storyboard(service.boards, board)
    write_json(out / "initial.json", initial)
    started_at = datetime.now(UTC)
    started = perf_counter()
    run = service.start(board.id, board.version, historical["run"]["request"], background=False)
    wall = round(perf_counter() - started, 3)
    snapshot = present_storyboard(service.boards, service.boards.get(board.id))
    first_save = [
        (datetime.fromisoformat(rev["createdAt"]) - started_at).total_seconds()
        for shot in snapshot["shots"]
        for rev in service.shots.get(shot["id"]).model_dump(by_alias=True)["revisions"]
        if datetime.fromisoformat(rev["createdAt"]) >= started_at
    ]
    timing = {
        "wallSeconds": wall,
        "firstSaveSeconds": round(min(first_save), 3) if first_save else None,
        "lastSaveSeconds": round(max(first_save), 3) if first_save else None,
    }
    write_json(out / "result.json", {
        "run": run.model_dump(by_alias=True), "board": snapshot, "timing": timing,
        "shotRevisions": {
            shot["id"]: service.shots.get(shot["id"]).model_dump(by_alias=True)["revisions"]
            for shot in snapshot["shots"]
        },
    })
    for index, shot in enumerate(snapshot["shots"], start=1):
        if shot["svg"]:
            stem = f"shot-{index:02}"
            (out / f"{stem}.svg").write_text(shot["svg"], encoding="utf-8")
            try:
                (out / f"{stem}.png").write_bytes(service.visuals.renderer.render(shot["svg"]))
            except ShotModelError as error:
                write_json(out / f"{stem}-render-error.json", {"error": str(error)})
    print(f"{case} {run.status} {wall:.3f}s, {len(run.steps)} tools", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, help="现有模型配置文件，可选")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["VOICECANVAS_SHOT_DB_PATH"] = str(out / "pilot.sqlite3")
    service = create_storyboard_agent_service()
    config = service.shots.generator.config
    if not all((config.base_url, config.model, config.api_key)):
        parser.error("请配置模型地址、名称和密钥")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    write_json(out / "metadata.json", {
        "commit": commit, "model": config.model, "endpointHost": urlsplit(config.base_url).hostname,
        "reasoningEffort": config.reasoning_effort, "drawingSkill": config.drawing_skill,
        "maxTokens": config.max_tokens, "timeoutSeconds": config.timeout_seconds,
        "localAddress": config.local_address,
    })
    experiments = Path(__file__).resolve().parents[2] / "docs" / "experiments"
    for case, source in (
        ("VC-01", experiments / "storyboard-agent-20261117/api-run.json"),
        ("VC-02", experiments / "shot-visual-tools-20261117/agent-run.json"),
    ):
        case_out = out / case
        case_out.mkdir()
        run_case(service, source, case, case_out)


if __name__ == "__main__":
    main()
