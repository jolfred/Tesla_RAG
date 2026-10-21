"""Prepare source-audit candidates; no model calls, semantic verdicts or DB access."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlparse

SEED = "tesla-source-audit-v1-2026-10-21"
CATEGORIES = {
    "role": "Должности и годы",
    "event": "События и даты",
    "bio": "Организационные и биографические сведения",
}
EXCLUDED_EXPORTS = {"posts_kgeu_official.jsonl", "posts_spoyunost.jsonl"}
ROLE = re.compile(r"командир|комиссар|\bмастер(?:а|ом|у|ы|ов|ами|ах|е)?\b|методист|руководител|пресс-секретар", re.I)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
DATE = re.compile(r"\b\d{1,2}(?:[–—-]\d{1,2})?\s+(?:январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)|\b\d{4}-\d\d-\d\d\b|\b\d\d\.\d\d\.(?:19|20)\d\d\b", re.I)
EVENT = re.compile(r"прош[еёлли]|состоя|пров[еёлд]|организова|откры[лт]|закры[лт]|отме[тч]|встре[тч]|отправ|принял|приняли|участ|выступ|получ|награжд|занял", re.I)
BIO = re.compile(r"основан|основа[лт]|образован|создан|участв|работал|работа[ею]|входи[лт]|вош[еёл]|явля|талисман|родил|день рождения|направление|объедин|называ|названи|переимен|девиз|подар|награжд|удосто|побед|занял", re.I)
URL = re.compile(r"\[[^\]\n]*\]\((https?://[^\s)]+|/api/v1/wiki/source\?[^\s)]+)\)")
WALL = re.compile(r"wall-?\d+_\d+")
PRIVATE = re.compile(r"противореч|дискусс|расхожд|источники данных|редактор|техническ", re.I)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def visible(text: str) -> str:
    text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    return text.replace("**", "").replace("`", "")


def pool_for_article(path: str, text: str) -> list[dict]:
    """First declarative sentence of eligible prose/bullet lines, exact slices."""
    rows = []
    heading = ""
    title_match = re.search(r"(?m)^# (.+)$", text)
    title = title_match[1] if title_match else path
    frontmatter_end = text.find("\n---", 4) + 4 if text.startswith("---\n") else 0
    offset = 0
    private_level = None
    for line_no, raw in enumerate(text.splitlines(keepends=True), 1):
        line = raw.rstrip("\r\n")
        start = offset
        offset += len(raw)
        if start < frontmatter_end:
            continue
        h = re.match(r"^(#{1,6})\s+(.+)", line)
        if h:
            level = len(h[1])
            if private_level is not None and level <= private_level:
                private_level = None
            if PRIVATE.search(h[2]):
                private_level = level
            heading = h[2]
            continue
        if private_level is not None or not line.strip() or line.startswith(("<!--", "```", ">")):
            continue
        if line.startswith("|"):
            # Leadership tables have an explicit period + role + organization level.
            # Retain these cells verbatim; the article title supplies the person.
            parts = line.split("|")
            if not path.startswith("persons/") or "Должности" not in heading or len(parts) < 6:
                continue
            claim = "|".join(parts[:4]) + "|"
            if not ROLE.search(parts[2]) or not YEAR.search(parts[1]):
                continue
            begin = start
            rows.append({"category": "role", "article": path, "title": title, "heading": heading,
                "line": line_no, "claim": claim, "claim_span": [begin, begin + len(claim)],
                "context_line": line, "citation_urls": list(dict.fromkeys(URL.findall(line))),
                "citation_scope": "same table row; all source links, no inferred adjacent citation",
                "rank": digest((SEED + f"\0role\0{path}\0{begin}\0{claim}").encode())})
            continue
        prefix = re.split(r"\s*\(?Источники?:", line, maxsplit=1)[0].rstrip(" (`")
        prefix = re.sub(r"^\s*[-*]\s+", "", prefix)
        # Do not split initials, abbreviations, dates or punctuation inside links.
        masked = list(prefix)
        for m in re.finditer(r"\[\[.*?\]\]|\[[^]]*\]\([^)]*\)", prefix):
            masked[m.start():m.end()] = "x" * len(m[0])
        # Parentheses may contain dates and abbreviations. Keep them intact.
        for m in re.finditer(r"\([^()]*\)", prefix):
            masked[m.start():m.end()] = "x" * len(m[0])
        end = re.search(r"[.!?](?:\s+(?=[А-ЯЁA-Z«0-9*])|$)|;", "".join(masked))
        claim = prefix[:end.end()].rstrip() if end else prefix
        plain = visible(claim)
        if not 45 <= len(plain) <= 550 or not re.search(r"[а-яё]", plain):
            continue
        if re.search(r"нет данных|неизвест|не зафиксирован|см\.|^\*?\*?(?:Статус|Отряд|Штаб|Домен|Сообщество|Университет):", plain, re.I):
            continue
        category = None
        if EVENT.search(plain) and DATE.search(plain):
            category = "event"
        elif BIO.search(plain):
            category = "bio"
        if category is None:
            continue
        begin = start + line.index(claim)
        key = f"{category}\0{path}\0{begin}\0{claim}"
        rows.append({
            "category": category, "article": path, "title": title, "heading": heading,
            "line": line_no, "claim": claim, "claim_span": [begin, begin + len(claim)],
            "context_line": line, "citation_urls": list(dict.fromkeys(URL.findall(line))),
            "citation_scope": "same physical line; all links, no inferred adjacent citation",
            "rank": digest((SEED + "\0" + key).encode()),
        })
    return rows


def choose(pool: list[dict]) -> list[dict]:
    selected = []
    # Source presence and content play no part in rank or eligibility.
    for category in CATEGORIES:
        used_articles = set()
        ordered = sorted((x for x in pool if x["category"] == category), key=lambda x: x["rank"])
        chosen = []
        for item in ordered:
            if item["article"] in used_articles:
                continue
            used_articles.add(item["article"])
            chosen.append(item.copy())
            if len(chosen) == 7:
                break
        if len(chosen) != 7:
            raise ValueError(f"Insufficient article diversity for {category}")
        for number, item in enumerate(chosen):
            base = list(CATEGORIES).index(category) * 5
            item["id"] = f"{base + number + 1:02}" if number < 5 else f"R-{category}-{number - 4:02}"
            item["sample"] = "primary" if number < 5 else "reserve"
            selected.append(item)
    return selected


def quote_window(body: str, claim: str) -> tuple[str, list[int]]:
    """Mechanical lexical suggestion, never an entailment decision."""
    tokens = {t[:6] for t in re.findall(r"[а-яёa-z0-9]+", visible(claim).lower()) if len(t) >= 4}
    units = list(re.finditer(r"[^\n]+", body))
    if not units:
        return "", [0, 0]
    scores = []
    for i, unit in enumerate(units):
        end = units[min(i + 2, len(units) - 1)].end()
        part = body[unit.start():end]
        overlap = len(tokens & {t[:6] for t in re.findall(r"[а-яёa-z0-9]+", part.lower()) if len(t) >= 4})
        scores.append((overlap, -len(part), -unit.start(), unit.start(), end))
    best = max(scores)
    return body[best[3]:best[4]], [best[3], best[4]]


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    if out.exists():
        raise SystemExit("Refusing to overwrite an existing preparation.")
    if not out.is_relative_to(root / "experiments/wiki-source-audit/materials"):
        raise SystemExit("Output must be inside experiments/wiki-source-audit/materials/.")
    started = datetime.now(timezone.utc).isoformat()
    snapshot = {}
    pool = []
    for p in sorted((root / "storage/wiki").rglob("*.md")):
        rel = p.relative_to(root / "storage/wiki")
        if p.is_symlink() or any(s.startswith(("_", ".")) for s in rel.parts) or p.name == "AGENTS.md":
            continue
        data = p.read_bytes()
        snapshot[rel.as_posix()] = data
        pool.extend(pool_for_article(rel.as_posix(), data.decode("utf-8")))
    selected = choose(pool)
    # Freeze selection before opening the publication archive.
    dump(out / "selection-before-source-lookup.json", selected)
    dump(out / "pool.json", sorted(pool, key=lambda x: (x["category"], x["rank"])))
    for rel, data in snapshot.items():
        target = out / "wiki-snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    needed = {m[0] for x in selected for u in x["citation_urls"] if (m := WALL.search(unquote(u)))}
    records = {pid: [] for pid in needed}
    read_archives = {}
    for p in sorted((root / "storage/posts").glob("*.jsonl")):
        if p.name in EXCLUDED_EXPORTS:
            continue
        data = p.read_bytes()
        read_archives[p.relative_to(root).as_posix()] = digest(data)
        for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            m = WALL.search(unquote(str(raw.get("post_url", ""))))
            if not m or m[0] not in needed:
                continue
            pid = m[0]
            raw_pid = str(raw.get("post_id", ""))
            group_id = str(raw.get("group_id", "")).lstrip("-")
            derived = raw_pid if WALL.fullmatch(raw_pid) else f"wall-{group_id}_{raw_pid}" if group_id.isdigit() and raw_pid.isdigit() else None
            body_field = "text_raw" if "text_raw" in raw else "text_clean"
            body = str(raw.get(body_field) or "")
            rec = {"post_id": pid, "archive": p.relative_to(root).as_posix(), "archive_line": number,
                   "url_from_record": raw.get("post_url"), "raw_post_id": raw_pid,
                   "derived_id_from_fields": derived, "identifier_matches": derived == pid,
                   "published_at": raw.get("published_at"), "body_field": body_field,
                   "body": body, "body_sha256": digest(body.encode()), "raw": raw}
            records[pid].append(rec)
    groups = {}
    for p in sorted((root / "storage/groups").glob("groups_*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            groups[str(raw.get("domain", ""))] = (p, raw)
    for item in selected:
        item["article_sha256"] = digest(snapshot[item["article"]])
        item["semantic_status"] = "Не проверено"
        item["temporal_status"] = "Не проверено"
        item["external_access"] = "Не проверено; HTTP-ответ не доказывает читаемость публикации"
        sources = []
        for url in item["citation_urls"]:
            entry = {"cited_url": url, "external_access": "not_checked", "records": []}
            m = WALL.search(unquote(url))
            if m:
                entry["post_id"] = m[0]
                entry["records"] = records[m[0]]
            else:
                domain = urlparse(url).path.strip("/")
                if urlparse(url).hostname in {"vk.com", "vk.ru", "www.vk.com"} and domain in groups:
                    p, raw = groups[domain]
                    entry["records"] = [{"post_id": "group:" + domain, "archive": p.relative_to(root).as_posix(),
                        "archive_line": None, "published_at": None, "publication_date_note": "Undated saved group description, not a post",
                        "identifier_matches": raw.get("domain") == domain, "body_field": "description",
                        "body": str(raw.get("description") or ""), "body_sha256": digest(str(raw.get("description") or "").encode()), "raw": raw}]
                    read_archives[p.relative_to(root).as_posix()] = digest(p.read_bytes())
            entry["archive_found"] = bool(entry["records"])
            for rec in entry["records"]:
                quote, span = quote_window(rec["body"], item["claim"])
                # Copy per item: shared sources can have different quote suggestions.
                rec = rec.copy()
                rec["suggested_quote"], rec["quote_span"] = quote, span
                rec["quote_exact_match"] = rec["body"][span[0]:span[1]] == quote
                rec["quote_note"] = "Lexical overlap suggestion only; no semantic confirmation"
                sourcefile = f"cases/{item['id']}/source-{len(sources) + 1}-record-{len(entry.get('record_files', [])) + 1}.json"
                dump(out / sourcefile, rec)
                entry.setdefault("record_files", []).append(sourcefile)
            entry.pop("records")
            sources.append(entry)
        item["sources"] = sources
        item["archive_found_for_any_cited_url"] = any(s["archive_found"] for s in sources)
        dump(out / "cases" / item["id"] / "candidate.json", item)
    dump(out / "candidates.json", selected)
    # Verify a stable content snapshot; timestamps/SQLite are not touched.
    current_paths = {p.relative_to(root / "storage/wiki").as_posix() for p in (root / "storage/wiki").rglob("*.md")
                     if not p.is_symlink() and p.name != "AGENTS.md" and not any(s.startswith(("_", ".")) for s in p.relative_to(root / "storage/wiki").parts)}
    if current_paths != set(snapshot):
        raise RuntimeError("Wiki article set changed during preparation")
    for rel, data in snapshot.items():
        if (root / "storage/wiki" / rel).read_bytes() != data:
            raise RuntimeError("Wiki changed during preparation: " + rel)
    for rel, sha in read_archives.items():
        if digest((root / rel).read_bytes()) != sha:
            raise RuntimeError("Source archive changed during preparation: " + rel)
    manifest = {
        "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip(),
        "wiki_hashes": {p: digest(b) for p, b in snapshot.items()},
        "wiki_snapshot_sha256": digest(json.dumps({p: digest(b) for p, b in sorted(snapshot.items())}, sort_keys=True).encode()),
        "seed": SEED, "sampling": "SHA256(seed NUL category NUL path NUL character_offset NUL exact_claim), ascending; one article per category; first 5 primary, next 2 reserves",
        "pool_counts": dict(Counter(x["category"] for x in pool)), "article_count": len(snapshot),
        "source_archive_hashes": read_archives, "excluded_exports": sorted(EXCLUDED_EXPORTS),
        "generator_sha256": digest(Path(__file__).read_bytes()),
        "uncited_pool_counts": dict(Counter(x["category"] for x in pool if not x["citation_urls"])),
        "selection_approved": False,
        "scope": "role: period/role/level cells in persons leadership tables; event/bio: first sentence or semicolon unit of visible prose/bullet lines; no frontmatter/private sections; not representative of all Wiki statements",
        "source_lookup_after_selection": True, "llm_calls": 0, "sqlite_connections": 0,
        "external_urls_checked": 0, "stage": "1: awaiting user sample approval; no semantic judgments",
    }
    dump(out / "manifest.json", manifest)
    render(out, selected, manifest)
    dump(out / "checksums.json", {p.relative_to(out).as_posix(): digest(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()})
    print(json.dumps({"output": str(out), "pool": manifest["pool_counts"], "primary": 15, "reserve": 6, "wiki_snapshot_sha256": manifest["wiki_snapshot_sha256"]}, ensure_ascii=False))


def render(out: Path, items: list[dict], manifest: dict) -> None:
    intro = ["# Кандидаты: достоверность исторических утверждений Wiki", "",
        "**Этап 1. Нужны утверждение выборки и затем ручные оценки Альфреда. Итоговых статусов нет.**", "",
        f"Снимок: {manifest['started_at_utc']}; Git `{manifest['commit']}` (Git не версионирует контент Wiki).",
        f"SHA-256 снимка {manifest['article_count']} статей: `{manifest['wiki_snapshot_sha256']}`.", "",
        "15 основных утверждений (по 5 на категорию) и 6 резервных (по 2). Выборка зафиксирована до поиска источников. "
        "Резерв не подменяет неудачные результаты после утверждения. Правила отбора и ограничения: README.md проекта исследования.", "",
        "Ни наличие ссылки, ни совпадение цитаты не подтверждают смысл утверждения. Предложенная цитата найдена по пересечению слов; "
        "полный текст прилагается для ручной проверки. Внешние публикации на этом этапе не открывались. "
        "Наличие архивной копии и возможность прочесть внешний оригинал учитываются раздельно.", "",
        "| ID | Категория | Точное утверждение | Статья и строка | Ссылки в статье | Архив | Оценки |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    full = []
    cards = []
    csvrows = []
    evaluation = ["# Лист ручной оценки — не заполнен", "", "Сначала Альфред утверждает выборку. После этого только он определяет смысловое подтверждение и временной контекст. "
        "Значение «Не проверено» не равно Unverifiable или Unclear. ID с префиксом R — резерв, не входят в знаменатель 15.", "",
        "| ID | Категория | Утверждение | Источник | Подтверждение | Дата | Комментарий |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for x in items:
        links = "<br>".join(f"[источник {i + 1}]({s['cited_url']})" for i, s in enumerate(x["sources"])) or "Нет в строке"
        archive = "Есть" if x["archive_found_for_any_cited_url"] else "Нет записи / нет ссылки"
        intro.append(f"| [{x['id']}](cases/{x['id']}/REVIEW.md){' (резерв)' if x['sample'] == 'reserve' else ''} | {CATEGORIES[x['category']]} | {cell(x['claim'])} | `{x['article']}:{x['line']}` | {links} | {archive} | Не проверено |")
        evaluation.append(f"| {x['id']} | {CATEGORIES[x['category']]} | {cell(x['claim'])} | {links} | Не проверено | Не проверено | |")
        text = [f"# {x['id']}: {x['title']}", "", f"Категория: {CATEGORIES[x['category']]}; {'основная выборка' if x['sample'] == 'primary' else 'резерв'}.", "",
            f"Статья: `storage/wiki/{x['article']}:{x['line']}`; раздел «{x['heading']}».",
            f"SHA-256 статьи: `{x['article_sha256']}`; точный диапазон символов `[start,end)`: {x['claim_span']}.", "",
            "## Точная формулировка из Wiki", "", "```text", x["claim"], "```", "",
            "## Полная строка и привязка источников", "", "```text", x["context_line"], "```", "",
            "Все ссылки взяты из той же физической строки. Если ссылка относится к абзацу целиком, это ещё не доказывает, "
            "что она подтверждает выбранное предложение. Ссылки соседних строк автоматически не приписывались.", ""]
        bodyhtml = f"<h3>Точное утверждение</h3><pre>{html.escape(x['claim'])}</pre><p>storage/wiki/{html.escape(x['article'])}:{x['line']} · {html.escape(x['title'])}</p>"
        if not x["sources"]:
            text += ["Ссылка на источник в строке отсутствует. Архивная публикация не подбиралась по догадке.", ""]
            bodyhtml += "<p>В строке нет ссылки. Архивный источник не подбирался по догадке.</p>"
        dates, quotes = [], []
        for i, source in enumerate(x["sources"], 1):
            text += [f"## Источник {i}", "", source["cited_url"], "", "Внешняя доступность: не проверено.",
                     f"Архивная запись: {'найдена' if source['archive_found'] else 'не найдена в разрешённых экспортах'}.", ""]
            bodyhtml += f"<h3>Источник {i}</h3><p><a href='{html.escape(source['cited_url'], quote=True)}'>{html.escape(source['cited_url'])}</a></p><p>Внешняя доступность не проверена; архив: {'найден' if source['archive_found'] else 'не найден'}.</p>"
            for filename in source.get("record_files", []):
                rec = json.loads((out / filename).read_text(encoding="utf-8"))
                date = rec.get("published_at") or "В записи отсутствует"
                dates.append(date)
                quotes.append(rec["suggested_quote"])
                text += [f"### Архивная копия: {rec['post_id']}", "", f"Файл: `{rec['archive']}`; строка: {rec.get('archive_line')}. Дата публикации: {date}.",
                    f"Хэш полного текста: `{rec['body_sha256']}`. Поле: `{rec['body_field']}`. ID совпадает: {rec['identifier_matches']}.", "",
                    "**Предположительный фрагмент (механический подбор, не вывод о достоверности):**", "", "```text", rec["suggested_quote"], "```", "",
                    f"Точное совпадение в тексте: {rec['quote_exact_match']}; диапазон: {rec['quote_span']}.", "",
                    "**Полный текст публикации:**", "", "```text", rec["body"], "```", ""]
                bodyhtml += f"<p>Архив: {html.escape(rec['archive'])}:{rec.get('archive_line')} · Дата публикации: {html.escape(date)}</p><h4>Предположительный фрагмент — без оценки смысла</h4><pre>{html.escape(rec['suggested_quote'])}</pre><details><summary>Полный текст архивной публикации</summary><pre>{html.escape(rec['body'])}</pre></details>"
        text += ["## Ручное решение Альфреда", "", "- Утверждение кандидата: ожидается.", "- Достоверность: Не проверено (будет Supported / Contradicted / Unverifiable).", "- Временная корректность: Не проверено (будет Correct / Incorrect / Unclear / Not applicable).", "- Комментарий и основание: не заполнены.", ""]
        (out / "cases" / x["id"] / "REVIEW.md").write_text("\n".join(text), encoding="utf-8")
        full.extend(text + ["---", ""])
        cards.append(f"<section id='{x['id']}'><h2>{x['id']} · {CATEGORIES[x['category']]} {'(резерв)' if x['sample'] == 'reserve' else ''}</h2>{bodyhtml}<p><strong>Достоверность и временной контекст: не проверено. Решение за Альфредом.</strong></p></section>")
        csvrows.append({"ID": x["id"], "Выборка": x["sample"], "Категория": CATEGORIES[x["category"]], "Утверждение": x["claim"],
            "Статья": "storage/wiki/" + x["article"], "Строка": x["line"], "Источник": "\n".join(s["cited_url"] for s in x["sources"]),
            "Дата_публикации": "\n".join(dates), "Цитата_кандидат": "\n---\n".join(quotes),
            "Ссылка_есть": bool(x["sources"]), "Архив_есть": x["archive_found_for_any_cited_url"], "Внешняя_доступность": "Не проверено",
            "Подтверждение": "Не проверено", "Дата": "Не проверено", "Комментарий": "", "Утвердил": "", "Дата_решения": ""})
    (out / "CANDIDATES.md").write_text("\n".join(intro) + "\n", encoding="utf-8")
    (out / "manual-evaluation.md").write_text("\n".join(evaluation) + "\n", encoding="utf-8")
    (out / "ALL-MATERIALS.md").write_text("\n".join(full), encoding="utf-8")
    with (out / "manual-evaluation.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(csvrows[0]))
        writer.writeheader()
        writer.writerows(csvrows)
    nav = " · ".join(f"<a href='#{x['id']}'>{x['id']}</a>" for x in items)
    page = "<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Wiki — кандидаты аудита</title><style>body{font:16px/1.55 system-ui;background:#f7f3fc;color:#241532;max-width:1050px;margin:24px auto;padding:0 18px}section{background:white;border:1px solid #d4c2ed;border-radius:14px;padding:22px;margin:24px 0}h1,h2,a{color:#6732a1}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2ecf8;padding:15px;border-radius:8px}nav{position:sticky;top:0;background:#f7f3fc;padding:14px 0}summary{cursor:pointer;color:#6732a1}</style><h1>Источники и исторический контекст Wiki</h1><p>Этап 1: 15 основных утверждений + 6 резервных. Только подготовка. Достоверность и временной контекст оценивает Альфред после утверждения выборки.</p><p>Дата снимка: " + manifest["started_at_utc"] + "</p><p>Предложенные цитаты найдены механически по общим словам. Совпадение текста не означает подтверждения. Внешние ссылки не проверялись; полные архивные тексты сохранены.</p><nav>" + nav + "</nav>" + "".join(cards) + "</html>"
    (out / "REVIEW.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
