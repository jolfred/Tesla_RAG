"""Шим обратной совместимости (Milestone A).

Каноническая онтология живёт в backend/common/ontology.py.
Этот модуль только реэкспортирует имена, чтобы не трогать writer,
transformer, indexer и тесты в рамках Milestone A.
Новых импортов отсюда не добавлять — импортируйте из backend.common.ontology.
"""

from backend.common.ontology import (
    ALLOWED_NODES,
    ALLOWED_REL_TYPES,
    ALLOWED_RELATIONSHIPS,
    NODE_PROPERTIES,
    ORG_TYPES,
    RELATIONSHIP_PROPERTIES,
    SOURCE_MODEL_V2,
    STOP_NODES,
    PROMPT_VERSION,
    validate_triple,
)

# Исторические имена из первой версии модуля.
ALLOWED_NODE_TYPES = ALLOWED_NODES
ALLOWED_TRIPLES = ALLOWED_RELATIONSHIPS

__all__ = [
    "ALLOWED_NODES",
    "ALLOWED_NODE_TYPES",
    "ALLOWED_REL_TYPES",
    "ALLOWED_RELATIONSHIPS",
    "ALLOWED_TRIPLES",
    "NODE_PROPERTIES",
    "ORG_TYPES",
    "RELATIONSHIP_PROPERTIES",
    "SOURCE_MODEL_V2",
    "STOP_NODES",
    "PROMPT_VERSION",
    "validate_triple",
]
