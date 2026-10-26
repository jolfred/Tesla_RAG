"""Read a saved Wiki tar into an offline HTML catalogue; never modify the Wiki.

Rendering uses markdown-it-py 4.0.0 and mdit-py-plugins 0.5.0 (footnotes).
Only public Markdown members are copied, with their original bytes and hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin


STYLE = """body{margin:0;background:#f5f4f0;color:#252525;font:17px/1.7 system-ui,sans-serif}
main{max-width:960px;margin:auto;padding:28px;background:white;min-height:100vh}
a{color:#235baa;overflow-wrap:anywhere}h1,h2{font-family:Georgia,serif;line-height:1.3}
h1{font-size:32px}h2{border-bottom:1px solid #ddd;padding-bottom:6px;margin-top:32px}
.banner{background:#fff4cd;border-left:4px solid #a66a00;padding:12px 16px;margin:20px 0}
.muted,small{color:#626262}input{box-sizing:border-box;padding:12px;width:100%;font:inherit}
li{margin:6px 0}table{border-collapse:collapse;display:block;overflow-x:auto}
th,td{padding:7px 12px;border:1px solid #ccc}pre{overflow-x:auto;background:#f3f3f3;padding:12px}
code{font-size:90%}.missing{color:#626262;text-decoration:underline dotted}
@media(max-width:640px){main{padding:18px}h1{font-size:26px}}
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def public_slug(name: str) -> str | None:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return None
    parts = list(p.parts)
    if parts[:2] == ["storage", "wiki"]:
        parts = parts[2:]
    elif parts[:1] == ["wiki"]:
        parts = parts[1:]
    if not parts or any(s.startswith(("_", ".")) for s in parts):
        return None
    if parts[-1].lower() in {"agents.md", "log.md"} or not parts[-1].endswith(".md"):
        return None
    slug = "/".join(parts)[:-3]
    return slug if re.fullmatch(r"[a-z0-9_]+(?:/[a-z0-9_]+)*", slug) else None


def rel(target: Path, current: Path) -> str:
    return quote(Path(os.path.relpath(target, current.parent)).as_posix(), safe="/#")


def shell(title: str, body: str, label: str) -> str:
    return ('<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow">'
            f'<title>{html.escape(title)} — архив Летописи</title><style>{STYLE}</style>'
            f'<main><div class="banner"><b>{html.escape(label)}</b><br>'
            'Сохранённые тексты до массовой обработки. Статьи доступны для чтения.</div>'
            f'{body}</main></html>')


def export(archive: Path, out: Path, label: str) -> dict:
    if out.exists():
        raise ValueError("Output must be a new directory")
    articles = {}
    excluded_stub_pages = 0
    with tarfile.open(archive) as tar:
        for member in tar:
            slug = public_slug(member.name)
            if not member.isfile() or slug is None:
                continue
            if member.size > 2_000_000 or slug in articles:
                raise ValueError(f"Duplicate or oversized public page: {slug}")
            data = tar.extractfile(member).read()
            text = data.decode("utf-8-sig")
            front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
            body = text[front.end():] if front else text
            meta = front.group(1) if front else ""
            if re.search(r"(?m)^status:\s*stub\s*$", meta):
                excluded_stub_pages += 1
                continue
            heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
            alias = re.search(r"(?m)^slug:\s*['\"]?([a-z0-9_/]+)", meta)
            articles[slug] = {"bytes": data, "body": body, "title": heading.group(1) if heading else slug,
                              "alias": alias.group(1) if alias else slug, "member": member.name}
    if not articles:
        raise ValueError("No public Markdown pages")
    aliases = dict((slug, slug) for slug in articles)
    counts = Counter(p["alias"] for p in articles.values())
    basenames = Counter(PurePosixPath(slug).name for slug in articles)
    for slug, page in articles.items():
        if counts[page["alias"]] == 1:
            aliases.setdefault(page["alias"], slug)
        if basenames[PurePosixPath(slug).name] == 1:
            aliases.setdefault(PurePosixPath(slug).name, slug)
    out.mkdir(parents=True)
    manifest = {"archive": archive.name, "archive_sha256": digest(archive.read_bytes()),
                "label": label, "articles": {}, "missing_wikilinks": [],
                "excluded_stub_pages": excluded_stub_pages,
                "renderer": {p: importlib.metadata.version(p) for p in ("markdown-it-py", "mdit-py-plugins")}}
    for slug, page in articles.items():
        path = out / "pages" / (slug + ".html")
        raw = out / "markdown" / (slug + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(page["bytes"])

        def wikilink(match):
            key = match.group(1).strip().removesuffix(".md")
            text = match.group(2) or articles.get(aliases.get(key), {}).get("title", key)
            dest = aliases.get(key)
            if dest:
                # Label is parsed as Markdown text, never injected as HTML.
                text = re.sub(r"([\\\[\]])", r"\\\1", text)
                return f'[{text}]({rel(out / "pages" / (dest + ".html"), path)})'
            manifest["missing_wikilinks"].append({"from": slug, "target": key})
            return text + " (нет в опубликованной копии)"

        body = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", wikilink, page["body"])
        md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough").use(footnote_plugin)
        tokens = md.parse(body)
        for token in tokens:
            for child in token.children or []:
                if child.type != "link_open":
                    continue
                href = child.attrGet("href") or ""
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc or href.startswith("#"):
                    continue
                if href.endswith(".html"):
                    continue
                key = unquote(parsed.path).removeprefix("/wiki/").removesuffix(".md")
                if key in aliases:
                    child.attrSet("href", rel(out / "pages" / (aliases[key] + ".html"), path) +
                                  ("#" + parsed.fragment if parsed.fragment else ""))
                elif href.startswith("/api/v1/wiki/source?"):
                    child.attrSet("href", "https://sotesla.ru" + href)
                else:
                    child.attrs.pop("href", None)
                    child.attrSet("class", "missing")
                    child.attrSet("title", "Файл источника не входит в этот снимок: " + href)
        rendered = md.renderer.render(tokens, md.options, {})
        nav = f'<nav><a href="{rel(out / "index.html", path)}">Все старые статьи</a> · <a href="{rel(raw, path)}">Исходный текст</a></nav>'
        path.write_text(shell(page["title"], nav + rendered, label), encoding="utf-8")
        manifest["articles"][slug] = {"title": page["title"], "archive_member": page["member"],
                                      "sha256": digest(page["bytes"]), "html": path.relative_to(out).as_posix()}
    rows = []
    for slug in sorted(articles, key=lambda s: articles[s]["title"].casefold()):
        title = articles[slug]["title"]
        rows.append(f'<li><a href="{rel(out / "pages" / (slug + ".html"), out / "index.html")}">{html.escape(title)}</a> <small>{html.escape(slug)}</small></li>')
    body = ('<h1>Летопись до массовой обработки</h1>'
            f'<p>{len(articles)} сохранённых статей. Дата архива — 5 октября 2026 года.</p>'
            '<label for="search">Найти старую статью</label><input id="search" type="search" placeholder="Название или имя">'
            '<p id="count" class="muted"></p><ul id="articles">' + "".join(rows) + '</ul>'
            '<p><a href="manifest.json">Состав архива и контрольные суммы</a></p>'
            '<script>const input=document.getElementById("search"),rows=[...document.querySelectorAll("#articles li")];'
            'input.addEventListener("input",()=>{let n=0;for(const r of rows){r.hidden=!r.textContent.toLocaleLowerCase("ru").includes(input.value.toLocaleLowerCase("ru"));if(!r.hidden)n++}document.getElementById("count").textContent="Найдено: "+n});</script>')
    (out / "index.html").write_text(shell("Каталог старой вики", body, label), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"articles": len(articles), "output": str(out), "archive_sha256": manifest["archive_sha256"],
            "missing_wikilinks": len(manifest["missing_wikilinks"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", default="Снимок до массовой обработки · архив от 5 октября 2026")
    args = parser.parse_args()
    print(json.dumps(export(args.archive, args.output, args.label), ensure_ascii=False))
