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


def test_render_catalog_resolves_commerce_subject_and_attributes() -> None:
    catalog = get_render_catalog()

    match = catalog.resolve("草莓味珍珠奶茶")

    assert match is not None
    assert match.render_key == "bubble-tea"
    assert match.asset_provider == "minio"
    assert match.asset_path == "catalog/commerce/food-drink/bubble-tea.png"
    assert match.attributes is not None
    assert "草莓味" in match.attributes["flavor"]
    assert "珍珠" in match.attributes["toppings"]


def test_render_catalog_resolves_smartphone_alias() -> None:
    catalog = get_render_catalog()

    match = catalog.resolve("画一台旗舰手机")

    assert match is not None
    assert match.render_key == "smartphone"
    assert match.asset_provider == "minio"


def test_render_catalog_does_not_guess_unknown_object() -> None:
    catalog = get_render_catalog()

    assert catalog.resolve("火箭发动机剖面图") is None


def test_render_catalog_prompt_manifest_exposes_capabilities() -> None:
    manifest = get_render_catalog().prompt_manifest()

    assert "character" in manifest
    assert "direct" in manifest
    assert "placeholder" in manifest
