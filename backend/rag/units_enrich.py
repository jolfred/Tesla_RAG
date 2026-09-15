"""Обогащение списка отрядов (п.2 отзыва): направления из карточки штаба,
описания и ссылки из метафайлов групп.

Всё чистое (unit-тестируется на фикстурах): парсинг карточки, стыковка
clubID -> метафайл по group_id, рендер с группировкой по направлениям.
IO (чтение storage/groups) — в searcher, не здесь.
"""

from __future__ import annotations

import re

from backend.common.canon import normalize_id

_BULLET_LINK_RE = re.compile(r"\[(club\d+|https?://[^\]|]+)\|([^]]+)\]")


def _clean_name(raw: str) -> str:
    return raw.strip().strip("«»\"' ")


def parse_unit_directions(card_text: str) -> list[dict]:
    """Разбор карточки штаба: [(направление, club_id|None, url|None, имя)].

    Заголовок = строка без '[' и '•', кончающаяся на ':'
    («Строительное направление:», «Отряд проводников:»).
    """
    entries: list[dict] = []
    current: str | None = None
    for line in (card_text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if "[" not in s and "•" not in s and s.endswith(":"):
            current = s[:-1].strip()
            continue
        if current is None:
            continue
        for m in _BULLET_LINK_RE.finditer(s):
            target, name = m.group(1), _clean_name(m.group(2))
            club_num = None
            url = None
            if target.startswith("club"):
                club_num = int(target[4:])
            else:
                url = target
            entries.append(
                {"direction": current, "club_num": club_num,
                 "url": url, "name": name}
            )
    return entries


def _blurb(meta: dict | None, limit: int = 150) -> str | None:
    if not meta:
        return None
    text = re.sub(r"\s+", " ", (meta.get("description") or "").strip())
    return text[:limit].rstrip() or None


def enrich_units(
    unit_names: list[str],
    directions: list[dict],
    metas_by_id: dict[int, dict],
) -> list[dict]:
    """Стыковка фактов графа с карточкой: порядок карточки первый.

    Возвращает [{name, direction|None, url|None, blurb|None}].
    Отряды карточки идут все (карточка — авторитетный список);
    факты графа вне карточки (Турбопиш) дописываются без направления.
    """
    items: list[dict] = []
    seen: set[str] = set()
    for d in directions:
        meta = metas_by_id.get(d["club_num"]) if d["club_num"] else None
        url = d["url"]
        if meta and meta.get("domain"):
            url = f"https://vk.com/{meta['domain']}"
        elif d["club_num"]:
            url = f"https://vk.com/club{d['club_num']}"
        items.append(
            {"name": d["name"], "direction": d["direction"],
             "url": url, "blurb": _blurb(meta)}
        )
        seen.add(normalize_id(d["name"]))
    for name in unit_names:
        if normalize_id(name) in seen:
            continue
        seen.add(normalize_id(name))
        items.append({"name": name, "direction": None, "url": None,
                      "blurb": None})
    return items


def render_units_enriched(items: list[dict], org_name: str) -> str | None:
    """Группировка по направлениям + описание + ссылка (формат из отзыва)."""
    if not items:
        return None
    lines = [f"Отряды «{org_name}»:"]
    current = object()  # sentinel: первый заголовок печатаем всегда
    for it in items:
        direction = it.get("direction")
        if direction != current:
            current = direction
            lines.append(f"{direction}:" if direction else "Другие отряды:")
        bullet = f"• {it['name']}"
        if it.get("blurb"):
            bullet += f" — {it['blurb']}"
        if it.get("url"):
            bullet += f" ({it['url']})"
        lines.append(bullet)
    return "\n".join(lines)
