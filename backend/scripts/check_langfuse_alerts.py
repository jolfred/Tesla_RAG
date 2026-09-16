"""L6: алерты поверх Langfuse API. Langfuse — не система алертинга,
поэтому пороги проверяем этим скриптом, доставка в канал — снаружи.

Проверяет:
- fail rate Score Слоя 1 (date_groundedness, hierarchy_claim_ok,
  empty_but_confident_ok) по последним до 100 скорам каждого имени;
- последний run датасета regression-golden-set (score regression_contains).

Пороги: hierarchy — любой провал; остальные Слой 1 — >=30%;
регресс — любой провал. Exit 2 при срабатывании.
"""
from __future__ import annotations

import base64
import os
import sys

import httpx

import backend.config  # noqa: F401 — грузит .env (ключи Langfuse)

LAYER1 = ["date_groundedness", "hierarchy_claim_ok",
          "empty_but_confident_ok"]
DATASET = "regression-golden-set"


def _api():
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")
    auth = base64.b64encode(
        f"{os.getenv('LANGFUSE_PUBLIC_KEY', '')}"
        f":{os.getenv('LANGFUSE_SECRET_KEY', '')}".encode()
    ).decode()
    return httpx.Client(base_url=host,
                        headers={"Authorization": f"Basic {auth}"},
                        timeout=30)


def score_fail_rate(cli: httpx.Client, name: str,
                    limit: int = 100) -> tuple[int, int]:
    fails = total = 0
    page, pages = None, 0
    while pages < 10:
        params = {"name": name, "limit": 50}
        if page:
            params["page"] = page
        r = cli.get("/api/public/scores", params=params).json()
        data = r.get("data", [])
        if not data:
            break
        for s in data:
            v = s.get("value")
            total += 1
            if v is False or v == 0:
                fails += 1
        meta = r.get("meta", {})
        page = meta.get("page", 0) + 1
        if page >= meta.get("totalPages", 1):
            break
        pages += 1
        if total >= limit:
            break
    return fails, total


def latest_regression(cli: httpx.Client) -> tuple[str, int, int]:
    runs = cli.get(f"/api/public/datasets/{DATASET}/runs",
                   params={"limit": 1}).json()
    data = runs.get("data", [])
    if not data:
        return ("none", 0, 0)
    run_name = data[0]["name"]
    run = cli.get(
        f"/api/public/datasets/{DATASET}/runs/{run_name}").json()
    tids = {i.get("traceId") for i in run.get("datasetRunItems", [])
            if i.get("traceId")}
    # Внимание: фильтр traceId API игнорирует — тянем по name и
    # джойним по traceId в питоне.
    fails = total = 0
    page = 1
    while True:
        r = cli.get("/api/public/scores",
                    params={"name": "regression_contains", "limit": 50,
                            "page": page}).json()
        batch = r.get("data", [])
        if not batch:
            break
        for s in batch:
            if s.get("traceId") not in tids:
                continue
            total += 1
            if (s.get("value") or 0) < 1.0:
                fails += 1
        meta = r.get("meta", {})
        page += 1
        if page > meta.get("totalPages", 1):
            break
    return (run_name, fails, total)


def main() -> int:
    cli = _api()
    alerts: list[str] = []
    for name in LAYER1:
        fails, total = score_fail_rate(cli, name)
        rate = (fails / total) if total else 0.0
        line = f"{name}: {fails}/{total} ({rate:.0%})"
        print(line)
        threshold = 0.0 if name == "hierarchy_claim_ok" else 0.30
        if total and rate > threshold:
            alerts.append(line)
    run_name, fails, total = latest_regression(cli)
    line = f"regression {run_name}: {fails}/{total} fails"
    print(line)
    if fails:
        alerts.append(line)
    if alerts:
        print("ALERT:")
        for a in alerts:
            print(" -", a)
        return 2
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
