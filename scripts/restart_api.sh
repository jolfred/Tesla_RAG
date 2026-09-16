#!/bin/bash
# Рестарт API без pkill-лотереи (pkill -f убивает собственный шелл,
# т.к. паттерн есть в его командной строке). PID — через pgrep из файла
# скрипта: в cmdline запуска скрипта паттерна нет, сам себе не страшен.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${PIDFILE:-/tmp/tesla_api.pid}"

if [ -f "$PIDFILE" ]; then
    OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
        kill "$OLD"
        sleep 3
    fi
fi

cd "$ROOT"
setsid nohup .venv/bin/python -m uvicorn backend.main:app \
    --host 0.0.0.0 --port 8000 \
    > storage/logs/api.log 2>&1 < /dev/null &
echo $! > "$PIDFILE"

sleep 10
STATUS="$(curl -s http://localhost:8000/api/v1/status --max-time 10)"
echo "$STATUS" | head -c 150
echo
if ! echo "$STATUS" | grep -q '"status":"ok"'; then
    echo "API не поднялся (порт занят старым процессом?)" >&2
    exit 1
fi
if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "PID из $PIDFILE мёртв" >&2
    exit 1
fi
