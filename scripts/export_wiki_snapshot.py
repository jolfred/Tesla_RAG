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
import shutil
import tarfile
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin


FULL_NAME = 'Штаб СО КГЭУ «Тесла»'
CATEGORY_NAMES = {'persons': 'Люди', 'people': 'Люди', 'events': 'События',
                  'lso': 'Отряды', 'hq': 'Штаб', 'projects': 'Проекты',
                  'heritage': 'Традиции', 'tradition': 'Традиции',
                  'methodology': 'Методика', 'rso': 'РСО', 'wiki': 'Летопись'}
STYLE = """*{box-sizing:border-box}body{margin:0;background:#f8f9fa;color:#202122;font:15px/1.65 Arial,Helvetica,sans-serif}
a{color:#36c;text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:underline}button,input{font:inherit}
.header{min-height:51px;padding:6px 15px;background:white;border-bottom:1px solid #a2a9b1;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:9px;color:#202122;flex-shrink:0}.brand:hover{text-decoration:none}
.brand img{width:36px;height:36px;border-radius:6px}.brand span{font:20px/1.05 Georgia,serif}.brand small{display:block;font:12px/1.5 Arial,sans-serif;color:#54595d;margin-top:2px}
.search{display:flex;width:370px;max-width:100%;min-width:180px}.search input{width:100%;min-width:0;height:30px;border:1px solid #a2a9b1;padding:4px 10px;font-size:13px;border-radius:2px 0 0 2px}
.search button{border:1px solid #a2a9b1;border-left:0;background:#f8f9fa;color:#202122;padding:3px 13px;font-size:13px;border-radius:0 2px 2px 0;cursor:pointer}
.archive-badge{margin-left:auto;font-size:11px;color:#72777d;white-space:nowrap}
.layout{display:grid;grid-template-columns:207px minmax(0,1fr);min-height:calc(100vh - 51px);max-width:1440px;margin:auto}
.sidebar{padding:24px 25px 30px 15px;font-size:12px;line-height:1.7}.sidebar h2{font:11px/1.5 Arial,sans-serif;color:#54595d;border-bottom:1px solid #c8ccd1;margin:5px 0 5px;padding-bottom:2px}
.sidebar ul{list-style:none;padding:0;margin:0 0 15px}.sidebar li{margin:0 0 2px}.sidebar .selected{font-weight:bold;color:#202122}
main{background:white;border-left:1px solid #a2a9b1;border-right:1px solid #a2a9b1;padding:17px 24px 40px;min-width:0}
.back,.subtitle{font-size:12px;line-height:1.5}.subtitle{color:#54595d;margin:1px 0 5px}.archive-note{color:#72777d;font-size:12px;margin-bottom:12px}
h1,h2{font-family:Georgia,'Times New Roman',serif;font-weight:400;line-height:1.15}h1{font-size:34px;border-bottom:1px solid #a2a9b1;margin:5px 0 9px;padding-bottom:6px}
h2{font-size:23px;border-bottom:1px solid #a2a9b1;margin:29px 0 8px;padding-bottom:3px;scroll-margin-top:16px}h3{font-size:18px;margin:23px 0 7px;scroll-margin-top:16px}
p{margin:9px 0;line-height:1.65}li{margin:3px 0}ul,ol{padding-left:20px}blockquote{margin:16px 0;padding-left:16px;border-left:3px solid #c8ccd1;color:#54595d}
.toc{border:1px solid #a2a9b1;background:#f8f9fa;padding:8px 14px;margin:17px 0 27px;font-size:12px;line-height:1.3}
.toc strong{display:block;margin:0 0 4px}.toc ol{margin:0;padding-left:19px}.toc li{margin:1px 0}.toc .level3{margin-left:14px}
table{border-collapse:collapse;display:block;max-width:100%;overflow-x:auto;margin:14px 0;font-size:14px}th,td{padding:7px 10px;border:1px solid #a2a9b1}th{background:#eaecf0;text-align:left}
pre{overflow-x:auto;background:#f8f9fa;padding:12px;border:1px solid #eaecf0}code{font-size:90%}.missing{color:#626262;text-decoration:underline dotted}
.article-footer{border-top:1px solid #c8ccd1;margin-top:30px;padding-top:10px;font-size:12px;color:#54595d}.catalog li{margin:6px 0}.catalog small{color:#72777d;margin-left:7px;font-size:11px}
.catalog-note{font-size:13px;color:#54595d}img{max-width:100%;height:auto}[hidden]{display:none!important}
@media(min-width:1441px){.header{padding-left:max(15px,calc((100vw - 1440px)/2 + 15px))}}
@media(max-width:680px){.header{gap:9px;padding:9px 14px}.brand{width:100%}.search{width:100%}.layout{grid-template-columns:1fr}.sidebar{padding:10px 16px;border-bottom:1px solid #c8ccd1}.sidebar h2,.sidebar .categories{display:none}.sidebar .navigation{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0}.sidebar li{margin:0}main{border:0;padding:16px 17px 30px}h1{font-size:27px}h2{font-size:22px}.toc{padding:9px 12px}}
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


def shell(title: str, body: str, label: str, current: Path, out: Path, categories: Counter) -> str:
    catalog = rel(out / 'index.html', current)
    category_links = ''.join(f'<li><a href="{catalog}?cat={quote(cat)}">{html.escape(CATEGORY_NAMES.get(cat, cat))} · {n}</a></li>'
                             for cat, n in categories.most_common())
    return ('<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow">'
            f'<title>{html.escape(title)} — Летопись · {FULL_NAME}</title><style>{STYLE}</style>'
            f'<header class="header"><a class="brand" href="{catalog}"><img src="{rel(out / "assets/logo.jpg", current)}" alt="{FULL_NAME}">'
            f'<span>Летопись<small>{FULL_NAME}</small></span></a>'
            f'<form class="search" action="{catalog}" role="search"><input type="search" name="q" aria-label="Поиск статей" placeholder="Поиск по Летописи"><button>Найти</button></form>'
            f'<span class="archive-badge" title="{html.escape(label, quote=True)}">Архив · 05.10.2026</span></header>'
            '<div class="layout"><aside class="sidebar"><nav aria-label="Навигация"><h2>Навигация</h2><ul class="navigation">'
            f'<li><a href="{catalog}">Заглавная страница</a></li><li><a href="{catalog}?random=1">Случайная статья</a></li>'
            '<li><a href="https://sotesla.ru/">На основной сайт</a></li></ul>'
            f'<h2>Категории</h2><ul class="categories">{category_links}</ul></nav></aside>'
            f'<main>{body}</main></div></html>')


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
                              "alias": alias.group(1) if alias else slug, "member": member.name,
                              "category": slug.split('/')[0] if '/' in slug else 'wiki'}
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
    (out / 'assets').mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'frontend/src/assets/logos/tesla.jpg', out / 'assets/logo.jpg')
    categories = Counter(page['category'] for page in articles.values())
    manifest = {"archive": archive.name, "archive_sha256": digest(archive.read_bytes()),
                "label": label, "articles": {}, "missing_wikilinks": [],
                "excluded_stub_pages": excluded_stub_pages,
                "presentation": "wiki_reference_layout_v2",
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
        toc = []
        ids = Counter()
        for i, token in enumerate(tokens):
            if token.type == 'heading_open' and token.tag in ('h2', 'h3'):
                inline = tokens[i + 1]
                text = ''.join(c.content for c in inline.children or [] if c.type in ('text', 'code_inline'))
                anchor = re.sub(r'[^a-zа-яё0-9_]', '', re.sub(r'[\s\-–—]+', '_', text.lower())).strip('_') or 'section'
                ids[anchor] += 1
                unique = anchor if ids[anchor] == 1 else f'{anchor}_{ids[anchor]}'
                token.attrSet('id', unique)
                toc.append((unique, text, token.tag))
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
        if toc:
            contents = '<nav class="toc" aria-label="Содержание"><strong>Содержание</strong><ol>' + ''.join(
                f'<li class="{"level3" if level == "h3" else "level2"}"><a href="#{anchor}">{html.escape(text)}</a></li>' for anchor, text, level in toc) + '</ol></nav>'
            rendered = rendered.replace('<h2 ', contents + '<h2 ', 1) if '<h2 ' in rendered else contents + rendered
        nav = (f'<a class="back" href="{rel(out / "index.html", path)}">← Все статьи</a>'
               '<p class="subtitle">Материал из отрядной википедии</p>')
        footer = f'<footer class="article-footer"><a href="{rel(raw, path)}">Исходный текст статьи</a> · <a href="{rel(out / "manifest.json", path)}">Состав архивной копии</a></footer>'
        path.write_text(shell(page["title"], nav + rendered + footer, label, path, out, categories), encoding="utf-8")
        manifest["articles"][slug] = {"title": page["title"], "archive_member": page["member"],
                                      "sha256": digest(page["bytes"]), "html": path.relative_to(out).as_posix()}
    rows = []
    for slug in sorted(articles, key=lambda s: articles[s]["title"].casefold()):
        title = articles[slug]["title"]
        rows.append(f'<li data-category="{articles[slug]["category"]}"><a href="{rel(out / "pages" / (slug + ".html"), out / "index.html")}">{html.escape(title)}</a> <small>{html.escape(slug)}</small></li>')
    body = ('<h1>Летопись до массовой обработки</h1>'
            f'<p>{len(articles)} сохранённых статей. Дата архива — 5 октября 2026 года.</p>'
            '<p id="count" class="catalog-note" aria-live="polite"></p><ul class="catalog" id="articles">' + "".join(rows) + '</ul>'
            '<footer class="article-footer"><a href="manifest.json">Состав архива и контрольные суммы</a></footer>'
            '<script>const input=document.querySelector("input[name=q]"),rows=[...document.querySelectorAll("#articles li")],params=new URLSearchParams(location.search);'
            'if(params.has("random"))location.replace(rows[Math.floor(Math.random()*rows.length)].querySelector("a").href);'
            'input.value=params.get("q")||"";function filter(){let n=0;for(const r of rows){r.hidden=!!((params.get("cat")&&r.dataset.category!==params.get("cat"))||!r.textContent.toLocaleLowerCase("ru").includes(input.value.toLocaleLowerCase("ru")));if(!r.hidden)n++}document.getElementById("count").textContent="Найдено статей: "+n}input.addEventListener("input",filter);filter();</script>')
    (out / "index.html").write_text(shell("Каталог старой вики", body, label, out / 'index.html', out, categories), encoding="utf-8")
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
