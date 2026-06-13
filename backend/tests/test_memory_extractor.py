from voicecanvas.application.memory_extractor import MemoryExtractor


def test_extractor_promotes_explicit_future_preference_to_active_memory() -> None:
    extractor = MemoryExtractor()

    memories = extractor.extract(
        user_id="user_1",
        project_id="project_1",
        user_input="以后带货分镜默认用主图、卖点、转化三段结构",
    )

    assert len(memories) == 1
    assert memories[0].kind == "workflow_preference"
    assert memories[0].scope == "commerce"
    assert memories[0].status == "active"
    assert memories[0].confidence >= 0.85
    assert memories[0].evidence[0].project_id == "project_1"


def test_extractor_keeps_single_soft_preference_as_candidate() -> None:
    extractor = MemoryExtractor()

    memories = extractor.extract(
        user_id="user_1",
        user_input="这个清爽绿色风格挺好",
    )

    assert len(memories) == 1
    assert memories[0].kind == "style_preference"
    assert memories[0].status == "candidate"
    assert memories[0].confidence < 0.85


def test_extractor_ignores_sensitive_information() -> None:
    extractor = MemoryExtractor()

    memories = extractor.extract(
        user_id="user_1",
        user_input="记住我的手机号是13812345678",
    )

    assert memories == []


def test_extractor_ignores_plain_canvas_instruction() -> None:
    extractor = MemoryExtractor()

    memories = extractor.extract(
        user_id="user_1",
        user_input="把标题移到左上角",
    )

    assert memories == []
