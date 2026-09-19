"""media + preview для карточки ответа: группировка фото по постам, капы, превью."""

from backend.rag.searcher import GraphRAGSearcher


def _post(url, photos=(), text="t", group="g", date="2026-01-01"):
    photos = [p if "://" in p else f"https://vk.com/{p}.jpg" for p in photos]
    return {"post_url": url, "photos": list(photos), "text": text,
            "group_name": group, "published_at": date}


def _u(*names):
    return [f"https://vk.com/{n}.jpg" for n in names]


def test_collect_media_groups_by_post():
    src = [_post("u1", ["a1", "a2"]), _post("u2", ["b1"])]
    vec = [_post("u3", ["c1", "c2", "c3"])]
    assert GraphRAGSearcher._collect_media(src, vec) == _u("a1", "a2", "b1", "c1", "c2", "c3")


def test_collect_media_caps_and_dedupes():
    src = [_post("u1", ["a", "b", "c", "d", "e"])]  # per_post=4
    vec = [_post("u2", ["a", "f", "g", "h", "i", "j"])]  # 'a' уже есть
    got = GraphRAGSearcher._collect_media(src, vec, per_post=4, total=8)
    # per_post режет список до дедупликации: у u2 берутся [a,f,g,h], 'a' — дубль
    assert got == _u("a", "b", "c", "d", "f", "g", "h")


def test_collect_media_empty():
    assert GraphRAGSearcher._collect_media([], []) == []
    assert GraphRAGSearcher._collect_media([_post("u")], []) == []


def test_build_preview_prefers_post_with_photo():
    no_photo = _post("u1", [], text="без фото, но длинный текст" * 10)
    with_photo = _post("u2", ["pic"], text="с фото", group="Отряд", date="2026-03-01")
    prev = GraphRAGSearcher._build_preview([no_photo, with_photo], [])
    # первый годный пост (даже без фото) — превью строится по порядку
    assert prev["url"] == "u1"
    prev2 = GraphRAGSearcher._build_preview([with_photo], [])
    assert prev2 == {"group_name": "Отряд", "published_at": "2026-03-01",
                     "text": "с фото", "photo": "https://vk.com/pic.jpg", "url": "u2"}


def test_build_preview_skips_group_cards_and_truncates():
    card = _post("group://x", ["pic"], text="карточка")
    long_post = _post("u", ["pic2"], text="x" * 500)
    prev = GraphRAGSearcher._build_preview([card, long_post], [])
    assert prev["url"] == "u"
    assert len(prev["text"]) == 280
    assert GraphRAGSearcher._build_preview([card], []) is None
