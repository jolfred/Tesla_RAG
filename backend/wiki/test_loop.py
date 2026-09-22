"""Мок-тесты wiki tools_loop: сеть не нужна, читает storage/wiki."""
from backend.wiki import loop


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat_with_functions(self, messages, functions, function_call="auto"):
        self.calls += 1
        return self.script.pop(0)


def _fc(name, args):
    return {
        "message": {"content": "", "function_call": {"name": name, "arguments": args}},
        "finish_reason": "function_call",
    }


def test_search_finds_yunost():
    r = loop.wiki_search("Юность командир 2024", 3)
    assert r["status"] == "success"
    assert any("yunost" in i["slug"] for i in r["items"])


def test_read_ok_and_traversal_blocked():
    r = loop.wiki_read("lso/spo_yunost")
    assert r["status"] == "success" and r["links"] is not None and r["sources"]
    assert loop.wiki_read("../backend/config")["status"] == "fail"
    assert loop.wiki_read("no/such_page")["status"] == "fail"


def test_loop_happy_path():
    c = FakeClient(
        [
            _fc("wiki_search", {"query": "Юность командир", "top_k": 5}),
            _fc("wiki_read", {"slug": "lso/spo_yunost"}),
            {"message": {"content": "Командир — Шарифуллин (см. https://vk.com/x)"}, "finish_reason": "stop"},
        ]
    )
    r = loop.try_wiki_answer("Кто командовал Юностью?", client=c)
    assert r and "Шарифуллин" in r["answer"]
    assert r["pages"] == ["lso/spo_yunost"] and r["sources"]
    assert c.calls == 3


def test_loop_client_error_returns_none():
    class Boom:
        def chat_with_functions(self, *a, **k):
            raise RuntimeError("net down")

    assert loop.try_wiki_answer("что?", client=Boom()) is None


def test_search_empty_query_fails():
    assert loop.wiki_search(".. !!")["status"] == "fail"


def test_read_section():
    r = loop.wiki_read("lso/spo_yunost", "Награды и достижения")
    assert r["status"] == "success" and "Мисс Инт" in r["markdown"]
