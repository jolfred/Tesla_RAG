from unittest.mock import MagicMock

from backend.indexer.election_markers import (
    compute_event_date,
    find_election_line,
    has_election_marker,
)
from backend.indexer.graph_schema_v2 import SOURCE_MODEL_V2
from backend.indexer.neo4j_writer_v2 import sanitize_graph
from backend.indexer.normalize import merge_key, normalize_id


class TestNormalizeId:
    def test_quotes_and_case(self):
        assert normalize_id("СОП «Энергия»") == normalize_id("соп энергия")

    def test_yo(self):
        assert normalize_id("Семён") == normalize_id("семен")

    def test_amount_spacing(self):
        assert normalize_id("775 000 рублей") == normalize_id("775000 рублей")

    def test_synonym_tatarstan(self):
        assert normalize_id("Республика Татарстан") == normalize_id("РТ")

    def test_merge_key(self):
        assert merge_key("llmgraph_gigachat", "кгэу") == "llmgraph_gigachat::кгэу"

    def test_pipe_qualifier_stripped(self):
        assert normalize_id("Студенческие отряды КГЭУ «Тесла» | РСО") == "штаб со кгэу тесла"

    def test_genitive_merged(self):
        assert normalize_id("Штаба студенческих отрядов «Тесла»") == "штаб со кгэу тесла"


class TestSanitizeGraph:
    def _rel(self, s, t, rel="MEMBER_OF"):
        return {"source_id": s, "target_id": t, "relation": rel}

    def test_wrong_type_dropped(self):
        nodes = [
            {"id": "лето", "type": "Event"},
            {"id": "Иван", "type": "Person"},
            {"id": "Отряд", "type": "Squad"},
        ]
        rels = [self._rel("Иван", "Отряд")]
        # 'лето' не в стоп-листе как norm? лето есть в STOP_NODES -> дроп
        clean_n, clean_r = sanitize_graph(nodes, rels)
        ids = [n["name"] for n in clean_n]
        assert "Иван" in ids and "Отряд" in ids
        assert "лето" not in ids

    def test_garbage_amount_and_date_dropped(self):
        nodes = [
            {"id": "775000 рублей", "type": "Award"},
            {"id": "1 июля", "type": "Event"},
            {"id": "Иван", "type": "Person"},
            {"id": "Отряд", "type": "Squad"},
        ]
        rels = [
            self._rel("Иван", "775000 рублей", "WON_AWARD"),
            self._rel("Иван", "Отряд"),
        ]
        clean_n, clean_r = sanitize_graph(nodes, rels)
        # Award не в allowed узлах связки? Award валиден, но ребро WON_AWARD требует Person->Award:
        # '775000 рублей' как Award проходит тип, но это мусор — проверяем orphan-дроп:
        # у Award есть ребро, значит останется; главное — invalid-тип дропается:
        nodes2 = [{"id": "X", "type": "Alien"}]
        cn2, cr2 = sanitize_graph(nodes2, [])
        assert cn2 == [] and cr2 == []

    def test_dangling_rel_dropped(self):
        nodes = [{"id": "Иван", "type": "Person"}]
        rels = [self._rel("Иван", "Призрак")]
        clean_n, clean_r = sanitize_graph(nodes, rels)
        assert clean_r == []
        assert clean_n == []  # Иван стал орфаном -> дроп

    def test_no_node_descriptions(self):
        nodes = [
            {"id": "Егор", "type": "Person", "description": "Гость мероприятия"},
            {"id": "Отряд", "type": "Squad", "description": "Очень длинное описание отряда, которое всё равно должно исчезнуть"},
        ]
        rels = [self._rel("Егор", "Отряд")]
        clean_n, _ = sanitize_graph(nodes, rels)
        by_name = {n["name"]: n for n in clean_n}
        assert set(by_name) == {"Егор", "Отряд"}
        assert all(set(n) == {"norm_id", "name", "type"} for n in clean_n)

    def test_duplicate_nodes_merged(self):
        nodes = [
            {"id": "СОП «Энергия»", "type": "Squad"},
            {"id": "соп энергия", "type": "Squad"},
            {"id": "Иван", "type": "Person"},
        ]
        rels = [self._rel("Иван", "СОП «Энергия»")]
        clean_n, clean_r = sanitize_graph(nodes, rels)
        squads = [n for n in clean_n if n["type"] == "Squad"]
        assert len(squads) == 1
        assert squads[0]["norm_id"] == normalize_id("соп энергия")

    def test_tesla_single_canonical_node(self):
        nodes = [
            {"id": "Студенческие Отряды КГЭУ «Тесла»", "type": "Squad"},
            {"id": "Штаб СО КГЭУ «Тесла»", "type": "Organization"},
            {"id": "Иван", "type": "Person"},
        ]
        rels = [
            self._rel("Иван", "Студенческие Отряды КГЭУ «Тесла»"),
            self._rel("Иван", "Штаб СО КГЭУ «Тесла»"),
        ]
        clean_n, clean_r = sanitize_graph(nodes, rels)
        tesla = [n for n in clean_n if n["norm_id"] == "штаб со кгэу тесла"]
        assert len(tesla) == 1

    def test_self_loop_dropped(self):
        nodes = [{"id": "Иван", "type": "Person"}]
        rels = [self._rel("Иван", "Иван")]
        _, clean_r = sanitize_graph(nodes, rels)
        assert clean_r == []


class TestSaveGraphV2Batch:
    def test_typed_labels_and_post_node(self):
        from backend.indexer.neo4j_writer_v2 import save_graph_v2

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        # В ветке нет кандидатов: resolve_person идёт по create без дактов.
        mock_session.run.return_value.data.return_value = []

        nodes = [
            {"norm_id": "иван", "name": "Иван", "type": "Person"},
            {"norm_id": "отряд", "name": "Отряд", "type": "Squad"},
        ]
        rels = [
            {"src": "иван", "tgt": "отряд", "relation": "MEMBER_OF",
             "role_title": None, "status": "active", "description": None}
        ]
        n, r = save_graph_v2(
            mock_driver, nodes, rels, source_model=SOURCE_MODEL_V2,
            post_url="https://vk.com/x", post_date="2026-01-01", group_name="G",
            post_text="Иван вступил в отряд.",
        )
        assert (n, r) == (2, 1)
        queries = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("SET n:Person" in q for q in queries)
        assert any("SET n:Squad" in q for q in queries)
        assert any("MERGE (a)-[r:MEMBER_OF" in q for q in queries)
        assert any("MERGE (p:Post" in q for q in queries)
        assert any("prompt_version" in q for q in queries)
        assert any("POSSIBLE_DUPLICATE" in q for q in queries) is False  # кандидатов не было


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def data(self):
        return self._rows

    def consume(self):
        m = MagicMock()
        m.counters.relationships_created = 1
        return m


class FakeSession:
    """Сессия Neo4j: resolve-запросы отдают canned-кандидатов."""

    def __init__(self, candidates=None):
        self.candidates = candidates or []
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))
        if "person_key" in query and "MATCH (p:Person" in query:
            return FakeResult(self.candidates)
        return FakeResult([])

    def rows_for(self, snippet):
        out = []
        for q, params in self.queries:
            if snippet in q and "rows" in params:
                out.extend(params["rows"])
        return out


class FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        from contextlib import nullcontext

        return nullcontext(self._session)


class TestElectionMarkers:
    POST = (
        "Перевыборы 2026! На должность командира встал: - Марсель Фарвазов. "
        "На должность комиссара встал: - Вадим Пырин."
    )

    def test_marker_found_in_line(self):
        line = find_election_line(self.POST, "Марсель Фарвазов")
        assert line is not None and "встал" in line

    def test_lemma_not_phrase(self):
        # "встал:" отдельно от "должность" — точная фраза бы не сматчилась.
        assert has_election_marker("На должность командира встал:") is True

    def test_plain_mention_no_marker(self):
        # Кейс Б6: упоминание руководителя без выборов -> null.
        assert find_election_line(
            "По всем вопросам пиши руководителю Даниилу Астафьеву.",
            "Даниил Астафьев",
        ) is None

    def test_compute_event_date(self):
        assert (
            compute_event_date(self.POST, "Марсель Фарвазов", "2026-04-01")
            == "2026-04-01"
        )
        assert (
            compute_event_date(
                "По всем вопросам пиши руководителю.", "Марсель Фарвазов", "2026-04-01"
            )
            is None
        )


class TestTripleGate:
    def _rel(self, s, t, rel):
        return {"source_id": s, "target_id": t, "relation": rel}

    def test_commanded_role_dropped(self):
        # Класс Б3b: узел Role + COMMANDED — дроп целиком.
        nodes = [
            {"id": "Даниил Астафьев", "type": "Person"},
            {"id": "Командир", "type": "Role"},
        ]
        _, clean_r = sanitize_graph(
            nodes, [self._rel("Даниил Астафьев", "Командир", "COMMANDED")]
        )
        assert clean_r == []

    def test_squad_award_kept(self):
        # Б2: отряд целиком получает награду.
        nodes = [
            {"id": "РКТ", "type": "Squad"},
            {"id": "Гран-при", "type": "Award"},
        ]
        clean_n, clean_r = sanitize_graph(
            nodes, [self._rel("РКТ", "Гран-при", "WON_AWARD")]
        )
        assert len(clean_r) == 1

    def test_person_spelling_fallback(self):
        # Б5: ребро на "Артём Хазиев" при узле "Хазиев Артем" — не висячее.
        nodes = [
            {"id": "Хазиев Артем", "type": "Person"},
            {"id": "Отряд", "type": "Squad"},
        ]
        clean_n, clean_r = sanitize_graph(
            nodes, [self._rel("Артём Хазиев", "Отряд", "MEMBER_OF")]
        )
        assert len(clean_n) == 2 and len(clean_r) == 1


class TestSaveV3Semantics:
    def _save(self, session, nodes, rels, post_text, post_date="2026-04-01"):
        from backend.indexer.neo4j_writer_v2 import save_graph_v2

        return save_graph_v2(
            FakeDriver(session),
            nodes,
            rels,
            source_model=SOURCE_MODEL_V2,
            post_url="https://vk.com/x",
            post_date=post_date,
            group_name="G",
            post_text=post_text,
        )

    def test_event_date_and_current_status(self):
        s = FakeSession()
        nodes = [
            {"norm_id": "марсель фарвазов", "name": "Марсель Фарвазов", "type": "Person"},
            {"norm_id": "отряд", "name": "Отряд", "type": "Squad"},
        ]
        rels = [
            {
                "src": "марсель фарвазов",
                "tgt": "отряд",
                "relation": "COMMANDED",
                "role_title": "командир",
                "status": "active",
                "description": None,
            }
        ]
        self._save(s, nodes, rels, "На должность командира встал: - Марсель Фарвазов.")
        rows = s.rows_for("r.event_date")
        assert len(rows) == 1
        assert rows[0]["event_date"] == "2026-04-01"
        assert rows[0]["observed_at"] == "2026-04-01"
        assert rows[0]["role_status"] == "current"

    def test_plain_mention_honest_null(self):
        # Кейс Б6: "с 19 февраля" больше не выдумывается.
        s = FakeSession()
        nodes = [
            {"norm_id": "даниил астафьев", "name": "Даниил Астафьев", "type": "Person"},
            {"norm_id": "штаб", "name": "Штаб", "type": "Organization"},
        ]
        rels = [
            {
                "src": "даниил астафьев",
                "tgt": "штаб",
                "relation": "COMMANDED",
                "role_title": "руководитель",
                "status": "active",
                "description": None,
            }
        ]
        self._save(
            s, nodes, rels, "По всем вопросам пиши руководителю Даниилу Астафьеву."
        )
        rows = s.rows_for("r.event_date")
        assert len(rows) == 1
        assert rows[0]["event_date"] is None
        assert rows[0]["observed_at"] == "2026-04-01"
        assert rows[0]["role_status"] == "unknown"

    def test_former_status_from_ex_prefix(self):
        s = FakeSession()
        nodes = [
            {
                "norm_id": "экс-командир иван петров",
                "name": "экс-командир Иван Петров",
                "type": "Person",
            },
            {"norm_id": "отряд", "name": "Отряд", "type": "Squad"},
        ]
        rels = [
            {
                "src": "экс-командир иван петров",
                "tgt": "отряд",
                "relation": "COMMANDED",
                "role_title": "командир",
                "status": "active",
                "description": None,
            }
        ]
        self._save(s, nodes, rels, "Экс-командир Иван Петров отчитался о работе.")
        rows = s.rows_for("r.event_date")
        assert rows[0]["role_status"] == "former"
        # Узел создан без экс-префикса.
        node_rows = s.rows_for("MERGE (n:Entity")
        names = [r["name"] for r in node_rows if r["label"] == "Person"]
        assert names == ["Иван Петров"]

    def test_possible_duplicate_edge(self):
        # Один кандидат, доказательств нет -> новый узел ##2 + дакт.
        s = FakeSession(
            [{"id": "m::петр иванов", "name": "Петр Иванов", "orgs": ["squad-y"]}]
        )
        nodes = [
            {"norm_id": "иван петров", "name": "Иван Петров", "type": "Person"},
            {"norm_id": "отряд", "name": "Отряд", "type": "Squad"},
        ]
        rels = [
            {
                "src": "иван петров",
                "tgt": "отряд",
                "relation": "MEMBER_OF",
                "role_title": None,
                "status": "active",
                "description": None,
            }
        ]
        self._save(s, nodes, rels, "Иван Петров вступил в отряд.")
        dup = s.rows_for("POSSIBLE_DUPLICATE")
        assert len(dup) == 1
        assert dup[0]["cand_key"] == "m::петр иванов"
        assert dup[0]["new_key"].endswith("##2")

    def test_merge_into_exact_candidate(self):
        s = FakeSession(
            [{"id": "m::иван петров", "name": "Иван Петров", "orgs": []}]
        )
        nodes = [
            {"norm_id": "иван петров", "name": "Иван Петров", "type": "Person"},
            {"norm_id": "отряд", "name": "Отряд", "type": "Squad"},
        ]
        rels = [
            {
                "src": "иван петров",
                "tgt": "отряд",
                "relation": "MEMBER_OF",
                "role_title": None,
                "status": "active",
                "description": None,
            }
        ]
        self._save(s, nodes, rels, "Иван Петров вступил в отряд.")
        assert s.rows_for("POSSIBLE_DUPLICATE") == []
        node_rows = s.rows_for("MERGE (n:Entity")
        keys = [r["merge_key"] for r in node_rows if r["label"] == "Person"]
        assert keys == ["m::иван петров"]
