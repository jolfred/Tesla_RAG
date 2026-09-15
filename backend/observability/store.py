"""SQLite-стор трейсов (Фаза 0 плана наблюдаемости).

Один файл storage/traces.db (WAL), ноль новых сервисов. Поля спанов —
по семантике OpenTelemetry gen_ai (gen_ai.request.model, gen_ai.usage.*),
чтобы будущий переезд на Langfuse/Phoenix был перекладкой, а не рерайтом.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.utils.logger import setup_logger

logger = setup_logger("trace_store")

DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "traces.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
  trace_id TEXT PRIMARY KEY,
  ts TEXT,
  question TEXT,
  intent TEXT,
  mode TEXT,
  kind TEXT,
  org_filter_raw TEXT,
  org_norm_id TEXT,
  n_facts INTEGER,
  used_vector_fallback BOOLEAN,
  final_answer TEXT,
  prompt_version TEXT,
  extractor_prompt_version TEXT,
  total_llm_calls INTEGER,
  total_tokens INTEGER,
  total_cost REAL,
  cost_currency TEXT,
  latency_ms INTEGER,
  source TEXT DEFAULT 'prod',
  groundedness_ok BOOLEAN,
  hierarchy_claim_flag BOOLEAN,
  empty_but_confident_flag BOOLEAN
);
CREATE TABLE IF NOT EXISTS spans (
  span_id TEXT PRIMARY KEY,
  trace_id TEXT REFERENCES traces(trace_id),
  name TEXT,
  input_json TEXT,
  output_json TEXT,
  latency_ms INTEGER,
  model TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER
);
CREATE TABLE IF NOT EXISTS judgements (
  trace_id TEXT REFERENCES traces(trace_id),
  judge_model TEXT,
  faithfulness_score INTEGER,
  relevance_score INTEGER,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS quality_log (
  ts TEXT,
  question TEXT,
  stage TEXT,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_ts ON traces(ts);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(obj) -> str | None:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)[:4000]


class TraceStore:
    """Тонкая обёртка над SQLite. Все записи — best-effort, трейсинг
    никогда не должен ронять ответ пользователю."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self._ok = True
        except OSError as e:
            logger.warning("TraceStore init failed: %s", e)
            self._conn = None
            self._ok = False

    def new_trace(self, question: str, source: str = "prod") -> str:
        trace_id = uuid.uuid4().hex[:16]
        if not self._ok:
            return trace_id
        try:
            self._conn.execute(
                "INSERT INTO traces (trace_id, ts, question, source) "
                "VALUES (?, ?, ?, ?)",
                (trace_id, _now(), question, source),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("new_trace failed: %s", e)
        return trace_id

    def add_span(self, trace_id: str, name: str, input_json=None,
                 output_json=None, latency_ms: int = 0,
                 model: str | None = None, tokens_in: int | None = None,
                 tokens_out: int | None = None) -> None:
        if not self._ok:
            return
        try:
            self._conn.execute(
                "INSERT INTO spans (span_id, trace_id, name, input_json, "
                "output_json, latency_ms, model, tokens_in, tokens_out) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex[:16], trace_id, name,
                 _dump(input_json), _dump(output_json), latency_ms,
                 model, tokens_in, tokens_out),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("add_span failed: %s", e)

    def finish_trace(self, trace_id: str, **fields) -> None:
        if not self._ok or not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        try:
            self._conn.execute(
                f"UPDATE traces SET {cols} WHERE trace_id = ?",
                (*fields.values(), trace_id),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("finish_trace failed: %s", e)

    def log_quality(self, question: str, stage: str, detail: str = "") -> None:
        if not self._ok:
            return
        try:
            self._conn.execute(
                "INSERT INTO quality_log (ts, question, stage, detail) "
                "VALUES (?, ?, ?, ?)",
                (_now(), question, stage, detail[:1000]),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("log_quality failed: %s", e)

    def add_judgement(self, trace_id: str, judge_model: str,
                      faithfulness: int | None, relevance: int | None,
                      notes: str = "") -> None:
        if not self._ok:
            return
        try:
            self._conn.execute(
                "INSERT INTO judgements (trace_id, judge_model, "
                "faithfulness_score, relevance_score, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (trace_id, judge_model, faithfulness, relevance,
                 notes[:2000]),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("add_judgement failed: %s", e)

    def fetch_trace(self, trace_id: str) -> dict | None:
        if not self._ok:
            return None
        try:
            cur = self._conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            trace = dict(zip(cols, row))
            cur = self._conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY rowid",
                (trace_id,),
            )
            scols = [d[0] for d in cur.description]
            trace["spans"] = [dict(zip(scols, r)) for r in cur.fetchall()]
            return trace
        except sqlite3.Error as e:
            logger.warning("fetch_trace failed: %s", e)
            return None

    def last_trace_id(self, source: str | None = None) -> str | None:
        if not self._ok:
            return None
        try:
            if source:
                cur = self._conn.execute(
                    "SELECT trace_id FROM traces WHERE source = ? "
                    "ORDER BY rowid DESC LIMIT 1", (source,))
            else:
                cur = self._conn.execute(
                    "SELECT trace_id FROM traces ORDER BY rowid DESC LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._ok = False
