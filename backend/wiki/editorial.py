"""Keep internal editorial notes out of both public pages and answer context."""
from __future__ import annotations

import re

_COMMENTS = re.compile(r"<!--[\s\S]*?-->")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PRIVATE = {
    "противоречия и дискуссии",
    "дискуссии и расхождения",
    "источники данных",
    "редакторские заметки",
}


def public_markdown(text: str) -> str:
    """Preserve the source file; omit private sections including subheadings."""
    lines: list[str] = []
    hidden_level: int | None = None
    for line in _COMMENTS.sub("", text).splitlines():
        heading = _HEADING.match(line)
        if heading:
            level = len(heading[1])
            if hidden_level is not None and level <= hidden_level:
                hidden_level = None
            if hidden_level is None and heading[2].strip().casefold() in _PRIVATE:
                hidden_level = level
        if hidden_level is None:
            lines.append(line)
    return "\n".join(lines).strip() + "\n"
