"""Бэкфилл person_key на Person-узлах сида групп (E1).

Сид (group_indexer_v2) пишет командиров из карточек старым путём — без
person_key. Без бэкфилла resolve_person их не находит (lookup идёт по
person_key) и постовые упоминания тех же людей создают дубли.
Скрипт детерминирован (canon.person_key), идемпотентен, перепроизводим.

Запуск: .venv/bin/python -m backend.scripts.backfill_person_key
"""

from backend.common.canon import person_key
from backend.common.ontology import SOURCE_MODEL_V2
from backend.utils.logger import setup_logger

logger = setup_logger("backfill_person_key")


def main() -> int:
    from neo4j import GraphDatabase

    import os

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "tesla_neo4j")),
    )
    updated = 0
    with driver.session() as session:
        rows = session.run(
            "MATCH (p:Person {source_model: $m}) "
            "WHERE p.person_key IS NULL RETURN p.merge_key AS k, p.name AS name",
            m=SOURCE_MODEL_V2,
        ).data()
        for r in rows:
            key = person_key(r["name"] or "")
            if not key:
                continue
            session.run(
                "MATCH (p:Person {merge_key: $k}) "
                "SET p.person_key = $key, p.prompt_version = 'v3-seed'",
                k=r["k"],
                key=list(key),
            )
            updated += 1
    driver.close()
    logger.info("Backfilled person_key on %d Person nodes", updated)
    print(f"backfilled: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
