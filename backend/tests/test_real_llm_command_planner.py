import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from voicecanvas.adapters.llm.openai_compatible import OpenAICompatibleLLMClient
from voicecanvas.application.command_executor import CommandExecutor
from voicecanvas.application.demo_command_planner import DemoCommandPlanner
from voicecanvas.application.llm_command_planner import LLMCommandPlanner
from voicecanvas.application.project_repository import InMemoryProjectRepository

load_dotenv()

pytestmark = pytest.mark.skipif(
    os.getenv("VOICECANVAS_RUN_REAL_LLM_TESTS") != "1",
    reason="真实 LLM 测试默认跳过；设置 VOICECANVAS_RUN_REAL_LLM_TESTS=1 后运行",
)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"缺少环境变量：{name}")
    return value


def _artifact_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    root = Path(os.getenv("VOICECANVAS_LLM_ARTIFACT_DIR", backend_dir / "artifacts" / "llm"))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / timestamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client() -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(
        base_url=_required_env("VOICECANVAS_LLM_BASE_URL"),
        model=_required_env("VOICECANVAS_LLM_MODEL"),
        api_key=os.getenv("VOICECANVAS_LLM_API_KEY"),
        provider=os.getenv("VOICECANVAS_LLM_PROVIDER", "openai-compatible"),
    )


def _planner() -> LLMCommandPlanner:
    return LLMCommandPlanner(
        _client(),
        max_attempts=int(os.getenv("VOICECANVAS_LLM_MAX_ATTEMPTS", "3")),
        timeout_seconds=float(os.getenv("VOICECANVAS_LLM_TIMEOUT_SECONDS", "20")),
        temperature=float(os.getenv("VOICECANVAS_LLM_TEMPERATURE", "0.1")),
    )


def _project_with_title():
    project = InMemoryProjectRepository().get_or_create("project_real_update_title")
    demo_plan = DemoCommandPlanner().plan("加标题，写新品上市", project)
    return CommandExecutor().execute_batch(demo_plan.commands, project).project


def test_real_llm_planner_outputs_are_saved_and_analyzed() -> None:
    planner = _planner()
    artifact_dir = _artifact_dir()
    cases = [
        {
            "name": "create_storyboard",
            "userInput": "创建一个三镜头的珍珠奶茶带货分镜",
            "project": InMemoryProjectRepository().get_or_create("project_real_storyboard"),
        },
        {
            "name": "add_title",
            "userInput": "加标题，写新品上市",
            "project": InMemoryProjectRepository().get_or_create("project_real_add_title"),
        },
        {
            "name": "update_title",
            "userInput": "把标题改成低糖也好喝",
            "project": _project_with_title(),
        },
    ]
    results = []
    failures = []

    for case in cases:
        plan = planner.plan(case["userInput"], case["project"])
        command_types = [command.type.value for command in plan.commands]
        record = {
            "case": case["name"],
            "userInput": case["userInput"],
            "action": plan.action,
            "message": plan.message,
            "notice": plan.notice,
            "commandCount": len(plan.commands),
            "commandTypes": command_types,
            "commands": [command.model_dump(by_alias=True) for command in plan.commands],
            "attempts": [asdict(attempt) for attempt in plan.attempts],
            "analysis": _analyze_plan(plan.action, command_types, plan.attempts),
        }
        results.append(record)
        (artifact_dir / f"{case['name']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if plan.action != "commands" or not plan.commands or not plan.attempts[-1].validated:
            failures.append(case["name"])

    (artifact_dir / "summary.md").write_text(_summary_markdown(results), encoding="utf-8")

    assert failures == []


def _analyze_plan(action: str, command_types: list[str], attempts: list[object]) -> dict:
    return {
        "formatValidated": bool(attempts and attempts[-1].validated),
        "finalAction": action,
        "usesOnlyStructuredCommands": action == "commands" and bool(command_types),
        "commandTypes": command_types,
        "retryCount": max(len(attempts) - 1, 0),
    }


def _summary_markdown(results: list[dict]) -> str:
    lines = [
        "# 真实 LLM Planner 输出分析",
        "",
        "本文件由真实 LLM 测试生成，用于复盘模型原始输出、重试次数和最终命令类型。",
        "",
    ]
    for result in results:
        analysis = result["analysis"]
        lines.extend(
            [
                f"## {result['case']}",
                "",
                f"- 用户命令：{result['userInput']}",
                f"- 最终动作：{result['action']}",
                f"- 命令数量：{result['commandCount']}",
                f"- 命令类型：{', '.join(result['commandTypes'])}",
                f"- 是否通过格式与业务校验：{analysis['formatValidated']}",
                f"- 重试次数：{analysis['retryCount']}",
                "",
            ]
        )
    return "\n".join(lines)
