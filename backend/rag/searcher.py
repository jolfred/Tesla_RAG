"""Compatibility import for callers migrated to the Wiki service.

Historical graph/vector implementations are available in Git history.
"""
from backend.wiki.service import WikiAnswerService


class GraphRAGSearcher(WikiAnswerService):
    def search(self, question: str, top_k: int = 8, include_context: bool = False,
               project_slug: str | None = None) -> dict:
        return super().search(question, include_context=include_context, project_slug=project_slug)
