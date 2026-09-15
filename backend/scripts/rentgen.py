"""Мгновенный разбор трейса (Фаза 3 плана наблюдаемости).

Тот же формат, что раньше копировали из «Рентгена» в чат вручную, —
теперь одной командой из стора, без копипаста:
    .venv/bin/python -m backend.scripts.rentgen --last
    .venv/bin/python -m backend.scripts.rentgen --trace-id <id>
"""

from __future__ import annotations

import argparse
import json

from backend.observability.store import TraceStore

_CAP = 3000


def _short(text: str | None) -> str:
    text = text or ""
    if len(text) > _CAP:
        return text[:_CAP] + f"\n…[{len(text) - _CAP} символов скрыто]"
    return text


def _flag(v) -> str:
    return "—" if v is None else str(bool(v))


def show(trace: dict) -> str:
    lines = [
        f"Вопрос: {trace.get('question')}",
        f"trace_id={trace.get('trace_id')} ts={trace.get('ts')} "
        f"source={trace.get('source')}",
        f"План: intent={trace.get('intent')} mode={trace.get('mode')} "
        f"kind={trace.get('kind')} org={trace.get('org_norm_id') or '-'} "
        f"(сырой: {trace.get('org_filter_raw') or '-'})",
        f"Факты: {trace.get('n_facts')} | vector_fallback={bool(trace.get('used_vector_fallback'))} "
        f"| вызовы LLM: {trace.get('total_llm_calls')} | "
        f"токены: {trace.get('total_tokens') or '?'} | "
        f"latency: {trace.get('latency_ms')}мс",
        f"Версии: ответ {trace.get('prompt_version') or '?'} / "
        f"экстрактор {trace.get('extractor_prompt_version') or '?'}",
        f"Флаги Слоя 1: groundedness_ok={_flag(trace.get('groundedness_ok'))} "
        f"hierarchy_claim={_flag(trace.get('hierarchy_claim_flag'))} "
        f"empty_but_confident={_flag(trace.get('empty_but_confident_flag'))}",
        "",
        "--- ОТВЕТ ---",
        _short(trace.get("final_answer")),
    ]
    for i, sp in enumerate(trace.get("spans") or [], 1):
        lines += [
            "",
            f"--- СПАН {i}: {sp.get('name')} ({sp.get('latency_ms')}мс"
            + (f", модель {sp.get('model')}" if sp.get("model") else "")
            + (f", токены {sp.get('tokens_in')}/{sp.get('tokens_out')}"
               if sp.get("tokens_in") is not None or sp.get("tokens_out") is not None else "")
            + ") ---",
            f"ВХОД: {_short(_pretty(sp.get('input_json')))}",
            f"ВЫХОД: {_short(_pretty(sp.get('output_json')))}",
        ]
    return "\n".join(lines)


def _pretty(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        return raw


def main() -> None:
    ap = argparse.ArgumentParser(description="Разбор трейса из стора")
    ap.add_argument("--trace-id", default=None)
    ap.add_argument("--last", action="store_true")
    ap.add_argument("--source", default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    store = TraceStore(args.db)
    tid = args.trace_id or (store.last_trace_id(args.source) if args.last else None)
    if not tid:
        print("Укажите --trace-id или --last")
        return
    trace = store.fetch_trace(tid)
    store.close()
    if not trace:
        print(f"Трейс {tid} не найден")
        return
    print(show(trace))


if __name__ == "__main__":
    main()
