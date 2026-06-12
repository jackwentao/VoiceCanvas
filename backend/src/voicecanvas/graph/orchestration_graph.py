from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph


class OrchestrationState(TypedDict, total=False):
    project_id: str
    session_id: str
    user_input: str
    status: str
    stage: str
    next_action: dict[str, Any]
    events: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    summary: str


def _append_event(state: OrchestrationState, event: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("events", []), event]


def receive_input(state: OrchestrationState) -> OrchestrationState:
    session_id = state.get("session_id") or f"session_{uuid4().hex[:12]}"
    return {
        **state,
        "session_id": session_id,
        "status": "RUNNING",
        "stage": "understanding",
        "events": _append_event(
            state,
            {
                "type": "STAGE_CHANGED",
                "sessionId": session_id,
                "stage": "understanding",
                "message": "正在理解用户输入",
            },
        ),
    }


def orchestrate_next_action(state: OrchestrationState) -> OrchestrationState:
    user_input = state.get("user_input", "")
    session_id = state["session_id"]
    action: dict[str, Any]

    if "哪个" in user_input or "不清楚" in user_input:
        action = {
            "type": "ASK_CLARIFICATION",
            "question": "你想操作哪个画布元素？",
            "expectedAnswerType": "element_selection",
            "resumePolicy": {
                "sessionId": session_id,
                "clarificationId": f"clarification_{uuid4().hex[:8]}",
                "allowVoiceAnswer": True,
                "allowOptionSelection": True,
            },
        }
        return {
            **state,
            "status": "WAITING_FOR_USER",
            "stage": "waiting_for_user",
            "next_action": action,
            "events": _append_event(
                state,
                {
                    "type": "CLARIFICATION_REQUESTED",
                    "sessionId": session_id,
                    "question": action["question"],
                },
            ),
        }

    if "创建" in user_input or "生成" in user_input:
        action = {
            "type": "EXECUTE_COMMANDS",
            "commands": [
                {
                    "id": f"cmd_{uuid4().hex[:12]}",
                    "type": "CREATE_SCENE",
                    "source": "ai",
                    "payload": {"name": "语音创建镜头", "activate": True},
                    "reason": "根据用户输入创建初始镜头",
                }
            ],
        }
        return {
            **state,
            "stage": "executing",
            "next_action": action,
            "events": _append_event(
                state,
                {
                    "type": "STAGE_CHANGED",
                    "sessionId": session_id,
                    "stage": "executing",
                    "message": "准备执行画布命令",
                },
            ),
        }

    action = {"type": "RESPOND", "message": "已收到需求，等待更具体的绘图指令。"}
    return {
        **state,
        "stage": "summarizing",
        "next_action": action,
    }


def route_action(state: OrchestrationState) -> Literal["wait", "summarize"]:
    if state.get("next_action", {}).get("type") == "ASK_CLARIFICATION":
        return "wait"
    return "summarize"


def summarize_turn(state: OrchestrationState) -> OrchestrationState:
    action_type = state.get("next_action", {}).get("type")
    status = state.get("status")
    if status != "WAITING_FOR_USER":
        status = "COMPLETED"

    summary = "已生成可执行画布命令。" if action_type == "EXECUTE_COMMANDS" else "已完成本轮处理。"
    return {
        **state,
        "status": status,
        "stage": "completed" if status == "COMPLETED" else state.get("stage", "waiting_for_user"),
        "summary": summary,
        "events": _append_event(
            state,
            {
                "type": "TURN_SUMMARY",
                "sessionId": state["session_id"],
                "summary": {"completed": status == "COMPLETED", "message": summary},
            },
        ),
    }


def build_orchestration_graph():
    graph = StateGraph(OrchestrationState)
    graph.add_node("receive_input", receive_input)
    graph.add_node("orchestrate_next_action", orchestrate_next_action)
    graph.add_node("summarize_turn", summarize_turn)

    graph.set_entry_point("receive_input")
    graph.add_edge("receive_input", "orchestrate_next_action")
    graph.add_conditional_edges(
        "orchestrate_next_action",
        route_action,
        {
            "wait": END,
            "summarize": "summarize_turn",
        },
    )
    graph.add_edge("summarize_turn", END)

    return graph.compile()
