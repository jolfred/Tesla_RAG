"""Offline-first, source-addressed ingestion ledger for the wiki."""
from __future__ import annotations

import hashlib
import datetime
import json
import os
import re
import sqlite3
from urllib.parse import parse_qs, quote, unquote, urlparse
from pathlib import Path
from typing import Any, Iterable

POST_ID = re.compile(r"^wall-?\d+_\d+$")
ARCHIVE_ID = re.compile(r"^archive:(chronicle_part_\d{3}\.txt):L([1-9]\d*)-L([1-9]\d*)$")
GROUP_ID = re.compile(r"^group:([A-Za-z0-9][A-Za-z0-9._-]*)$")
CLASSES = {"role", "event", "award", "tradition", "social", "noise"}
STATES = {"queued", "extracted", "applied", "verified", "skipped", "review", "legacy_processed"}


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS posts(
        post_id TEXT NOT NULL, source_hash TEXT NOT NULL, source_path TEXT NOT NULL,
        source_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(post_id, source_hash));
      CREATE TABLE IF NOT EXISTS facts(
        id INTEGER PRIMARY KEY, post_id TEXT NOT NULL, source_hash TEXT NOT NULL,
        ordinal INTEGER NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
        reason TEXT, page_path TEXT, rendered TEXT,
        UNIQUE(post_id, source_hash, ordinal),
        FOREIGN KEY(post_id,source_hash) REFERENCES posts(post_id,source_hash));
      CREATE TABLE IF NOT EXISTS applied(
        marker TEXT PRIMARY KEY, page_path TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
      CREATE TABLE IF NOT EXISTS proposals(
        page_slug TEXT PRIMARY KEY, expected_sha256 TEXT, markdown TEXT NOT NULL,
        source_post_ids TEXT NOT NULL, fact_refs TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL, reason TEXT);
    """)
    try: con.execute("ALTER TABLE proposals ADD COLUMN fact_refs TEXT NOT NULL DEFAULT '[]'")
    except sqlite3.OperationalError: pass
    return con


def identity(post: dict[str, Any]) -> tuple[str, str, str]:
    pid = str(post.get("post_id") or "").strip()
    url = str(post.get("post_url") or "")
    source_kind = post.get("source_kind")
    if source_kind == "archive":
        match = ARCHIVE_ID.fullmatch(pid)
        if not match:
            raise ValueError("invalid typed archive post_id")
        filename, first, last = match.group(1), int(match.group(2)), int(match.group(3))
        segments = post.get("source_segments")
        if first > last or segments != [{"file": filename, "line_start": first, "line_end": last}]:
            raise ValueError("archive source_segments do not match typed post_id")
        expected_url = "/api/v1/wiki/source?ref=" + quote(pid, safe="")
        if url != expected_url:
            raise ValueError("archive post_url must be the encoded Wiki source-viewer reference")
        if post.get("archive_source_uri") != f"storage/documents/{filename}#L{first}":
            raise ValueError("archive_source_uri does not match the declared segment")
        raw = str(post.get("text_raw") or "")
        return pid, hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw
    if source_kind == "group":
        match = GROUP_ID.fullmatch(pid)
        if not match:
            raise ValueError("invalid typed group post_id")
        domain = match.group(1)
        if post.get("group_domain") != domain or url != f"https://vk.com/{domain}" or post.get("published_at") is not None:
            raise ValueError("group metadata identity requires matching VK URL/domain and null published_at")
        raw = str(post.get("text_raw") or "")
        return pid, hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw
    parsed_url = urlparse(url) if url else None
    if parsed_url and parsed_url.hostname not in {"vk.com", "www.vk.com", "m.vk.com"}:
        raise ValueError("post_url is not an official VK host")
    if parsed_url:
        link_id = parse_qs(parsed_url.query).get("w", [""])[0] or parsed_url.path.rsplit("/", 1)[-1]
        if POST_ID.fullmatch(link_id) and POST_ID.fullmatch(pid) and link_id != pid:
            raise ValueError("post_id does not match the VK post_url wall ID")
    if not POST_ID.fullmatch(pid):
        # Raw VK exports commonly store only the numeric post ID. Derive its
        # canonical wall ID from a verified VK URL, then from VK group_id.
        raw_id = pid
        parsed = parsed_url
        if parsed:
            query_id = parse_qs(parsed.query).get("w", [""])[0]
            if not query_id:
                query_id = parsed.path.rsplit("/", 1)[-1]
            match = re.fullmatch(r"wall-?\d+_\d+", query_id)
            if match and query_id.rsplit("_", 1)[-1] == raw_id:
                pid = query_id
        if not POST_ID.fullmatch(pid) and raw_id.isdigit() and str(post.get("group_id", "")).lstrip("-").isdigit():
            pid = f"wall-{abs(int(post['group_id']))}_{raw_id}"
    raw_body = post.get("text_raw") if "text_raw" in post else post.get("text_clean")
    body = str(raw_body or "")
    if not POST_ID.fullmatch(pid):
        raise ValueError(f"invalid/missing post_id: {pid!r}")
    return pid, hashlib.sha256(body.encode("utf-8")).hexdigest(), body


def inventory(db: Path, source: Path, exclude: Iterable[str] = ()) -> dict[str, int]:
    con = connect(db)
    seen = added = changed = 0
    with source.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                post = json.loads(line)
                pid, sha, body = identity(post)
            except Exception as e:
                raise ValueError(f"{source}:{line_no}: {e}") from e
            domain = str(post.get("group_domain") or "")
            if domain in set(exclude):
                continue
            post["text_raw"] = body
            post["post_id"] = pid
            empty = not body.strip()
            cur = con.execute("INSERT OR IGNORE INTO posts(post_id,source_hash,source_path,source_json,state,reason) VALUES(?,?,?,?,?,?)",
                              (pid, sha, str(source), json.dumps(post, ensure_ascii=False), "skipped" if empty else "queued",
                               "empty raw source text" if empty else None))
            added += cur.rowcount
            if not cur.rowcount:
                con.execute("UPDATE posts SET source_path=?, source_json=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?",
                            (str(source), json.dumps(post, ensure_ascii=False), pid, sha))
            seen += 1
    con.commit()
    changed = con.execute("SELECT count(DISTINCT post_id) FROM posts").fetchone()[0]
    con.close()
    return {"seen": seen, "new_versions": added, "unique_post_ids": changed}


def export_posts(db: Path, limit: int = 50, state: str = "queued", max_chars: int = 40000) -> list[dict[str, Any]]:
    if not 1 <= limit <= 50:
        raise ValueError("post limit must be 1..50")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    con = connect(db)
    rows = con.execute("SELECT source_json,source_hash FROM posts WHERE state=? ORDER BY post_id LIMIT ?", (state, limit)).fetchall()
    con.close()
    posts = []
    used = 0
    for r in rows:
        post = json.loads(r[0]); body = post.get("text_raw", "")
        if posts and used + len(body) > max_chars: break
        post["source_hash"] = r[1]; posts.append(post); used += len(body)
        # One oversize post is still exported whole, as the only item in its batch.
        if used >= max_chars: break
    return posts


def relevant_pages(wiki: Path, query: str, limit: int = 5) -> list[dict[str, str]]:
    """Lexically retrieve existing pages only; never expose more than five."""
    pages = []
    for entry in relevant_page_catalog(wiki, query, limit):
        text = (wiki / (entry["page_slug"] + ".md")).read_text(encoding="utf-8")
        pages.append({"page_slug":entry["page_slug"], "expected_sha256":hashlib.sha256(text.encode()).hexdigest(), "markdown":text})
    return pages


def relevant_page_catalog(wiki: Path, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Small extraction context: page identity/title/headings, never full articles."""
    if not 1 <= limit <= 5: raise ValueError("page limit must be 1..5")
    terms = {w.casefold() for w in re.findall(r"[\w-]{3,}", query)}
    source_ids = set(re.findall(r"wall-?\d+_\d+", query))
    ranked = []
    for path in wiki.rglob("*.md"):
        if any(part.startswith("_") for part in path.relative_to(wiki).parts) or path.name in {"AGENTS.md", "log.md"}: continue
        if not path.is_file() or not path.resolve().is_relative_to(wiki.resolve()): continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if re.search(r"(?m)^status:\s*['\"]?stub['\"]?\s*$", content): continue
        slug = str(path.relative_to(wiki).with_suffix(""))
        title_match = re.search(r"(?m)^#\s+(.+)$", content)
        title = title_match.group(1).strip() if title_match else path.stem
        # The extraction handoff accepts level-two sections only.
        headings = re.findall(r"(?m)^##\s+.+$", content)
        identity_text = (slug + " " + title).casefold()
        full_text = content.casefold()
        score = sum((8 if term in identity_text else 1) * min(full_text.count(term), 2) for term in terms)
        generic = {"штаб", "ссо", "спо", "осд", "школа", "студенческих", "отрядов", "тесла",
                   "студенческий", "отряд", "реестр", "персон", "сквозная", "хронология", "кгэу"}
        title_terms = {w.casefold() for w in re.findall(r"[\w-]{3,}", title)} - generic
        matched = title_terms & terms
        if matched:
            score += 200 * len(matched) / len(title_terms)
            if matched == title_terms:
                score += 300
        score += 500 * sum(source_id in content for source_id in source_ids)
        if score: ranked.append((score, slug, title, headings))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [{"page_slug":s,"title":t,"headings":h[:40]} for _,s,t,h in ranked[:limit]]


def _date_ok(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value):
        return False
    parts = [int(part) for part in value.split("-")]
    try:
        datetime.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return False
    return True


def validate_post_result(result: dict[str, Any], known: dict[tuple[str, str], str]) -> list[tuple[dict[str, Any], str | None]]:
    pid = str(result.get("post_id", ""))
    sha = str(result.get("source_hash", ""))
    if (pid, sha) not in known:
        raise ValueError(f"unknown post_id/source_hash pair: {pid!r}/{sha!r}")
    if not sha:
        raise ValueError(f"{pid}: source_hash missing or mismatched")
    body = known[(pid, sha)]
    outcome = result.get("outcome", "extracted")
    if outcome in ("refused", "error"):
        return []
    if outcome != "extracted" or not isinstance(result.get("items"), list):
        raise ValueError(f"{pid}: outcome must be extracted/refused/error with items array")
    validated = []
    for item in result["items"]:
        why = None
        if not isinstance(item, dict) or item.get("class") not in CLASSES:
            why = "invalid class/item"
        elif item.get("confidence") not in ("high", "medium", "low"):
            why = "invalid confidence"
        elif not isinstance(item.get("joke_flag"), bool):
            why = "joke_flag must be boolean"
        elif not _date_ok(item.get("date_event")):
            why = "date_event must be YYYY, YYYY-MM, YYYY-MM-DD, or null"
        elif item.get("role_scope") is not None and item.get("role_scope") not in {"squad", "Tesla HQ", "regional HQ", "project", "other"}:
            why = "invalid role_scope"
        elif item.get("class") == "role" and item.get("date_event") is None:
            why = "role time period is not confirmed"
        elif item.get("class") == "role" and item.get("role_scope") is None:
            why = "role management level is not confirmed"
        elif item.get("status") is not None and item.get("status") not in {"planned", "verified", "uncertain"}:
            why = "invalid status"
        elif not isinstance(item.get("facts"), list):
            why = "facts must be array"
        else:
            for fact in item["facts"]:
                quote = fact.get("quote") if isinstance(fact, dict) else None
                if not isinstance(quote, str) or not quote.strip() or quote not in body:
                    why = "quote is not an exact substring of raw source"
                    break
                if not isinstance(fact.get("detail"), str) or not fact["detail"].strip():
                    why = "fact detail missing"
                    break
                if (item.get("class") == "event" and item.get("status") == "verified"
                        and re.search(r"\b(?:провед[её]т|проведут|предстоит|состоится|состоятся)\b", quote, re.IGNORECASE)):
                    why = "future event described as verified; requires review"
                    break
                if not isinstance(item.get("page_slug"), str) or not re.fullmatch(r"[a-z0-9_/-]+", item["page_slug"]):
                    why = "invalid page_slug"
                    break
                if not isinstance(item.get("section"), str) or not item["section"].startswith("## "):
                    why = "section must be an explicit level-two heading"
                    break
        validated.append((item, why))
    return validated


def import_results(db: Path, handoff: Path) -> dict[str, int]:
    data = json.loads(handoff.read_text(encoding="utf-8"))
    results = data.get("posts") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise ValueError("handoff must contain a posts array")
    con = connect(db)
    known = {(r["post_id"], r["source_hash"]): json.loads(r["source_json"]).get("text_raw", "")
             for r in con.execute("SELECT * FROM posts")}
    counts = {"extracted": 0, "review": 0, "refused": 0, "skipped": 0}
    for result in results:
        pid = str(result.get("post_id", ""))
        sha = str(result.get("source_hash", ""))
        if (pid, sha) not in known:
            raise ValueError(f"unknown post_id/source_hash pair: {pid!r}/{sha!r}")
        if not sha:
            raise ValueError(f"{pid}: source_hash missing or mismatched")
        outcome = result.get("outcome", "extracted")
        if outcome in ("refused", "error"):
            con.execute("UPDATE posts SET state='review', reason=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?",
                        (str(result.get("reason") or outcome), pid, sha))
            counts["refused"] += 1
            continue
        validated = validate_post_result(result, known)
        if not validated:
            con.execute("UPDATE posts SET state='skipped', reason='no supported facts extracted', updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?", (pid, sha))
            counts["skipped"] += 1
            continue
        fact_states=[]
        for n, (item, why) in enumerate(validated):
            state = "review" if why or item.get("confidence") != "high" or item.get("joke_flag") else "extracted"
            reason = why or ("low/medium confidence" if item.get("confidence") != "high" else "April-Fools/joke flag") if state == "review" else None
            if item.get("class") == "noise":
                state, reason = "skipped", "classified noise; retained with source/result"
            con.execute("INSERT OR REPLACE INTO facts(post_id,source_hash,ordinal,payload,state,reason,page_path) VALUES(?,?,?,?,?,?,?)",
                        (pid, sha, n, json.dumps(item, ensure_ascii=False), state, reason, item.get("page_slug")))
            fact_states.append(state)
            counts[state if state in counts else "review"] += 1
        if fact_states and all(x == "skipped" for x in fact_states):
            post_state, why = "skipped", "all extracted items classified as non-wiki/noise"
        elif "extracted" in fact_states:
            post_state, why = "extracted", None
        else:
            post_state, why = "review", "all extracted facts require review"
        con.execute("UPDATE posts SET state=?, reason=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?", (post_state, why, pid, sha))
    con.commit(); con.close()
    return counts


def _render(pid: str, item: dict[str, Any], source_url: str | None = None) -> str:
    date = item.get("date_event")
    when = f"{date} — " if date else ""
    bits = []
    for f in item.get("facts", []):
        quote = f["quote"].replace("\n", " ").strip()
        href = source_url or (f"https://vk.com/{pid}" if pid.startswith("group:") else f"https://vk.com/{pid}" if pid.startswith("wall") else "")
        citation = f"[источник {pid}]({href})" if href else f"источник {pid}"
        bits.append(f"{when}{f['detail'].strip()} (Источник: {citation}, цитата: «{quote}»).")
    return "\n".join("- " + x for x in bits)


def apply(db: Path, wiki: Path) -> dict[str, int]:
    con = connect(db)
    rows = con.execute("SELECT f.*,p.post_id,p.source_json FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state='extracted' ORDER BY p.post_id,f.ordinal").fetchall()
    done = review = 0
    for row in rows:
        item = json.loads(row["payload"])
        rel = Path(item["page_slug"] + ("" if item["page_slug"].endswith(".md") else ".md"))
        page = (wiki / rel).resolve()
        if wiki.resolve() not in page.parents or not page.is_file():
            con.execute("UPDATE facts SET state='review',reason=? WHERE id=?", ("target page missing or outside wiki", row["id"]))
            review += 1; continue
        marker = f"<!-- wiki-ingest:{row['post_id']}:{row['source_hash']}:{row['ordinal']} -->"
        text = page.read_text(encoding="utf-8")
        if marker in text:
            con.execute("INSERT OR IGNORE INTO applied(marker,page_path) VALUES(?,?)", (marker, str(rel)))
            con.execute("UPDATE facts SET state='applied',rendered=? WHERE id=?", (marker, row["id"]))
            _refresh_post_state(con, row["post_id"], row["source_hash"])
            done += 1; continue
        section = item["section"]
        match = re.search(rf"(?m)^{re.escape(section)}\s*$", text)
        if not match:
            con.execute("UPDATE facts SET state='review',reason=? WHERE id=?", (f"section not found: {section}", row["id"]))
            review += 1; continue
        source = json.loads(row["source_json"])
        rendered = _render(row["post_id"], item, source.get("post_url"))
        if not rendered:
            con.execute("UPDATE facts SET state='review',reason=? WHERE id=?", ("no renderable facts", row["id"]))
            review += 1; continue
        insertion = marker + "\n" + rendered + "\n\n"
        # Durable page write before the ledger transition; marker makes recovery idempotent.
        updated = text[:match.end()] + "\n\n" + insertion + text[match.end():]
        tmp = page.with_suffix(page.suffix + ".ingest-tmp")
        tmp.write_text(updated, encoding="utf-8")
        tmp.replace(page)
        con.execute("INSERT OR IGNORE INTO applied(marker,page_path) VALUES(?,?)", (marker, str(rel)))
        con.execute("UPDATE facts SET state='applied',rendered=? WHERE id=?", (rendered, row["id"]))
        _refresh_post_state(con, row["post_id"], row["source_hash"])
        done += 1
    con.commit(); con.close()
    return {"applied": done, "review": review}


def retrieval_pack(db: Path, wiki: Path, query: str, limit: int = 5) -> dict[str, Any]:
    """Return candidate facts and at most five relevant pages for editorial merge."""
    if not 1 <= limit <= 5:
        raise ValueError("page limit must be 1..5")
    con = connect(db)
    words = {w.lower() for w in re.findall(r"[\w-]{3,}", query)}
    facts = []
    for r in con.execute("SELECT f.payload,p.post_id,p.source_hash FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state IN ('extracted','review')"):
        fact = json.loads(r[0]); fact["post_id"] = r[1]; fact["source_hash"] = r[2]; facts.append(fact)
    slugs = {x.get("page_slug") for x in facts if x.get("page_slug")}
    scored = []
    for slug in slugs:
        path = wiki / (slug + ("" if slug.endswith(".md") else ".md"))
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            score = sum(w in (slug + " " + content).lower() for w in words)
            scored.append((score, slug, content))
    con.close(); scored.sort(key=lambda x: (-x[0], x[1]))
    return {"facts": facts, "pages": [{"page_slug": s, "sha256": hashlib.sha256(t.encode()).hexdigest(), "expected_sha256": hashlib.sha256(t.encode()).hexdigest(), "markdown": t}
                                      for _, s, t in scored[:limit]]}


def stage_proposals(db: Path, wiki: Path, handoff: Path, *, insertion_only: bool = False) -> dict[str, int]:
    data = json.loads(handoff.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise ValueError("merge handoff must contain pages array")
    con = connect(db); staged = review = 0
    known_sources = {(r[0], r[1]): json.loads(r[2]) for r in con.execute(
        "SELECT DISTINCT f.post_id,f.source_hash,p.source_json FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state IN ('extracted','review','applied')")}
    known_pairs = set(known_sources)
    pending_facts = {(r[0], r[1], r[2]): json.loads(r[3]) for r in con.execute(
        "SELECT post_id,source_hash,ordinal,payload FROM facts WHERE state='extracted'")}
    all_slugs = {str(p.relative_to(wiki).with_suffix('')) for p in wiki.rglob('*.md')}
    for prop in data["pages"]:
        slug = prop.get("page_slug", "")
        if not re.fullmatch(r"[a-z0-9_/-]+", slug) or ".." in Path(slug).parts:
            raise ValueError("invalid page slug: " + repr(slug))
        page = wiki / (slug + ("" if slug.endswith(".md") else ".md"))
        if wiki.resolve() not in page.resolve().parents:
            raise ValueError("page slug resolves outside wiki")
        content, ids, refs, covered = prop.get("markdown"), prop.get("source_post_ids"), prop.get("source_refs"), prop.get("covered_facts")
        # Repeating the same grounded source for two fact groups adds no provenance.
        # Normalize exact duplicates; conflicting or unknown hashes still fail below.
        if isinstance(refs, list) and all(isinstance(ref, dict) and isinstance(ref.get("post_id"), str)
                                         and isinstance(ref.get("source_hash"), str) for ref in refs):
            refs = list({(ref["post_id"], ref["source_hash"]): ref for ref in refs}.values())
        if isinstance(ids, list) and all(isinstance(pid, str) for pid in ids):
            ids = list(dict.fromkeys(ids))
        if "patches" in prop and prop.get("new_page") is not True:
            patches = prop["patches"]
            if not page.is_file() or not isinstance(patches, list) or (content is not None and patches):
                raise ValueError("existing-page patches require a target and markdown=null")
            content = page.read_text(encoding="utf-8")
            for patch in patches:
                if not isinstance(patch, dict) or not all(isinstance(patch.get(key), str) for key in ("old_text", "new_text")):
                    raise ValueError("patch requires old_text and new_text strings")
                operation = patch.get("operation", "replace")
                if operation not in {"replace", "insert_after"}:
                    raise ValueError("unsupported patch operation")
                if insertion_only and operation != "insert_after":
                    raise ValueError("routine compilation requires insert_after patches")
                anchor, replacement = patch["old_text"], patch["new_text"]
                if anchor:
                    if content.count(anchor) != 1:
                        raise ValueError("patch anchor must occur exactly once")
                    if operation == "insert_after":
                        replacement = anchor + "\n" + replacement
                    content = content.replace(anchor, replacement, 1)
                else:
                    content = content.rstrip() + "\n\n" + replacement.strip() + "\n"
        reason = None
        if insertion_only and prop.get("new_page") is not True and not isinstance(prop.get("patches"), list):
            raise ValueError("routine compilation requires insertion patches, not a full article rewrite")
        if not isinstance(content, str) or not re.search(r"(?m)^#\s+\S", content):
            reason = "proposal lacks an article heading"
        elif not isinstance(refs, list) or not refs or len({json.dumps([x.get("post_id"), x.get("source_hash")], sort_keys=True) for x in refs if isinstance(x, dict)}) != len(refs) or any(not isinstance(x, dict) or (x.get("post_id"), x.get("source_hash")) not in known_pairs for x in refs):
            reason = "source_refs must bind each post ID to a known ledger text hash"
        elif not isinstance(ids, list) or not ids or set(ids) != {x["post_id"] for x in refs}:
            reason = "source_post_ids must match source_refs"
        elif not isinstance(covered, list) or not covered or len({json.dumps([x.get("post_id"), x.get("source_hash"), x.get("ordinal")], sort_keys=True) for x in covered if isinstance(x, dict)}) != len(covered) or any(not isinstance(x, dict) or
                (x.get("post_id"), x.get("source_hash"), x.get("ordinal")) not in pending_facts or
                pending_facts[(x.get("post_id"), x.get("source_hash"), x.get("ordinal"))].get("page_slug") != slug
                for x in covered):
            reason = "covered_facts must identify pending facts routed to this page"
        elif {(x["post_id"], x["source_hash"]) for x in covered} != {(x["post_id"], x["source_hash"]) for x in refs}:
            reason = "source_refs must match covered_facts"
        elif {(x["post_id"], x["source_hash"], x["ordinal"]) for x in covered} != {
                (pid, sha, ordinal) for (pid, sha, ordinal), fact in pending_facts.items() if fact.get("page_slug") == slug}:
            reason = "covered_facts must account for every pending fact routed to this page"
        elif any(pid not in unquote(content) for pid in ids):
            reason = "proposal must visibly cite each declared post ID"
        elif any(str(known_sources[(ref["post_id"], ref["source_hash"])].get("post_url") or
                         ("https://vk.com/" + ref["post_id"] if ref["post_id"].startswith("wall-") else "")) not in content for ref in refs):
            reason = "proposal must include a source link for every source_ref"
        elif prop.get("new_page") is True:
            if page.exists():
                reason = "new page target already exists"
            elif slug in all_slugs:
                reason = "new page slug collides with an existing page"
            elif not content.startswith("---\n") or len(content.split("---", 2)) < 3 or not all(re.search(rf"(?m)^{field}:\s*.+$", content.split("---", 2)[1]) for field in ("slug", "kind", "status", "title", "tags")):
                reason = "new page frontmatter requires slug, kind, status, title, and tags"
            elif any(link not in all_slugs and link != slug and not (wiki / (link + ".md")).is_file() for link in re.findall(r"\[\[([^]|]+)", content)):
                reason = "new page contains unresolved wikilink"
        elif not page.is_file():
            reason = "target page missing; use new_page=true to stage creation"
        else:
            old = page.read_text(encoding="utf-8")
            digest = hashlib.sha256(old.encode()).hexdigest()
            if prop.get("expected_sha256") != digest:
                reason = "original page hash mismatch"
            elif len(content.strip()) < len(old.strip()) * 0.8:
                reason = "proposal removed substantial existing content"
            elif old.startswith("---\n") and (not content.startswith("---\n") or any(
                    match and not re.search(rf"(?m)^{field}:\s*{re.escape(match.group(1))}\s*$", content.split("---", 2)[1])
                    for field in ("slug", "kind", "norm_id", "status", "title", "tags")
                    for match in [re.search(rf"(?m)^{field}:\s*(.*)$", old.split("---", 2)[1])])):
                reason = "proposal changed protected frontmatter"
            elif set(re.findall(r"\[\[([^]|]+)", old)) - set(re.findall(r"\[\[([^]|]+)", content)):
                reason = "proposal removed existing wiki links"
            elif any(line.split("Источник:", 1)[0].rstrip(" (`") not in content for line in old.splitlines()
                     if "Источник:" in line and line.split("Источник:", 1)[0].rstrip(" (`")):
                reason = "proposal dropped a protected cited fact line"
            elif set(re.findall(r"\[[^\]]*\]\(((?:https?://|/api/v1/wiki/source\?)[^)]+)\)", old)) - set(
                    re.findall(r"\[[^\]]*\]\(((?:https?://|/api/v1/wiki/source\?)[^)]+)\)", content)):
                reason = "proposal removed existing source links"
            elif any(link not in all_slugs and not (wiki / (link + ".md")).is_file() for link in re.findall(r"\[\[([^]|]+)", content)):
                reason = "unresolved wikilink"
        state = "review" if reason else "staged"
        expected = "NEW" if prop.get("new_page") is True and not reason else prop.get("expected_sha256")
        con.execute("INSERT OR REPLACE INTO proposals(page_slug,expected_sha256,markdown,source_post_ids,fact_refs,state,reason) VALUES(?,?,?,?,?,?,?)",
                    (slug, expected, content or "", json.dumps(refs or [], ensure_ascii=False), json.dumps(covered or [], ensure_ascii=False), state, reason))
        if reason: review += 1
        else: staged += 1
    con.commit(); con.close(); return {"staged": staged, "review": review}


def apply_proposals(db: Path, wiki: Path) -> dict[str, int]:
    con = connect(db); done = review = 0
    for p in con.execute("SELECT * FROM proposals WHERE state='staged'").fetchall():
        page = wiki / (p["page_slug"] + ("" if p["page_slug"].endswith(".md") else ".md"))
        if wiki.resolve() not in page.resolve().parents:
            con.execute("UPDATE proposals SET state='review',reason='target resolves outside wiki' WHERE page_slug=?", (p["page_slug"],)); review += 1; continue
        marker = "<!-- wiki-merge:" + hashlib.sha256((p["page_slug"] + p["expected_sha256"]).encode()).hexdigest() + " -->"
        if page.is_file() and marker in page.read_text(encoding="utf-8"):
            _mark_proposal_sources(con, p["fact_refs"])
            con.execute("UPDATE proposals SET state='applied' WHERE page_slug=?", (p["page_slug"],)); done += 1; continue
        if p["expected_sha256"] == "NEW":
            if page.exists():
                con.execute("UPDATE proposals SET state='review',reason='new page target appeared after staging' WHERE page_slug=?", (p["page_slug"],)); review += 1; continue
            page.parent.mkdir(parents=True, exist_ok=True)
            proposed = p["markdown"].rstrip() + "\n\n" + marker + "\n"
            tmp = page.with_suffix(page.suffix + ".merge-tmp")
            tmp.write_text(proposed, encoding="utf-8")
            try:
                os.link(tmp, page)
            except FileExistsError:
                con.execute("UPDATE proposals SET state='review',reason='new page target appeared during apply' WHERE page_slug=?", (p["page_slug"],)); review += 1; tmp.unlink(missing_ok=True); continue
            tmp.unlink(missing_ok=True)
            _mark_proposal_sources(con, p["fact_refs"])
            con.execute("UPDATE proposals SET state='applied' WHERE page_slug=?", (p["page_slug"],)); done += 1; continue
        if not page.is_file() or hashlib.sha256(page.read_bytes()).hexdigest() != p["expected_sha256"]:
            con.execute("UPDATE proposals SET state='review',reason='page changed after staging' WHERE page_slug=?", (p["page_slug"],)); review += 1; continue
        tmp = page.with_suffix(page.suffix + ".merge-tmp")
        proposed = p["markdown"].rstrip() + "\n\n" + marker + "\n"
        tmp.write_text(proposed, encoding="utf-8"); tmp.replace(page)
        _mark_proposal_sources(con, p["fact_refs"])
        con.execute("UPDATE proposals SET state='applied' WHERE page_slug=?", (p["page_slug"],)); done += 1
    con.commit(); con.close(); return {"applied_pages": done, "review": review}


def _mark_proposal_sources(con: sqlite3.Connection, encoded_fact_refs: str) -> None:
    affected = set()
    for fact in json.loads(encoded_fact_refs):
        pid, sha, ordinal = fact["post_id"], fact["source_hash"], fact["ordinal"]
        con.execute("UPDATE facts SET state='applied',reason=NULL WHERE post_id=? AND source_hash=? AND ordinal=? AND state='extracted'", (pid, sha, ordinal))
        affected.add((pid, sha))
    for pid, sha in affected: _refresh_post_state(con, pid, sha)


def _refresh_post_state(con: sqlite3.Connection, pid: str, sha: str) -> None:
    if con.execute("SELECT 1 FROM facts WHERE post_id=? AND source_hash=? AND state='extracted' LIMIT 1", (pid, sha)).fetchone():
        state = "extracted"
    elif con.execute("SELECT 1 FROM facts WHERE post_id=? AND source_hash=? AND state='review' LIMIT 1", (pid, sha)).fetchone():
        state = "review"
    else:
        state = "applied"
    con.execute("UPDATE posts SET state=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?", (state, pid, sha))


def ledger_view(db: Path, state: str | None = None) -> list[dict[str, Any]]:
    con = connect(db)
    if state:
        rows = con.execute("SELECT post_id,source_hash,state,reason,source_path FROM posts WHERE state=? ORDER BY post_id", (state,)).fetchall()
    else:
        rows = con.execute("SELECT post_id,source_hash,state,reason,source_path FROM posts ORDER BY post_id").fetchall()
    out = [dict(r) for r in rows]; con.close(); return out


def verify_posts(db: Path, pairs: list[tuple[str, str]]) -> int:
    con = connect(db); changed = 0
    for pid, sha in pairs:
        cur = con.execute("UPDATE posts SET state='verified',reason=NULL,updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=? AND state IN ('applied','extracted','review')", (pid, sha))
        con.execute("UPDATE facts SET state='verified',reason=NULL WHERE post_id=? AND source_hash=? AND state IN ('applied','extracted','review')", (pid, sha))
        changed += cur.rowcount
    con.commit(); con.close(); return changed
