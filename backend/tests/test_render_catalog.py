from voicecanvas.application.render_catalog import get_render_catalog


def test_render_catalog_resolves_alias_and_variant() -> None:
    catalog = get_render_catalog()

    match = catalog.resolve("一个年轻男性顾客")

    assert match is not None
    assert match.render_key == "character"
    assert match.variant == "male"
    assert match.direct_render is True


def test_render_catalog_marks_known_but_unsupported_object_as_placeholder() -> None:
    catalog = get_render_catalog()

    match = catalog.resolve("画一只小狗")

    assert match is not None
    assert match.render_key == "dog"
    assert match.direct_render is False


def test_render_catalog_does_not_guess_unknown_object() -> None:
    catalog = get_render_catalog()

    assert catalog.resolve("火箭发动机剖面图") is None


def test_render_catalog_prompt_manifest_exposes_capabilities() -> None:
    manifest = get_render_catalog().prompt_manifest()

    assert "character" in manifest
    assert "direct" in manifest
    assert "placeholder" in manifest
