"""Count user-authored audit ratings, without making semantic judgments."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("materials", "evaluations", "external-access", "decisions", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    base = Path(__file__).resolve().parent
    if out.exists() or not out.is_relative_to(base / "results"):
        raise SystemExit("Choose a new output directory under experiments/wiki-source-audit/results/.")
    materials = args.materials.resolve()
    checks = json.loads((materials / "checksums.json").read_text(encoding="utf-8"))
    for rel, expected in checks.items():
        p = (materials / rel).resolve()
        if not p.is_relative_to(materials) or sha(p) != expected:
            raise SystemExit("Material checksum mismatch: " + rel)
    candidates = json.loads((materials / "candidates.json").read_text(encoding="utf-8"))
    primary = {x["id"]: x for x in candidates if x["sample"] == "primary"}
    with args.evaluations.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        all_rows = list(reader)
    rows = [r for r in all_rows if r["Выборка"] == "primary"]
    if len(rows) != 15 or len(primary) != 15 or {r["ID"] for r in rows} != set(primary):
        raise SystemExit("Exactly the 15 approved primary statements are required.")
    for row in rows:
        if row["Утверждение"] != primary[row["ID"]]["claim"]:
            raise SystemExit("Frozen statement changed: " + row["ID"])
        if row["Подтверждение"] not in {"Supported", "Contradicted", "Unverifiable"}:
            raise SystemExit("Missing/invalid manual semantic rating: " + row["ID"])
        if row["Дата"] not in {"Correct", "Incorrect", "Unclear", "Not applicable"}:
            raise SystemExit("Missing/invalid manual temporal rating: " + row["ID"])
        if row["Утвердил"] != "Альфред" or not row["Дата_решения"]:
            raise SystemExit("Missing reviewer/date: " + row["ID"])
    semantic = Counter(r["Подтверждение"] for r in rows)
    temporal = Counter(r["Дата"] for r in rows)
    applicable = len(rows) - temporal["Not applicable"]
    archive_count = sum(bool(x["sources"]) and all(s["archive_found"] for s in x["sources"]) for x in primary.values())
    urls = {s["cited_url"] for x in primary.values() for s in x["sources"]}
    external = json.loads(args.external_access.read_text(encoding="utf-8"))
    attempts = {a["cited_url"]: a for a in external["attempts"]}
    if set(attempts) != urls or any(a["outcome"] != "not_resolved_from_this_environment" for a in attempts.values()):
        raise SystemExit("This report template requires the recorded unresolved external-access outcomes for every cited URL.")
    manifest = json.loads((materials / "manifest.json").read_text(encoding="utf-8"))
    result = {
        "n": len(rows), "reviewer": "Альфред", "semantic_judge_model": None,
        "supported": semantic["Supported"], "supported_fraction": semantic["Supported"] / len(rows),
        "contradicted": semantic["Contradicted"], "unverifiable": semantic["Unverifiable"],
        "temporal_correct": temporal["Correct"], "temporal_incorrect": temporal["Incorrect"],
        "temporal_unclear": temporal["Unclear"], "temporal_not_applicable": temporal["Not applicable"],
        "temporal_applicable": applicable,
        "temporal_correct_fraction": temporal["Correct"] / applicable if applicable else None,
        "claims_with_all_cited_archives": archive_count, "archive_fraction": archive_count / len(rows),
        "unique_cited_urls": len(urls), "external_urls_attempted": len(attempts),
        "external_availability_fraction": None, "external_availability": "unknown due to retrieval errors",
        "completeness_measured": False, "representative_of_entire_wiki": False,
        "source_snapshot_sha256": manifest["wiki_snapshot_sha256"],
    }
    out.mkdir(parents=True)
    dump(out / "metrics.json", result)
    with (out / "evaluations.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    table = ["# Ручные оценки утверждений", "", "Все смысловые оценки выставлены Альфредом. "
        "Утверждения показаны с контекстом статьи; читательское изложение №14 сокращено по его замечанию. "
        "Дословные неизменные строки и история решений сохранены в CSV и исходном пакете.", "",
        "| ID | Категория | Статья и утверждение | Источник | Подтверждение | Время | Комментарий |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in sorted(rows, key=lambda r: r["ID"]):
        c = primary[row["ID"]]
        claim = row["Утверждение"]
        if row["ID"] == "14":
            claim = "День рождения — 7 октября; на 07.10.2023 — боец и один из руководителей пресс-службы «Сириуса»."
        links = "<br>".join(f"[источник {i+1}]({s['cited_url']})" for i, s in enumerate(c["sources"]))
        esc = lambda text: text.replace("|", "\\|").replace("\n", "<br>")
        cells = [row["ID"], row["Категория"], esc(c["title"] + ": " + claim), links,
                 row["Подтверждение"], row["Дата"], esc(row["Комментарий"])]
        table.append("| " + " | ".join(cells) + " |")
    (out / "evaluations.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    summary = ["# Итоги ручного аудита источников и временного контекста", "",
        f"Снимок Wiki: {manifest['started_at_utc']}; SHA-256 `{manifest['wiki_snapshot_sha256']}`. "
        f"Код подготовки: `{manifest['commit']}`; контент Wiki определяют отдельные хэши, поскольку он не хранится в Git.", "",
        "Выборка: 15 утверждений из 15 разных статей, по пять в каждой категории. Резерв не использован. "
        "Окончательные смысловые оценки выставил Альфред в переписке; Codex оформил материалы и выполнил арифметику. "
        "Отдельного LLM-судьи и экспериментальной генерации статей не было.", "",
        "## Результаты", "", "| Показатель | Абсолютное значение | Доля |", "| --- | ---: | ---: |",
        f"| Supported | {result['supported']}/15 | {result['supported_fraction']:.1%} |",
        f"| Contradicted | {result['contradicted']}/15 | {result['contradicted']/15:.1%} |",
        f"| Unverifiable | {result['unverifiable']}/15 | {result['unverifiable']/15:.1%} |",
        f"| Correct среди применимых временных оценок | {result['temporal_correct']}/{applicable} | {result['temporal_correct_fraction']:.1%} |" if applicable else "| Correct среди применимых | 0/0 | N/A |",
        f"| Incorrect | {result['temporal_incorrect']} | — |",
        f"| Unclear | {result['temporal_unclear']} | — |",
        f"| Not applicable | {result['temporal_not_applicable']} | — |",
        f"| Все указанные источники доступны в архиве | {archive_count}/15 | {result['archive_fraction']:.1%} |",
        f"| Доступность внешних оригиналов | Не установлена; попытки открыть {len(urls)} URL завершились ошибкой инструмента | Не вычисляется |", "",
        "Ошибки получения внешних страниц не доказывают, что публикации удалены или недоступны человеку. "
        "Доступность сохранённой копии и доступность оригинала не объединяются в одну метрику. "
        "Применимость временной проверки берётся из ручных оценок: знаменатель включает Correct, Incorrect и Unclear; исключает Not applicable.", "",
        "## Итоговая таблица", "", "В таблице указаны темы, а не переформулированные цитаты. "
        "Полные исходные утверждения, ссылки и основания сохранены в evaluations.csv и неизменном пакете подготовки.", "",
        "| ID | Статья | Достоверность | Время |", "| --- | --- | --- | --- |"]
    for row in sorted(rows, key=lambda r: r["ID"]):
        c = primary[row["ID"]]
        summary.append(f"| {row['ID']} | {c['title']} (`{c['article']}`) | {row['Подтверждение']} | {row['Дата']} |")
    summary += ["", "## Случаи и редакторские замечания", "",
        "- №03: в Wiki задан полный период комиссарства 05.12.2019–23.12.2020, а выбранный источник сообщает об избрании. "
        "Альфред заметил отсутствие подтверждения окончания и пересмотрел первоначальное одобрение на Unverifiable / Unclear. "
        "Это не доказывает ошибочность даты окончания. Первоначальные и пересмотренные оценки сохранены.",
        "- №08: выбранная строка относится к двум получателям писем ТРО. Трое получателей писем КГЭУ перечислены в предыдущей строке статьи. "
        "Уточнение названия «ТеслаФест» записано как редакторское замечание; исходная строка не заменялась.",
        "- №14: предпочтение Альфреда по сокращению формулировки дня рождения сохранено отдельно. "
        "Дословная цитата исследовательского снимка остаётся в CSV; новая редакция рабочей статьи в этом исследовании не создавалась.", "",
        "## Ограничения", "",
        "- 15 утверждений — ограниченная выборка, не репрезентативная оценка всей Wiki. "
        "Отбор детерминированный по SHA-256 внутри заранее заданной рамки: персональные таблицы для должностей, первые фрагменты прозы для остальных категорий. "
        "В рамке допускались утверждения без источника; в выбранных 15 все содержат ссылки.",
        "- Единственный рецензент — пользователь, связанный с предметной областью. Независимого второго оценщика, слепой проверки и межэкспертного согласия нет. "
        "Представление материала и вопросы составлял Codex; возможное влияние формулировок на ручные оценки не измерено.",
        "- Некоторые единицы содержат несколько связанных сведений. Они оценены целиком, число отдельных атомарных фактов не равно 15.",
        "- Доступность внешних оригиналов не установлена. Семантическая проверка проводилась по сохранённым текстам и контексту Wiki.",
        "- Полнота переноса всех сведений из публикаций в Wiki, полнота связей и качество генерации не измерялись. "
        "Проценты подтверждения нельзя интерпретировать как полноту Wiki или качество модели.",
        "- Рабочая Wiki и SQLite-реестр не редактировались; компиляция не запускалась. Исходники, пользовательские решения и версии оценок сохранены.", ""]
    (out / "RESULTS.md").write_text("\n".join(summary), encoding="utf-8")
    shutil.copyfile(args.evaluations, out / "evaluations-with-reserves.csv")
    shutil.copyfile(args.external_access, out / "external-access.json")
    dump(out / "calculation-manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": sha(Path(__file__)),
        "evaluations_sha256": sha(args.evaluations), "materials_checksums_sha256": sha(materials / "checksums.json"),
        "external_access_sha256": sha(args.external_access),
        "decision_record_hashes": {p.name: sha(p) for p in sorted(args.decisions.glob("*.json"))},
        "counts_derived_from_user_ratings_only": True,
    })
    dump(out / "checksums.json", {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
