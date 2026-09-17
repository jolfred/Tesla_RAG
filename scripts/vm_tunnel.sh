#!/bin/bash
# Reverse-туннель API на ВМ Кирилла (фронт-only схема).
# ВМ не видит этот сервер напрямую, поэтому пробрасываем API отсюда:
#   127.0.0.1:8000 на ВМ -> 127.0.0.1:8000 здесь.
# nginx на ВМ ходит в /api/ через этот туннель (127.0.0.1:8000, только loopback).
#
# Запуск (без setsid процесс умирает вместе с терминалом!):
#   setsid nohup bash scripts/vm_tunnel.sh > storage/logs/vm_tunnel.log 2>&1 < /dev/null & disown
# Проверка: ssh на ВМ + curl http://127.0.0.1:8000/api/v1/status
set -u
KEY="$HOME/.ssh/vm_jolfred"
while true; do
    ssh -i "$KEY" -o BatchMode=yes -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
        -N -R 127.0.0.1:8000:127.0.0.1:8000 jolfred@192.168.10.160
    echo "$(date -u +%FT%TZ) tunnel exited, reconnect in 5s"
    sleep 5
done
