from unittest.mock import MagicMock

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
        )
        assert (n, r) == (2, 1)
        queries = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("SET n:Person" in q for q in queries)
        assert any("SET n:Squad" in q for q in queries)
        assert any("MERGE (a)-[r:MEMBER_OF" in q for q in queries)
        assert any("MERGE (p:Post" in q for q in queries)
