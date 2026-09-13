"""Запись графа v2/v3 в Neo4j: настоящие метки, батчи, provenance из кода.

Отличия v3 (Milestone B) от v2:
- Рёбра проходят validate_triple() целиком (пункт 7), а не проверку имени типа.
- Персоны резолвятся бинарно через canon.resolve_person (пункт 2):
  merge в точное совпадение либо новый узел + POSSIBLE_DUPLICATE.
  Узлы Person несут свойство person_key (blocking-ключ для lookup).
- Рёбра ролей несут observed_at (всегда = дата поста, ставит код) и
  event_date (= дата поста ТОЛЬКО при лемма-маркере выборов в строке
  с ФИО, иначе null) + role_status (пункт 6).
- Всё записанное новым пайплайном штампуется prompt_version (Milestone A).

Контракт sanitize_graph НЕ менялся (nodes {norm_id,name,type},
rels {src,tgt,relation,...}) — старые тесты зелёные.
"""

from neo4j import GraphDatabase

from backend.common.canon import (
    normalize_id,
    person_key,
    resolve_person,
)
from backend.common.ontology import (
    ALLOWED_NODES,
    PROMPT_VERSION,
    validate_triple,
)
from backend.indexer.election_markers import (
    compute_event_date,
    is_role_relation,
)
from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()

_ALLOWED_NODE_SET = set(ALLOWED_NODES)


def _endpoint_norm(raw: str) -> str | None:
    """norm_id эндпоинта. Фолбэк на person_key (Б5) — в теле sanitize."""
    norm = normalize_id((raw or "").strip())
    return norm or None


def sanitize_graph(
    nodes: list[dict], rels: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Пост-фильтр после LLM: strict-онтология, стоп-лист, синонимы.

    Узлы хранят только {norm_id, name, type} — описаний у узлов нет
    (вся фактура на рёбрах). Персоны группируются внутри поста по person_key
    (разные написания одного ФИО — один узел). Дубли схлопываются.
    nodes: [{id, type, ...}], rels: [{source_id, target_id, relation, ...}]
    Возвращает очищенные списки. Узлы без рёбер (орфаны) дропаются.
    """
    from backend.common.ontology import STOP_NODES

    kept_nodes: dict[str, dict] = {}
    person_idx: dict[tuple, str] = {}
    for n in nodes:
        raw_id = (n.get("id") or "").strip()
        ntype = (n.get("type") or "").strip()
        if not raw_id or ntype not in _ALLOWED_NODE_SET:
            continue
        if ntype == "Person":
            pkey = person_key(raw_id)
            if pkey in person_idx:
                continue  # то же ФИО другим написанием — уже есть
            norm = normalize_id(raw_id)
            if not norm or norm in STOP_NODES:
                continue
            person_idx[pkey] = norm
            kept_nodes[norm] = {"norm_id": norm, "name": raw_id, "type": ntype}
            continue
        norm = normalize_id(raw_id)
        if not norm or norm in STOP_NODES:
            logger.debug("Dropping stop/garbage node %r (%s)", raw_id, ntype)
            continue
        if norm in kept_nodes:
            if kept_nodes[norm]["type"] != ntype:
                logger.debug(
                    "Type conflict for %r: %s vs %s",
                    raw_id,
                    kept_nodes[norm]["type"],
                    ntype,
                )
        else:
            kept_nodes[norm] = {"norm_id": norm, "name": raw_id, "type": ntype}

    kept_rels: list[dict] = []
    linked: set[str] = set()
    for r in rels:
        rel = (r.get("relation") or r.get("type") or "").strip()
        s = _endpoint_norm(r.get("source_id") or "")
        t = _endpoint_norm(r.get("target_id") or "")
        if s is None or t is None:
            continue  # пустой эндпоинт
        # Фолбэк на person_key (Б5): "Артём Хазиев" в ребре при узле "Хазиев Артем".
        if s not in kept_nodes:
            s = person_idx.get(person_key(r.get("source_id") or ""))
        if t not in kept_nodes:
            t = person_idx.get(person_key(r.get("target_id") or ""))
        if not s or not t:
            continue  # висячее ребро
        if s not in kept_nodes or t not in kept_nodes:
            continue
        if s == t:
            continue  # петля на себя
        # Hard gate всей тройкой (пункт 7): Person-COMMANDED->Role не проходит,
        # хотя имя типа связи "разрешено".
        if not validate_triple(
            kept_nodes[s]["type"], rel, kept_nodes[t]["type"]
        ):
            logger.debug(
                "Dropping triple %s-%s->%s",
                kept_nodes[s]["type"],
                rel,
                kept_nodes[t]["type"],
            )
            continue
        kept_rels.append(
            {
                "src": s,
                "tgt": t,
                "relation": rel,
                "role_title": r.get("role_title"),
                "status": r.get("status") or "active",
                "description": (r.get("description") or "").strip() or None,
            }
        )
        linked.add(s)
        linked.add(t)

    # Дроп орфанов: узел без рёбер в граф не пишем.
    final_nodes = [n for k, n in kept_nodes.items() if k in linked]
    if len(final_nodes) < len(kept_nodes):
        logger.debug(
            "Dropping %d orphan nodes", len(kept_nodes) - len(final_nodes)
        )
    return final_nodes, kept_rels


def get_indexed_post_urls_v2(driver, source_model: str) -> set[str]:
    """URL постов, уже записанных веткой v2 (для resume поверх --force)."""
    with driver.session() as session:
        rows = session.run(
            "MATCH (p:Post {source_model: $m}) RETURN p.url AS url", m=source_model
        )
        return {r["url"] for r in rows if r["url"]}


def save_graph_v2(
    driver: GraphDatabase.driver,
    nodes: list[dict],
    rels: list[dict],
    source_model: str,
    post_url: str | None = None,
    post_date: str | None = None,
    group_name: str | None = None,
    post_text: str | None = None,
) -> tuple[int, int]:
    """Batch-запись одного поста. Возвращает (n_nodes, n_rels).

    post_text нужен для детерминированного event_date (пункт 6):
    без текста все ролевые факты получают event_date=null.
    """
    if not nodes:
        return 0, 0

    with driver.session() as session:
        # Орг-контекст поста для верификации персон: группа + Squad/Org из поста.
        post_orgs = {normalize_id(group_name or "")} - {""}
        post_orgs |= {
            n["norm_id"]
            for n in nodes
            if n.get("type") in ("Squad", "Organization")
        }

        # Бинарный резолв персон (пункт 2). Не-персоны — как раньше.
        resolutions: dict[str, object] = {}
        for n in nodes:
            if n.get("type") == "Person":
                resolutions[n["norm_id"]] = resolve_person(
                    n["name"], post_orgs, session, source_model
                )

        node_rows = []
        norm_to_key: dict[str, str] = {}
        for n in nodes:
            if n.get("type") == "Person":
                res = resolutions[n["norm_id"]]
                mkey = res.target_id or res.new_merge_key
                # Рёбра ссылаются sanitize-нормой; резолв мог почистить имя
                # (экс-префикс) — мэппим обе нормы на один merge_key.
                norm_to_key[n["norm_id"]] = mkey
                norm_to_key[normalize_id(res.name)] = mkey
                node_rows.append(
                    {
                        "merge_key": mkey,
                        "norm_id": normalize_id(res.name),
                        "name": res.name,
                        "label": "Person",
                        "person_key": list(res.person_key),
                        "source_model": source_model,
                    }
                )
            else:
                mkey = f"{source_model}::{n['norm_id']}"
                norm_to_key[n["norm_id"]] = mkey
                node_rows.append(
                    {
                        "merge_key": mkey,
                        "norm_id": n["norm_id"],
                        "name": n["name"],
                        "label": n["type"],
                        "person_key": None,
                        "source_model": source_model,
                    }
                )

        rel_rows = []
        for r in rels:
            src_key = norm_to_key.get(r["src"])
            tgt_key = norm_to_key.get(r["tgt"])
            if not src_key or not tgt_key:
                continue
            event_date = None
            role_status = "unknown"
            if is_role_relation(r["relation"], r.get("role_title")):
                # Источник ролевого факта — персона (см. ALLOWED_TRIPLES).
                src_res = resolutions.get(r["src"])
                person_display = src_res.name if src_res else r["src"]
                event_date = compute_event_date(
                    post_text, person_display, post_date
                )
                if src_res and src_res.is_former:
                    role_status = "former"
                elif event_date:
                    role_status = "current"
            rel_rows.append(
                {
                    "src_key": src_key,
                    "tgt_key": tgt_key,
                    "relation": r["relation"],
                    "source_model": source_model,
                    "source_post_url": post_url,
                    "observed_at": post_date,
                    "event_date": event_date,
                    "role_status": role_status,
                    "role_title": r.get("role_title"),
                    "status": r.get("status") or "active",
                    "description": r.get("description"),
                }
            )

        # Узлы: MERGE по merge_key + настоящая метка.
        # Метку параметризовать в Cypher нельзя -> один запрос на тип узла.
        by_label: dict[str, list[dict]] = {}
        for r in node_rows:
            by_label.setdefault(r["label"], []).append(r)
        for label, rows in by_label.items():
            if label not in _ALLOWED_NODE_SET:
                continue
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:Entity {{merge_key: row.merge_key}})
                SET n:{label},
                    n.norm_id = row.norm_id,
                    n.id = row.name,
                    n.name = row.name,
                    n.type = row.label,
                    n.source_model = row.source_model,
                    n.person_key = coalesce(row.person_key, n.person_key),
                    n.prompt_version = $pv
                """,
                rows=rows,
                pv=PROMPT_VERSION,
            )
        # Рёбра настоящими типами: тип параметризовать нельзя -> один
        # запрос на тип связи.
        by_type: dict[str, list[dict]] = {}
        for row in rel_rows:
            by_type.setdefault(row["relation"], []).append(row)
        n_rels = 0
        for rel_type, rows in by_type.items():
            res = session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:Entity {{merge_key: row.src_key}}),
                      (b:Entity {{merge_key: row.tgt_key}})
                MERGE (a)-[r:{rel_type} {{source_model: row.source_model}}]->(b)
                SET r.type = row.relation,
                    r.source_post_url = coalesce(row.source_post_url, r.source_post_url),
                    r.date = coalesce(row.observed_at, r.date),
                    r.observed_at = row.observed_at,
                    r.event_date = row.event_date,
                    r.role_status = row.role_status,
                    r.role_title = coalesce(row.role_title, r.role_title),
                    r.status = coalesce(row.status, r.status),
                    r.description = coalesce(row.description, r.description),
                    r.prompt_version = $pv
                """,
                rows=[{k: v for k, v in r.items() if k != "relation"} for r in rows],
                pv=PROMPT_VERSION,
            )
            n_rels += (res.consume().counters.relationships_created or 0)
        # POSSIBLE_DUPLICATE: "пометить уточнить" (пункт 2, без журнала).
        dup_rows = []
        for norm, res in resolutions.items():
            if res.action == "create" and res.possible_duplicates:
                for cand in res.possible_duplicates:
                    dup_rows.append(
                        {"new_key": res.new_merge_key, "cand_key": cand}
                    )
        if dup_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Entity {merge_key: row.new_key}),
                      (b:Entity {merge_key: row.cand_key})
                MERGE (a)-[r:POSSIBLE_DUPLICATE]->(b)
                SET r.reason = 'same person_key, no context proof',
                    r.logged_at = datetime(),
                    r.prompt_version = $pv
                """,
                rows=dup_rows,
                pv=PROMPT_VERSION,
            )
        # :Post-узел + обратный индекс.
        if post_url:
            session.run(
                """
                MERGE (p:Post {url: $url})
                SET p.published_at = coalesce($date, p.published_at),
                    p.group_name = coalesce($group, p.group_name),
                    p.source_model = $model,
                    p.prompt_version = $pv
                WITH p
                UNWIND $keys AS k
                MATCH (n:Entity {merge_key: k})
                MERGE (p)-[:DESCRIBES]->(n)
                """,
                url=post_url,
                date=post_date,
                group=group_name,
                model=source_model,
                pv=PROMPT_VERSION,
                keys=[r["merge_key"] for r in node_rows],
            )

    logger.info(
        "Saved v2 to Neo4j (%s): %d entities, %d relationships (post %s)",
        source_model,
        len(node_rows),
        len(rel_rows),
        post_url,
    )
    return len(node_rows), len(rel_rows)
