"""Сводка наблюдаемости (Фаза 6): метрики без ручного разбора логов.
    .venv/bin/python -m backend.scripts.observability_report --since 7d
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.observability.store import TraceStore

LOGS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "logs"
)


def _parse_since(raw: str) -> str:
    m = re.fullmatch(r"(\d+)([dh])", raw or "7d")
    if not m:
        raise ValueError(f"bad --since {raw!r}, пример: 7d, 24h")
    n, unit = int(m.group(1)), m.group(2)
    dt = datetime.now(timezone.utc) - timedelta(
        days=n if unit == "d" else 0, hours=n if unit == "h" else 0)
    return dt.isoformat(timespec="seconds")


def _one(conn, sql: str, args: tuple = ()):
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def report(store: TraceStore, since: str, source: str) -> str:
    conn = store._conn
    if conn is None:
        return "Стор недоступен"
    W = "WHERE ts >= ? AND source = ?"
    A = (since, source)
    n = _one(conn, f"SELECT COUNT(*) FROM traces {W}", A) or 0
    lines = [f"Трейсы ({source}, с {since}): {n}"]
    if not n:
        return "\n".join(lines)
    avg_calls = _one(conn, f"SELECT AVG(total_llm_calls) FROM traces {W}", A)
    avg_lat = _one(conn, f"SELECT AVG(latency_ms) FROM traces {W}", A)
    tokens = _one(conn, f"SELECT SUM(total_tokens) FROM traces {W}", A)
    lines.append(f"LLM-вызовов на вопрос (среднее): {avg_calls:.2f}"
                 if avg_calls else "LLM-вызовов на вопрос: —")
    lines.append(f"Latency средняя: {avg_lat:.0f}мс" if avg_lat else "Latency: —")
    lines.append(f"Токены всего (оценка): {tokens or '—'} "
                 "(cost: NULL — тарифы не заданы)")
    lines.append("По интентам:")
    try:
        for intent, c, avg in conn.execute(
                f"SELECT intent, COUNT(*), AVG(total_llm_calls) FROM traces {W} "
                f"GROUP BY intent ORDER BY COUNT(*) DESC", A):
            lines.append(f"  {intent or '?'}: {c} (вызовов {avg or 0:.1f})")
    except Exception:
        pass
    def _rate(cond: str) -> str:
        v = _one(conn, f"SELECT AVG(CASE WHEN {cond} THEN 1.0 ELSE 0.0 END) "
                       f"FROM traces {W}", A)
        return f"{v * 100:.0f}%" if v is not None else "—"
    lines.append(f"Zero-result (тишина): {_rate('final_answer LIKE \"%архивах нет данных%\"')}")
    lines.append("Unresolved-org (struct без org_norm_id): "
                 + _rate("mode = 'struct' AND org_norm_id IS NULL"))
    lines.append(f"Флаги Слоя 1: groundedness_fail={_rate('groundedness_ok = 0')}, "
                 f"hierarchy={_rate('hierarchy_claim_flag = 1')}, "
                 f"empty_but_confident={_rate('empty_but_confident_flag = 1')}")
    lines.append("По версиям промпта ответа:")
    try:
        for pv, c, avg in conn.execute(
                f"SELECT prompt_version, COUNT(*), AVG(total_llm_calls) "
                f"FROM traces {W} GROUP BY prompt_version", A):
            lines.append(f"  {pv or '?'}: {c} (вызовов {avg or 0:.1f})")
    except Exception:
        pass
    lines.append("Регресс-тренд:")
    for path in sorted(glob.glob(str(LOGS_DIR / "regression_*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            ok = sum(1 for r in data if r.get("ok"))
            lines.append(f"  {Path(path).name}: {ok}/{len(data)}")
        except (ValueError, OSError):
            continue
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Сводка наблюдаемости")
    ap.add_argument("--since", default="7d")
    ap.add_argument("--source", default="prod")
    ap.add_argument("--db", default=None)
    ap.add_argument("--check-alerts", action="store_true",
                    help="Фаза 7: пороги, exit 2 при превышении (канал — снаружи)")
    args = ap.parse_args()
    store = TraceStore(args.db)
    try:
        text = report(store, _parse_since(args.since), args.source)
        print(text)
        if not args.check_alerts:
            return
        alerts = [
            line for line in text.splitlines()
            if re.search(r"(100|[3-9]\d)%", line) and
            any(k in line for k in ("Zero-result", "Unresolved-org",
                                    "hierarchy=", "empty_but_confident="))
        ]
        regs = [line for line in text.splitlines()
                if re.match(r"  regression_.*: [0-4]/\d+", line)]
        alerts += [f"ALERT регресс: {line.strip()}" for line in regs]
        if alerts:
            print("\n".join("ALERT " + a for a in alerts))
            raise SystemExit(2)
    finally:
        store.close()


if __name__ == "__main__":
    main()
