"""Export approval materials without any model calls or production mutations."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import shutil
import tarfile


CASES = [
    ("C01", "events/pogruzhenie", "Школа «Погружение»", True,
     "Многолетнее мероприятие: сохранение истории при нескольких сообщениях об одном выпуске.",
     "В поздней версии повторяются заголовки годов. Архивный исходник также требует проверки дат; его качество не считается доказанным.",
     [["wall-237134130_57", "wall-237134130_84"], ["wall-237134130_242", "wall-237134130_261"], ["wall-91740386_9972", "wall-198864697_5354"]],
     ["Подготовка школы и кураторы: различить анонс и проведение.", "Спикеры и объявленные результаты: проверить статус сообщений и принадлежность наград.", "Итоговые сообщения: объединить подтверждения без второго раздела о том же выпуске."]),
    ("C02", "lso/spo_delta", "СПО «Дельта»", True,
     "История отряда с составом, личными достижениями, выездами и несколькими годами истории.",
     "Архивная вводная содержит разные даты в поле основания и ссылке на событие. Это исходное расхождение, которое необходимо разобрать до эталонной разметки.",
     [["wall-117349582_7440", "wall-117349582_7460"], ["wall-117349582_7464", "wall-117349582_7479"], ["wall-117349582_7480", "wall-117349582_7483"]],
     ["Танцевальный конкурс и анонс выезда: различить личное участие, финал и победу.", "Отправление в лагерь и открытие пространства: не превращать отправление в доказательство завершённой целины.", "Открытие трудового семестра и выступление бывшего командира: сохранить уровень организации и атрибуцию."]),
    ("C03", "lso/index", "Реестр отрядов", True,
     "Реестр с большим количеством внутренних ссылок: краткие сведения, переименование и границы подробностей.",
     "В архивной версии общий абзац называет производственный отряд «Тесла», а ссылка — «Элемент». Пост от 13.05.2026 сообщает о смене названия на «Элемент»; точную дату вступления названия в силу предстоит оценить отдельно.",
     [["wall-91744408_1115", "wall-168038239_204"], ["wall-168038239_401", "wall-226472080_724"], ["wall-226472080_1074", "wall-226472080_1092"]],
     ["Юбилей Energy и годовщина «Заряда»: проверить основания дат, сохранить ссылки на существующие команды.", "Повторная годовщина «Заряда» и набор в СПрО «Тесла»: отделить подтверждение от нового факта.", "Сообщение о переименовании в «Элемент» и отбор на КАМАЗ: не создавать второй отряд, определить уместный объём сведений в реестре."]),
    ("C04", "persons/sharifullin_alfred", "Альфред Шарифуллин", True,
     "Короткая статья человека: роли в ЛСО, снежном десанте и Штабе, смена полномочий.",
     "Архив содержит разные уровни ролей и отдельные упоминания, которые нельзя автоматически превращать в непрерывные сроки. Проверка человека проводится по VK ID и тексту, не по одной фамилии.",
     [["wall-91740386_8248", "wall-91740386_8784"], ["wall-198864697_4014", "wall-207526383_874"], ["wall-207526383_907", "wall-237134130_217"]],
     ["Выборы комиссара и участие в защите конкурса: проверить точную роль и дату.", "Закрытие снежного десанта и позднее упоминание командира: проверить персональную награду и наблюдение должности.", "Передача руководства «Сириуса» и выступление на школе: не угадывать точный день по словам «на прошлой неделе»."]),
    ("C05", "hq/index", "Штаб «Тесла»", True,
     "Общая статья организации: сохранить основные сведения и включить новые виды деятельности без свалки подробностей.",
     "Позднее существовали несколько страниц Штаба. Сейчас hq/index перенаправляет на hq/tesla; ручной образец не объявляется утверждённым эталоном. Архивные награды требуют проверки получателя и даты.",
     [["wall-91740386_9556", "wall-91740386_9638"], ["wall-91740386_9993", "wall-91740386_10000"], ["wall-91740386_10007", "wall-91740386_10046"]],
     ["Анонс и отчёт о фестивале: объединить сообщения, различить даты публикации и события.", "Экологический квиз и отбор сервисных отрядов: не превращать отбор в отчёт о работе.", "Совместный субботник и гранты участников: сохранить различие организации и личных проектов."]),
    ("C06", "lso/spo_yunost", "СПО «Юность»", False,
     "Длинная статья как дополнительная проверка сохранности большого объёма знаний.",
     "Длинные таблицы и исходные объединённые наименования мастера и методиста требуют проверки по источникам. Длина контекста заметно отличается от остальных случаев.",
     [["wall-198864697_5085"], ["wall-198864697_5155"], ["wall-198864697_5271"]],
     ["Представление комиссара.", "Представление мастера-методиста: сохранить буквальное наименование источника без обобщения на остальные годы.", "Представление пресс-секретаря: частичное обновление не означает увольнение остальных."]),
    ("C07", "events/tesla_leader", "Школа «ТеслаЛидер»", False,
     "Ещё одно повторяющееся мероприятие для проверки переноса правил объединения выпусков.",
     "В текущем материале есть повторные и неупорядоченные годовые разделы. Совпадение названия не означает один и тот же выпуск.",
     [["wall-91740386_9586"], ["wall-218400774_1163"], ["wall-117349582_7282"]],
     ["Анонс осеннего выпуска.", "Отчёт о ноябрьской школе.", "Отчёт о весеннем выпуске следующего года."]),
    ("C08", "persons/astafiev_daniil", "Даниил Астафьев", False,
     "Дополнительная карточка человека с переходом между уровнями руководства.",
     "Архивная статья использует объединённые роли мастера-методиста; каждое наименование необходимо проверить отдельно. Позднее упоминание должности не доказывает весь промежуток.",
     [["wall-91740386_9439"], ["wall-91740386_9748"], ["wall-237134130_242"]],
     ["Контактное лицо набора на обучение.", "Новое объявление обучения и подтверждение должности на дату публикации.", "Сообщение о выступлении на школе: проверить анонс или репортаж."]),
    ("C09", "lso/osd_sirius", "ОСД «Сириус»", False,
     "Смена командного состава и отдельные уровни членства в снежном десанте.",
     "Архивная статья содержит старые спорные сопоставления людей. Их нельзя включать в защищаемый эталон без проверки. Одни и те же источники пересекаются с карточкой Альфреда.",
     [["wall-207526383_626"], ["wall-207526383_907"], ["wall-207526383_922"]],
     ["Упоминание командира на дату поздравления.", "Перевыборы и сдача отчётов.", "Участие комиссара и бойца в слёте: не расширять список участников без источника."]),
    ("C10", "lso/spro_element", "Производственный отряд «Элемент» / «Тесла»", False,
     "Короткая предметная статья о переименовании одной команды.",
     "Необходима проверка исторического и действующего названий по одному group_id. Нельзя считать дату публикации автоматически точным днём переименования. Источники пересекаются с реестром.",
     [["wall-226472080_724"], ["wall-226472080_1074"], ["wall-226472080_1092"]],
     ["Набор под названием «Тесла».", "Явное сообщение об официальном названии «Элемент».", "Объявление результатов отбора на КАМАЗ: отделить от факта прохождения работы."]),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.snapshot_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Output exists; choose a new path to preserve earlier materials.")
    if output == root or output.is_relative_to(root / "storage/wiki"):
        raise SystemExit("Output must not overwrite the source Wiki.")
    excluded = {"posts_kgeu_official.jsonl", "posts_spoyunost.jsonl"}
    wanted = {pid for case in CASES for batch in case[6] for pid in batch}
    found: dict[str, list[dict]] = {}
    read_files = []
    for path in sorted((root / "storage/posts").glob("*.jsonl")):
        if path.name in excluded:
            continue
        read_files.append(path.relative_to(root).as_posix())
        with path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                item = json.loads(line)
                match = re.search(r"wall-?\d+_\d+", str(item.get("post_url", "")))
                if not match or match[0] not in wanted:
                    continue
                body = str(item.get("text_raw") if "text_raw" in item else item.get("text_clean") or "")
                record = {"canonical_id": match[0], "body": body, "body_sha256": sha(body.encode()),
                          "source_file": path.relative_to(root).as_posix(), "source_line": line_no, "raw": item}
                versions = found.setdefault(match[0], [])
                if all(v["body_sha256"] != record["body_sha256"] for v in versions):
                    versions.append(record)
    missing = wanted - found.keys()
    if missing:
        raise SystemExit("Missing source IDs: " + ", ".join(sorted(missing)))
    output.mkdir(parents=True)
    implementation = ["backend/wiki/ingest.py", "backend/wiki/ingest_runner.py",
                      "backend/wiki/editorial_store.py", "schema/rules.md", "schema/rules_mapping.md",
                      "schema/prompts/wiki_merge_en.md", "schema/prompts/wiki_extract_en.md"]
    implementation_hashes = {}
    for filename in implementation:
        target = output / "implementation" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / filename, target)
        implementation_hashes[filename] = sha(target.read_bytes())
    migration = root / "MIGRATION/transfer-manifest.json"
    snapshot_commit = json.loads(migration.read_text(encoding="utf-8")).get("git_commit") if migration.exists() else None
    archive_path = root / "storage/backups/wiki-before-compile-2026-10-05.tar.gz"
    freeze_path = root / "storage/backups/wiki-editorial-freeze-20261014T220417/public-articles.tar.gz"
    summary = []
    rows = ["# Материалы для согласования № 1", "", "Статус: ожидается решение Альфреда. Ни один случай и ни один эталон ещё не утверждены. Эксперимент и LLM-вызовы не выполнялись.", "",
            "Первые пять случаев рекомендуются для полной выборки. Для срочного пилота предлагаются C01, C03, C04 и первые две партии каждого: это отдельный вариант, который тоже требует утверждения.", "",
            "Публикации новые относительно библиографии/содержания выбранного архивного исходника, а не обязательно позднее времени сохранения файла. Это ретроспективное дополнение пропусков, не чистое прогнозирование будущих событий. Отсутствие wall-ID в тексте не доказывает новизну факта; она устанавливается отдельно на этапе № 2.", "",
            "| Случай | Статья | Исходная версия | Партии публикаций | Почему выбрана |", "|---|---|---|---|---|"]
    with tarfile.open(archive_path) as old, tarfile.open(freeze_path) as freeze:
        for code, slug, title, recommended, why, problems, batches, expectations in CASES:
            folder = output / code
            folder.mkdir()
            member = old.getmember("wiki/" + slug + ".md")
            baseline = old.extractfile(member).read()
            (folder / "baseline-candidate.md").write_bytes(baseline)
            old_text = baseline.decode("utf-8")
            versions = [{"file": "baseline-candidate.md", "origin": archive_path.relative_to(root).as_posix(), "member": member.name,
                         "sha256": sha(baseline), "status": "archived; not a verified gold baseline"}]
            for source_slug in dict.fromkeys([slug, "hq/tesla" if slug == "hq/index" else slug]):
                try:
                    data = freeze.extractfile(source_slug + ".md").read()
                except KeyError:
                    data = None
                safe_slug = source_slug.replace("/", "_")
                if data is not None:
                    filename = "versions/2026-10-14-" + safe_slug + ".md"
                    (folder / filename).parent.mkdir(exist_ok=True)
                    (folder / filename).write_bytes(data)
                    versions.append({"file": filename, "origin": freeze_path.relative_to(root).as_posix(), "member": source_slug + ".md", "sha256": sha(data)})
                current = root / "storage/wiki" / (source_slug + ".md")
                if current.is_file():
                    data = current.read_bytes()
                    filename = "versions/2026-10-19-" + safe_slug + ".md"
                    (folder / filename).parent.mkdir(exist_ok=True)
                    (folder / filename).write_bytes(data)
                    versions.append({"file": filename, "origin": current.relative_to(root).as_posix(), "sha256": sha(data)})
            editorial_db = root / "storage/wiki/_editorial/editorial.sqlite"
            if editorial_db.exists():
                with sqlite3.connect(editorial_db.as_uri() + "?mode=ro", uri=True) as db:
                    db.row_factory = sqlite3.Row
                    for v in db.execute("SELECT * FROM versions WHERE slug IN (?,?) ORDER BY created_at,id", (slug, "hq/tesla" if slug == "hq/index" else slug)):
                        filename = "versions/cabinet-" + v["id"] + ".md"
                        (folder / filename).parent.mkdir(exist_ok=True)
                        data = v["markdown"].encode()
                        (folder / filename).write_bytes(data)
                        versions.append({"file": filename, "origin": "editorial.sqlite/versions", "id": v["id"], "created_at": v["created_at"], "sha256": sha(data), "kind": v["kind"]})
            notes = [f"# {code}: {title}", "", f"Рабочая статья: `storage/wiki/{slug}.md`.", "", f"Почему выбрана: {why}", "", f"Исходные проблемы и ограничения: {problems}", "", "Исходник `baseline-candidate.md` приведён полностью и сохранён без исправлений. Он ещё не является утверждённым эталоном. До запуска по этапу № 2 могут потребоваться проверенная экспериментальная редакция и перечень её изменений.", "", "## Исторические версии", ""]
            notes += [f"- [{v['file']}]({v['file']}) — SHA-256 `{v['sha256']}`; {v['origin']}." for v in versions]
            case_batches = []
            previous = ""
            for number, (ids, expectation) in enumerate(zip(batches, expectations), 1):
                records = sorted([found[pid][0] for pid in ids], key=lambda p: p["raw"].get("published_at") or "")
                dates = [p["raw"].get("published_at") or "" for p in records]
                if previous and min(dates) < previous:
                    raise ValueError(f"Source batches are not chronological: {code}")
                previous = max(dates)
                party = []
                notes += ["", f"## Партия {number}", "", "Предполагаемые сведения, ещё не эталон: " + expectation, ""]
                for p in records:
                    pid, raw = p["canonical_id"], p["raw"]
                    cited = pid in old_text
                    source_file = "sources/" + pid + ".json"
                    dump(folder / source_file, p)
                    if len(found[pid]) > 1:
                        dump(folder / "sources" / (pid + "-all-versions.json"), found[pid])
                    party.append({"post_id": pid, "source_hash": p["body_sha256"], "published_at_utc": raw.get("published_at"), "url": raw.get("post_url"), "record_file": source_file, "already_cited_in_baseline": cited, "source_versions": len(found[pid])})
                    notes += [f"### {pid}", "", f"Дата публикации (UTC): {raw.get('published_at')}. Ссылка: {raw.get('post_url')}.", "", f"Экспорт: `{p['source_file']}:{p['source_line']}`; SHA-256 текста: `{p['body_sha256']}`. Упомянут в исходнике: {'да — контроль повтора' if cited else 'нет — новизна фактов ещё проверяется'}.", "", "Полный текст:", "", "```text", p["body"], "```", ""]
                case_batches.append({"batch": number, "proposed_information": expectation, "sources": party})
            meta = {"id": code, "slug": slug, "title": title, "recommended": recommended, "reason": why, "existing_problems": problems,
                    "baseline_sha256": sha(baseline), "baseline_status": "candidate; not verified", "versions": versions, "batches": case_batches, "approval": "pending"}
            dump(folder / "case.json", meta)
            notes += ["## Решение хранителя", "", "Варианты: утвердить материалы / отклонить / заменить исходник / заменить публикации. Решение пока не получено. Одобрение этого списка не заменяет отдельное утверждение эталонных фактов и методики.", ""]
            (folder / "REVIEW.md").write_text("\n".join(notes), encoding="utf-8")
            label = "основной" if recommended else "резерв"
            party_ids = "; ".join(str(b["batch"]) + ": " + ", ".join(s["post_id"] for s in b["sources"]) for b in case_batches)
            rows.append(f"| [{code} — {title}]({code}/REVIEW.md), {label} | `storage/wiki/{slug}.md` | [Архив 05.10.2026]({code}/baseline-candidate.md), {len(baseline.decode('utf-8'))} знаков | {party_ids} | {why} |")
            summary.append(meta)
    usage = Counter(s["post_id"] for c in summary for b in c["batches"] for s in b["sources"])
    rows += ["", "## Что требуется утвердить сейчас", "", "Для каждого C01–C10 можно утвердить, отклонить или заменить исходник и публикации. Предлагается полная выборка C01–C05 с тремя партиями по два поста. Резерв C06–C10 пока содержит три партии по одному посту и требует выравнивания нагрузки при включении в основную выборку.", "", "Сначала согласуются только материалы. После решения будут подготовлены и отдельно согласованы эталонные прежние/новые факты с точными фрагментами источников. Критерии сейчас — проект, результатов сравнения нет.", "", "## Ограничения отбора", "", "- Архив от 5 октября не гарантирует качества: обнаруженные старые ошибки требуют проверки до построения эталона.", "- Отсутствие идентификатора источника не означает отсутствие его факта; возможны контрольные повторы и источники без новых подходящих сведений.", "- Части случаев используют одинаковые источники. Нельзя считать их полностью независимыми наблюдениями.", "- Выборка целевая и предварительная, не случайная и не репрезентативная для всей Wiki.", "- Полные тексты и цитаты из этих материалов ещё не являются окончательной экспертной разметкой.", ""]
    (output / "REVIEW.md").write_text("\n".join(rows), encoding="utf-8")
    dump(output / "manifest.json", {"created_at": datetime.now(timezone.utc).isoformat(), "snapshot_root_at_preparation": str(root), "snapshot_commit": snapshot_commit, "implementation_hashes": implementation_hashes, "source_archive_sha256": sha(archive_path.read_bytes()), "read_source_files": read_files, "excluded_source_files": sorted(excluded), "cases": summary, "shared_sources": {k: v for k, v in usage.items() if v > 1}, "llm_calls": 0, "approval": "pending"})
    checks = {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    dump(output / "checksums.json", checks)
    print(json.dumps({"cases": len(summary), "recommended": sum(c[3] for c in CASES), "unique_posts": len(wanted), "files": len(checks), "output": str(output), "llm_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
