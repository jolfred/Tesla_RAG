"""The public and admin chat use Wiki exclusively."""
from __future__ import annotations
import json

from backend.wiki.loop import SILENCE, WikiUnavailable, try_wiki_answer
from backend.observability import langfuse_client as lf


class WikiProjectUnavailable(ValueError):
    pass


class WikiAnswerService:
    def search(self, question: str, include_context: bool = False, project_slug: str | None = None) -> dict:
        if project_slug:
            raise WikiProjectUnavailable("Этот проект ещё не подключён к Летописи.")
        with lf.observation("wiki_answer", input=question) as trace:
            try:
                result = try_wiki_answer(question, raise_on_error=True)
                result = result or {"answer": SILENCE, "pages": [], "sources": []}
                trace.update(output=result["answer"], metadata={"mode": "wiki", "pages": result.get("pages", [])})
                return {
                    **result, "mode": "wiki", "facts_count": len(result.get("pages", [])),
                    "posts_used": len(result.get("sources", [])), "media": [], "previews": [],
                    "calls": [{"title": c["name"], "text": json.dumps({"arguments": c["arguments"], "result": c["result"]}, ensure_ascii=False, indent=2)} for c in result.get("calls", [])] if include_context else None,
                    "context": {"wiki_pages": result.get("pages", [])} if include_context else None,
                    "trace_id": lf.current_trace_id(),
                }
            finally:
                lf.flush()
