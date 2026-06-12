from voicecanvas.graph.orchestration_graph import build_orchestration_graph


def test_graph_can_pause_for_clarification() -> None:
    graph = build_orchestration_graph()

    result = graph.invoke(
        {
            "project_id": "project_demo",
            "user_input": "我不清楚要改哪个",
            "events": [],
            "observations": [],
        }
    )

    assert result["status"] == "WAITING_FOR_USER"
    assert result["stage"] == "waiting_for_user"
    assert result["next_action"]["type"] == "ASK_CLARIFICATION"
    assert result["events"][-1]["type"] == "CLARIFICATION_REQUESTED"

