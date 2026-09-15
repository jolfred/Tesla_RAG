"""Тесты обогащения units: парсинг карточки, стыковка, рендер."""

from backend.rag.units_enrich import (
    enrich_units,
    parse_unit_directions,
    render_units_enriched,
)

CARD = """Отряды Штаба СО КГЭУ «Тесла»
Строительное направление:
• [club144172595|«Монолит»]
• [club180894546|«Дайнима»]
Отряд проводников:
• [club91744408|«Energy»]
Производственное направление:
• [https://vk.ru/spro_tesla|«Тесла»]
"""

METAS = {
    144172595: {"domain": "ssomonolitkazan",
                "description": "Студенческий строительный отряд «Монолит» Штаба СО КГЭУ «Тесла» Наш девиз отличный!"},
    91744408: {"domain": "sopenergy", "description": ""},
}


def test_parse_unit_directions():
    entries = parse_unit_directions(CARD)
    assert [(e["direction"], e["club_num"], e["name"]) for e in entries] == [
        ("Строительное направление", 144172595, "Монолит"),
        ("Строительное направление", 180894546, "Дайнима"),
        ("Отряд проводников", 91744408, "Energy"),
        ("Производственное направление", None, "Тесла"),
    ]
    assert entries[3]["url"] == "https://vk.ru/spro_tesla"
    assert parse_unit_directions("") == []
    assert parse_unit_directions("просто текст без направлений:\n• привет") == []


def test_enrich_units_order_and_meta():
    items = enrich_units(["Турбопиш", "Монолит"], parse_unit_directions(CARD), METAS)
    assert [i["name"] for i in items] == [
        "Монолит", "Дайнима", "Energy", "Тесла", "Турбопиш"]
    mono = items[0]
    assert mono["direction"] == "Строительное направление"
    assert mono["url"] == "https://vk.com/ssomonolitkazan"
    assert mono["blurb"].startswith("Студенческий строительный отряд")
    # Пустое описание -> None, но ссылка по domain есть.
    assert items[2]["blurb"] is None
    assert items[2]["url"] == "https://vk.com/sopenergy"
    # Прямая ссылка из карточки, меты нет.
    assert items[3]["url"] == "https://vk.ru/spro_tesla"
    # Внекарточный — без всего.
    assert items[4] == {"name": "Турбопиш", "direction": None,
                        "url": None, "blurb": None}


def test_render_units_enriched_exact():
    items = enrich_units(["Монолит"], parse_unit_directions(CARD), METAS)
    assert render_units_enriched(items[:1], "Тесла") == (
        "Отряды «Тесла»:\n"
        "Строительное направление:\n"
        "• Монолит — Студенческий строительный отряд «Монолит» Штаба СО КГЭУ «Тесла» Наш девиз отличный! (https://vk.com/ssomonolitkazan)"
    )
    assert render_units_enriched([], "Тесла") is None


def test_render_units_enriched_other_direction():
    items = [
        {"name": "X", "direction": None, "url": None, "blurb": None},
    ]
    assert render_units_enriched(items, "Тесла") == (
        "Отряды «Тесла»:\nДругие отряды:\n• X"
    )
