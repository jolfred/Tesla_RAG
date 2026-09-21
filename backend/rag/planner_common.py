"""Общее для Cypher-шаблонов: модель графа и строители условий/параметров."""

MODEL = "llmgraph_gigachat"


def _limit(plan: dict) -> int:
    return int(plan.get("limit") or 20)


def _org_cond(alias: str = "o") -> str:
    """Условие по организации (C4, union-форма).

    Точное совпадение norm_id — первым, CONTAINS — следом. Строгая ветвь
    БЕЗ фолбэка давала тишину, когда org_exact указывал не на тот узел
    (кейс D: org_exact='тесла' = Squad СПрО, а не штаб → 0 фактов при живых
    сидовых данных). Union не молчит никогда.
    """
    return (
        f"($org IS NULL OR "
        f"($org_exact IS NOT NULL AND {alias}.norm_id = $org_exact) "
        f"OR toLower(toString({alias}.name)) CONTAINS toLower($org))"
    )


def _exact_first(alias: str = "o") -> str:
    """Точные совпадения первыми (защита от усечения LIMIT'ом)."""
    return (
        f"CASE WHEN $org_exact IS NOT NULL AND {alias}.norm_id = $org_exact "
        f"THEN 0 ELSE 1 END"
    )


def _params(plan: dict, **extra) -> dict:
    p = {
        "model": plan.get("source_model") or MODEL,
        "org": plan.get("org_filter"),
        "org_exact": plan.get("org_exact"),
        "limit": _limit(plan),
    }
    p.update(extra)
    return p


# Новые свойства рёбер v3 (пункт 6): пробрасываем в факты, чтобы отвечающий
# различал дату события и дату упоминания. У старых данных — null, это нормально.
_V3_PROPS = "r.observed_at AS observed_at, r.event_date AS event_date, r.role_status AS role_status"
_V3_LINKS = ("rel: type(r), date: r.date, observed_at: r.observed_at, "
             "event_date: r.event_date, role_status: r.role_status, "
             "source_post_url: r.source_post_url")
