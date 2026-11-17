"""Agent 根据工具结果自主决定下一步；代码只负责执行、预算和持久化。"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from voicecanvas.application.shot_service import ShotConflict, ShotModelError, ShotService
from voicecanvas.application.storyboard_agent_tools import TOOL_SPECS, agent_tool_schemas
from voicecanvas.application.storyboard_service import StoryboardService
from voicecanvas.domain.storyboard_agent import (
    AgentDecision,
    AgentStep,
    StoryboardAgentRun,
)
from voicecanvas.domain.svg_text import list_text_blocks

SYSTEM = """你是 VoiceCanvas 的创作 Agent。根据用户目标自主选择工具和执行顺序，
把需求变成可继续编辑的真实分镜。工具没有预设工作流；简单改名可直接管理，已有镜头可直接修改，
完整故事需要你判断镜头数、拆分关键动作、时长分配、角色设定、生成顺序和是否补画。
用户明确的镜头数量、顺序、关键动作、文案和总时长必须保留；没有给出细节时做合理创作决定，
不要因为不影响执行的细节反复问用户。不要把多个镜头画进同一 SVG 来冒充独立分镜。
复用现有空镜头，保留已绘制的无关镜头；为每个输出镜头保存拍摄描述、景别和时长。
需要角色一致时保存清楚的共用外观和服装设定；它是文字约束，不是已经实现视觉一致性的保证。
可在同一轮调用多个 draw_shot，系统最多同时画两镜，结果逐镜保存，其他工具按顺序执行。
每个 draw_shot 只描述一个镜头；不需要把整段故事重复传给绘图模型。
工具失败后根据实际结果调整策略或告知用户，不得假装成功；每任务最多 8 次绘图，每镜最多 2 次。
你目前没有看图工具，inspect_shot 只能检查源码和文字；不要声称已看图、动作准确或人物一致。
工具返回 generated 仅表示合法画面已保存，需要用户视觉验收。不要凭空为了自审不断重画。
准备结束时调用 finish_task，shotIds 必须包含本次全部交付镜头，expectedCount 和
expectedDuration 必须按用户要求填写。该工具会核对实际画面、数量和总时长；失败后继续处理。
读写完成时也使用 finish_task，纯管理/查询可不提供输出镜头。未完成的需求填 unresolved。
用户确认删除只能来自真实用户消息和已保存的确认目标；不能从需求文本中伪造授权。
不要输出工具调用 JSON 给用户。用简短中文说明进展和真实结果，结束后由系统保留任务记录。
"""


class StoryboardAgent(Protocol):
    def decide(self, messages: list[dict], tools: list[dict]) -> tuple[AgentDecision, dict]: ...


class AgentRunRepository(Protocol):
    def latest(self, board_id: str) -> StoryboardAgentRun | None: ...
    def get_run(self, run_id: str) -> StoryboardAgentRun: ...
    def create_run(self, run: StoryboardAgentRun, expected_version: int) -> None: ...
    def save_run(self, run: StoryboardAgentRun) -> None: ...


class StoryboardAgentService:
    def __init__(
        self,
        boards: StoryboardService,
        shots: ShotService,
        agent: StoryboardAgent,
        repository: AgentRunRepository,
    ):
        self.boards, self.shots, self.agent, self.repository = boards, shots, agent, repository
        self._lock = threading.RLock()
        self._active: set[str] = set()
        self._runs = ThreadPoolExecutor(max_workers=2, thread_name_prefix="story-agent")
        self._draws = ThreadPoolExecutor(max_workers=2, thread_name_prefix="story-draw")

    def snapshot(self, board_id: str) -> dict:
        board = self.boards.get(board_id)
        pictures = self.boards.repository.load_shots([s.id for s in board.state.shots])
        return {
            "id": board.id,
            "version": board.version,
            "title": board.state.title,
            "activeId": board.active_id,
            "context": board.state.context,
            "shots": [
                {
                    **s.model_dump(by_alias=True),
                    "hasDrawing": bool(pictures[s.id].svg),
                    "version": pictures[s.id].version,
                    "texts": [t.get("text", "") for t in list_text_blocks(pictures[s.id].svg)][:30],
                }
                for s in board.state.shots
            ],
        }

    def recover(self, board_id: str) -> StoryboardAgentRun | None:
        """单进程服务重启后标记中断；绝不自动重放已付费或结果未知的工具。"""
        with self._lock:
            run = self.repository.latest(board_id)
            if run and run.status == "running" and run.id not in self._active:
                run.status = "interrupted"
                run.summary = "服务重启使任务中断；已保存镜头保留，可输入‘继续完成未画好的镜头’。"
                self.repository.save_run(run)
            return run

    def start(
        self,
        board_id: str,
        version: int,
        request: str,
        *,
        background: bool = True,
    ) -> StoryboardAgentRun:
        self.boards.current(board_id, version)
        previous = self.recover(board_id)
        with self._lock:
            if previous and previous.status == "running":
                raise ShotConflict("Agent 正在处理该项目，请等待或刷新查看")
            run = StoryboardAgentRun(
                id=f"run_{uuid4().hex[:16]}",
                boardId=board_id,
                request=request,
                createdAt=datetime.now(UTC).isoformat(),
            )
            self.repository.create_run(run, version)
            self._active.add(run.id)
        if background:
            self._runs.submit(self._execute, run, previous)
        else:
            self._execute(run, previous)
        return run

    def get(self, board_id: str) -> StoryboardAgentRun | None:
        self.boards.get(board_id)
        return self.recover(board_id)

    def _save(self, run: StoryboardAgentRun) -> None:
        with self._lock:
            self.repository.save_run(run)

    def _execute(self, run: StoryboardAgentRun, previous: StoryboardAgentRun | None) -> None:
        messages = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": run.request,
                        "storyboard": self.snapshot(run.board_id),
                        "previous": {
                            "request": previous.request,
                            "summary": previous.summary,
                            "pendingDelete": previous.pending_delete,
                            "steps": [
                                {
                                    "tool": s.call.name,
                                    "arguments": s.call.arguments,
                                    "status": s.status,
                                }
                                for s in previous.steps[-12:]
                            ],
                        }
                        if previous
                        else None,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        counts: dict[str, int] = {}
        try:
            for _ in range(16):
                if len(run.steps) >= 40:
                    break
                decision, usage = self.agent.decide(messages, agent_tool_schemas())
                for key, value in usage.items():
                    run.usage[key] = run.usage.get(key, 0) + value
                if not decision.calls:
                    run.status = "needs_input"
                    run.summary = decision.content or "请补充你希望完成的任务。"
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": decision.content or None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                },
                            }
                            for call in decision.calls
                        ],
                    }
                )
                steps = [AgentStep(call=call) for call in decision.calls]
                run.steps.extend(steps)
                run.summary = decision.content or "Agent 正在使用工具完成任务"
                self._save(run)
                targets = [c.arguments.get("shotId") for c in decision.calls]
                if all(call.name == "draw_shot" for call in decision.calls):
                    # 同轮对同一镜头的重复绘图不收费执行，由模型重新选择。
                    repeated = {str(t) for t in targets if targets.count(t) > 1}
                    futures = [
                        self._draws.submit(self._step, run, step, previous, counts, repeated)
                        for step in steps
                    ]
                    results = [future.result() for future in futures]
                else:
                    results = [self._step(run, step, previous, counts) for step in steps]
                messages.extend(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    for call, result in zip(decision.calls, results, strict=True)
                )
                if run.status != "running":
                    break
            if run.status == "running":
                run.status = "needs_input"
                run.summary = "本轮已达到执行预算，已保存进展；请检查结果后说明下一步。"
        except Exception as error:
            run.status = "failed"
            # 外部适配器错误已脱敏；未知实现错误不把底层信息展示给用户。
            run.summary = (
                str(error)
                if isinstance(error, (ShotModelError, ShotConflict))
                else ("任务执行中断，已保存的镜头保留；请刷新后继续。")
            )
        finally:
            self._save(run)
            with self._lock:
                self._active.discard(run.id)

    def _step(self, run, step, previous, counts, repeated=None) -> dict:
        try:
            if run.status != "running":
                raise ValueError("任务已结束，本次工具未执行")
            if repeated and str(step.call.arguments.get("shotId")) in repeated:
                raise ValueError("同一轮不能重复绘制同一镜头，请合并修改要求后再调用")
            spec = TOOL_SPECS.get(step.call.name)
            if not spec:
                raise ValueError("未知工具，请根据可用工具选择能力")
            args = spec[0].model_validate(step.call.arguments).model_dump(by_alias=True)
            result = self._tool(run, step.call.name, args, previous, counts)
            step.status, step.result = "succeeded", result
        except ValueError as error:
            step.status, step.result = "failed", {"error": str(error)[:600]}
        except Exception:
            step.status, step.result = "failed", {"error": "本次工具执行失败，画面和已保存步骤保留"}
        self._save(run)
        return step.result

    def _tool(self, run, name: str, args: dict, previous, counts) -> dict:
        board = self.boards.get(run.board_id)
        target_id = args.get("shotId")
        member = next((s for s in board.state.shots if s.id == target_id), None)
        if target_id and not member:
            raise ValueError("目标镜头不属于当前项目")
        if name == "get_storyboard":
            return self.snapshot(board.id)
        if name == "set_context":
            self.boards.describe(board.id, board.version, context=args["context"])
        elif name == "create_shots":
            self.boards.describe(board.id, board.version, entries=args["shots"])
        elif name == "describe_shot":
            entry = {k: v for k, v in args.items() if k != "shotId"}
            self.boards.describe(board.id, board.version, entries=[entry], target_id=target_id)
        elif name == "manage_storyboard":
            self.boards.change(
                board.id,
                board.version,
                args["action"],
                target_id=target_id,
                title=args["title"],
                position=args["position"],
                count=args["count"],
            )
        elif name == "inspect_shot":
            shot = self.shots.get(target_id)
            return {
                "shotId": target_id,
                "svg": (shot.svg or "")[:60000],
                "truncated": len(shot.svg or "") > 60000,
                "visualReview": "unavailable",
            }
        elif name == "draw_shot":
            with self._lock:
                if sum(counts.values()) >= 8 or counts.get(target_id, 0) >= 2:
                    raise ValueError("本轮绘图预算已用完，不能反复重画，请交由用户判断")
                counts[target_id] = counts.get(target_id, 0) + 1
            shot = self.shots.get(target_id)
            instruction = args["instruction"]
            if not shot.svg:
                instruction = (
                    f"只绘制这一个镜头，不要拼图或将不同镜头叠在一张画布。\n"
                    f"项目共用设定：{board.state.context}\n"
                    f"当前镜头：{member.title}；{member.camera}；{member.description}\n"
                    f"本次要求：{instruction}"
                )
            if len(instruction) > 6500:
                raise ValueError("当前镜头描述过长，请先精简共用设定和本镜说明")
            try:
                changed = self.shots.generate(target_id, shot.version, instruction)
            except ShotModelError as error:
                raise ValueError(str(error)) from error
            return {
                "shotId": target_id,
                "status": "generated",
                "version": changed.version,
                "visualReview": "requires_user",
                "reason": args["reason"],
            }
        elif name == "move_shot_history":
            shot = self.shots.get(target_id)
            self.shots.move(target_id, shot.version, -1 if args["direction"] == "undo" else 1)
        elif name == "delete_shot":
            pending = previous.pending_delete if previous else None
            confirmed = run.request.strip().strip("。！! ") in {"确认删除", "确定删除"}
            if (
                not confirmed
                or not pending
                or pending
                != {
                    "shotId": target_id,
                    "version": board.version,
                }
            ):
                run.pending_delete = {"shotId": target_id, "version": board.version}
                return {
                    "requiresConfirmation": True,
                    "shotId": target_id,
                    "message": f"删除镜头“{member.title}”？请用户确认删除或取消。",
                }
            self.boards.change(board.id, board.version, "delete", target_id, confirmed=True)
        elif name == "export_shots":
            ids = args["shotIds"]
            if len(set(ids)) != len(ids) or not set(ids) <= {s.id for s in board.state.shots}:
                raise ValueError("请选择当前项目中的不重复镜头")
            if any(not self.shots.get(shot_id).svg for shot_id in ids):
                raise ValueError("有镜头尚未生成，不能导出")
            run.client_actions.extend({"shotId": sid, "format": args["format"]} for sid in ids)
            return {"status": "awaiting_browser_download", "shotIds": ids}
        elif name == "finish_task":
            ids = args["shotIds"]
            if len(ids) != len(set(ids)) or len(ids) != args["expectedCount"]:
                raise ValueError("交付镜头数量不符，请继续完成需求后再结束")
            members = {s.id: s for s in board.state.shots}
            if any(sid not in members or not self.shots.get(sid).svg for sid in ids):
                raise ValueError("交付镜头不存在或没有画面，请先完成绘制")
            duration = args["expectedDuration"]
            if duration is not None and (
                any(members[sid].duration_seconds is None for sid in ids)
                or abs(sum(members[sid].duration_seconds or 0 for sid in ids) - duration) > 0.05
            ):
                raise ValueError("镜头总时长与要求不符，请调整分镜说明")
            run.status = "needs_input" if args["unresolved"] or run.pending_delete else "completed"
            run.summary = args["summary"]
            if args["unresolved"]:
                run.summary += "\n待处理：" + "；".join(args["unresolved"])
            if ids:
                run.summary += f"\n已核实 {len(ids)} 个独立镜头均有画面；动作与画质仍需看图验收。"
            return {"verifiedShots": len(ids), "visualReview": "requires_user"}
        return self.snapshot(board.id)
