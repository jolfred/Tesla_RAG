"""Фильтр известного безвредного уведомления Neo4j (event_date на старых рёбрах)."""

import logging

from backend.graph.graph_builder import _EventDateNoticeFilter


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("neo4j", logging.WARNING, __file__, 1, msg,
                             (), None)


def test_event_date_notice_filtered():
    f = _EventDateNoticeFilter()
    assert f.filter(_record(
        "Received notification from DBMS server: warn: property key does "
        "not exist. The property `event_date` does not exist.")) is False


def test_other_notices_pass():
    f = _EventDateNoticeFilter()
    assert f.filter(_record("Received notification: something else")) is True
