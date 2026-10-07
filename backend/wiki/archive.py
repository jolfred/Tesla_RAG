"""Audited source excerpts: named records only, with original archive line ranges."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

ARCHIVE_ID = re.compile(r"^archive:(chronicle_part_\d{3}\.txt):L(\d+)-L(\d+)$")
GROUP_ID = re.compile(r"^group:([a-z0-9_]+)$")
CURATOR_ID = re.compile(r"^curator:\d{4}-\d{2}-\d{2}:[a-z0-9_-]+$")
EXCLUDED = {"kgeu_official", "spoyunost"}


def source_url(ref: str) -> str:
    return "/api/v1/wiki/source?ref=" + quote(ref, safe="")


def read_records(wiki: Path) -> dict[str, dict]:
    path = wiki / "_source_records.json"
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, dict):
        raise ValueError("invalid source record registry")
    return records


def register_records(wiki: Path, sources: list[dict], documents: Path, groups: Path) -> int:
    """Check excerpts against local primary sources before exposing a stable source URL."""
    records = read_records(wiki)
    for source in sources:
        ref = str(source.get("post_id", ""))
        domain = source.get("group_domain")
        if domain in EXCLUDED:
            raise ValueError("excluded source group")
        match = ARCHIVE_ID.fullmatch(ref)
        group_match = GROUP_ID.fullmatch(ref)
        if match and source.get("source_kind") == "archive":
            segments = source.get("source_segments")
            if not isinstance(segments, list) or not 1 <= len(segments) <= 8:
                raise ValueError("archive record requires bounded source_segments")
            first = segments[0]
            if (first.get("file"), first.get("line_start"), first.get("line_end")) != (match[1], int(match[2]), int(match[3])):
                raise ValueError("archive ID does not match its first line range")
            parts = []
            for segment in segments:
                name = segment.get("file", "")
                start, end = segment.get("line_start"), segment.get("line_end")
                if not re.fullmatch(r"chronicle_part_\d{3}\.txt", name) or not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end:
                    raise ValueError("invalid archive line range")
                path = (documents / name).resolve()
                if not path.is_relative_to(documents.resolve()):
                    raise ValueError("archive source resolves outside documents")
                lines = path.read_text(encoding="utf-8").splitlines()
                if end > len(lines):
                    raise ValueError("archive range exceeds source file")
                parts.append("\n".join(lines[start-1:end]))
            text = "\n".join(parts).strip()
            if text != str(source.get("text_raw", "")).strip():
                raise ValueError("archive excerpt differs from primary source lines")
            url = source_url(ref)
        elif group_match and source.get("source_kind") == "group":
            domain = group_match[1]
            if domain in EXCLUDED or source.get("group_domain") != domain:
                raise ValueError("excluded or mismatched group metadata")
            path = (groups / f"groups_{domain}.json").resolve()
            if not path.is_relative_to(groups.resolve()):
                raise ValueError("group source resolves outside groups")
            metadata = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(metadata, ensure_ascii=False, indent=2)
            if text != source.get("text_raw"):
                raise ValueError("metadata text differs from primary JSON")
            url = f"https://vk.com/{domain}"
        else:
            raise ValueError("invalid typed source ID or source kind")
        if not text or len(text) > 100000:
            raise ValueError("source excerpt is empty or too large")
        if source.get("post_url") != url:
            raise ValueError("typed source URL is not canonical")
        records[ref] = {"url":url,"text":text,"title":source.get("source_title") or "Архивная публикация", "group_name":source.get("group_name") or domain or "", "published_at":source.get("published_at") or "", "source_segments":source.get("source_segments",[])}
    wiki.mkdir(parents=True, exist_ok=True)
    target=wiki/"_source_records.json"; temporary=target.with_suffix('.json.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(records,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    temporary.replace(target)
    return len(sources)


def source_text(ref: str, wiki: Path) -> str | None:
    if not (ARCHIVE_ID.fullmatch(ref) or CURATOR_ID.fullmatch(ref)):
        return None
    record = read_records(wiki).get(ref)
    if not record:
        return None
    label = "Дата уточнения: " if CURATOR_ID.fullmatch(ref) else "Дата публикации в архиве: "
    header = [str(record.get("title") or "Архивная публикация"), str(record.get("group_name") or ""), label + str(record.get("published_at") or "не указана")]
    ranges = [f"{s['file']}#L{s['line_start']}-L{s['line_end']}" for s in record.get('source_segments',[])]
    return "\n".join(header + ranges) + "\n\n" + record['text']
