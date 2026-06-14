from voicecanvas.application.referent_resolver import ReferentResolver, resolution_to_next_action
from voicecanvas.domain.conversation import ConversationMemorySnapshot, ElementMemory
from voicecanvas.domain.project import CanvasElement, ElementType, Project, Scene


def _element(
    element_id: str,
    name: str,
    x: float,
    *,
    text: str | None = None,
    element_type: ElementType = ElementType.SHAPE,
) -> CanvasElement:
    return CanvasElement(
        id=element_id,
        type=element_type,
        name=name,
        text=text,
        x=x,
        y=120,
        width=120,
        height=160,
        zIndex=1,
    )


def _project(elements: list[CanvasElement]) -> Project:
    return Project(
        id="project_ref",
        title="Referent Test",
        mode="storyboard",
        scenes=[Scene(id="scene_1", name="主图", order=1, elements=elements)],
        activeSceneId="scene_1",
    )


def test_resolver_matches_single_left_cup() -> None:
    project = _project(
        [
            _element("el_left_cup", "左侧奶茶杯", 80),
            _element("el_title", "标题", 520, element_type=ElementType.TEXT, text="新品上市"),
        ]
    )

    result = ReferentResolver().resolve("把左边那个杯子放大一点", project)

    assert result is not None
    assert result.status == "matched"
    assert result.candidates[0].element_id == "el_left_cup"


def test_resolver_returns_candidates_when_multiple_cups_match() -> None:
    project = _project(
        [
            _element("el_left_cup", "左侧奶茶杯", 80),
            _element("el_right_cup", "右侧奶茶杯", 760),
        ]
    )

    result = ReferentResolver().resolve("把那个杯子放大一点", project)

    assert result is not None
    assert result.status == "ambiguous"
    assert [candidate.element_id for candidate in result.candidates] == [
        "el_left_cup",
        "el_right_cup",
    ]


def test_resolver_expands_candidate_scope_when_direct_name_misses() -> None:
    project = _project(
        [
            _element("el_ceramic", "左侧陶瓷器", 80),
            _element("el_title", "标题", 520, element_type=ElementType.TEXT, text="新品上市"),
        ]
    )

    result = ReferentResolver().resolve("把左边那个杯子放大一点", project)

    assert result is not None
    assert result.expanded
    assert result.candidates[0].element_id == "el_ceramic"


def test_resolver_prefers_direct_element_name_for_named_character() -> None:
    project = _project(
        [
            _element("el_girl", "小女孩", 520),
            _element("el_cat", "小猫", 80),
        ]
    )

    result = ReferentResolver().resolve("把小女孩移到左边", project)

    assert result is not None
    assert result.status == "matched"
    assert result.candidates[0].element_id == "el_girl"


def test_resolution_to_next_action_carries_candidates_for_resume() -> None:
    project = _project(
        [
            _element("el_left_cup", "左侧奶茶杯", 80),
            _element("el_right_cup", "右侧奶茶杯", 760),
        ]
    )
    result = ReferentResolver().resolve("把那个杯子放大一点", project)
    assert result is not None

    action = resolution_to_next_action(result, session_id="session_test")

    assert action["type"] == "ASK_CLARIFICATION"
    assert action["resumePolicy"]["sessionId"] == "session_test"
    assert action["resumePolicy"]["resumeWith"]["type"] == "REFERENT_CLARIFICATION_RESULT"
    assert len(action["options"]) == 2


def test_resolver_uses_recent_focus_for_implicit_move() -> None:
    dog = _element("el_dog", "狗", 320)
    title = _element(
        "el_title",
        "标题",
        80,
        element_type=ElementType.TEXT,
        text="标题",
    )
    project = _project([dog, title])
    memory = ConversationMemorySnapshot(
        focusStack=[
            ElementMemory(
                sceneId="scene_1",
                elementId="el_dog",
                type="shape",
                name="狗",
                bounds={"x": 320, "y": 120, "width": 120, "height": 160},
                source="element_added",
                lastTouchedAt="2026-06-13T00:00:00+00:00",
            )
        ]
    )

    result = ReferentResolver().resolve("往左移一点", project, memory)

    assert result is not None
    assert result.status == "matched"
    assert result.candidates[0].element_id == "el_dog"
