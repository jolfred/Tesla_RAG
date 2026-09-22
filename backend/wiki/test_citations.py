from backend.wiki.citations import build_wall_index, rewrite_answer_links, wiki_url_for_post


def _seed_wiki(tmp_path):
    (tmp_path / "lso").mkdir()
    (tmp_path / "lso" / "spo_yunost.md").write_text(
        "# Юность\n\nфакт (Источник: ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)), опубл. 2021-04-07).",
        encoding="utf-8",
    )
    (tmp_path / "persons").mkdir()
    (tmp_path / "persons" / "bogachev_egor.md").write_text(
        "# Богачёв\n\nтот же пост ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)).",
        encoding="utf-8",
    )


def test_build_wall_index(tmp_path):
    _seed_wiki(tmp_path)
    assert build_wall_index(tmp_path) == {
        "wall-198864697_133": ["lso/spo_yunost", "persons/bogachev_egor"]
    }


def test_wiki_url_for_post_known_and_unknown(tmp_path):
    _seed_wiki(tmp_path)
    assert wiki_url_for_post("https://vk.com/spoyunost2020?w=wall-198864697_133", tmp_path) == "/wiki/lso/spo_yunost"
    assert wiki_url_for_post("https://vk.com/other?w=wall-1_999", tmp_path) is None
    assert wiki_url_for_post("https://vk.com/rso_tesla", tmp_path) is None


def test_rewrite_md_link_and_bare_url(tmp_path):
    _seed_wiki(tmp_path)
    answer = (
        "Был Богачёв [sources](https://vk.com/spoyunost2020?w=wall-198864697_133), "
        "а ещё https://vk.com/spoyunost2020?w=wall-198864697_133. "
        "Чужой пост [sources](https://vk.com/other?w=wall-1_999)."
    )
    assert rewrite_answer_links(answer, tmp_path) == (
        "Был Богачёв [sources](/wiki/lso/spo_yunost), "
        "а ещё /wiki/lso/spo_yunost. "
        "Чужой пост [sources](https://vk.com/other?w=wall-1_999)."
    )


def test_rewrite_noop_without_vk():
    assert rewrite_answer_links("Просто текст [документ](https://example.com/a).") == "Просто текст [документ](https://example.com/a)."
    assert rewrite_answer_links("") == ""
