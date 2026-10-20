# Проверки подготовки от 20.10.2026

Экспериментальных обращений к модели: **0**. Результатов сравнения Wiki нет.

## Пройдено

- 12 unittest: московские границы года, порядок партий, дубли/конфликт версий,
  дословность текстов, исключение вложений, идентичность сообщества,
  рандомизация 30/30, изменение контрольных сумм/состава снимка,
  read-only чтение реестра промптов, exact transport payload,
  medium, запрет fallback/retry, сохранение отказов и невалидных ответов,
  закрытый preflight при неутверждённой методике и дополнительных знаниях в canon.
- Python 3.12.14 Windows, изолированный venv, `pip check` без ошибок.
  Версии в requirements-windows.lock.txt; backend-окружение не менялось.
- OpenWiki 0.7.2, commit 6c14bff27830034bfd70c15bde46825d7686ec60:
  `pnpm install --frozen-lockfile --ignore-scripts`, штатный `pnpm run build`.
  Node v24.19.0, pnpm 11.25.0. Checkout после сборки чистый.
- OpenWiki fixture: штатный custom-mcp raw reader читает синтетический JSONL,
  отклоняет отсутствующую будущую партию и выход за raw-каталог, составляет
  personal init/update промпты. medium разрешается в responses-reasoning.
  fetch в fixture запрещён; модель/агент не запускались.
  Частный отчёт: `storage/experiments/yunost-2024/fixture-openwiki-01/fixture-report.json`.
- Linux fixture Tesla: **штатный** compile_wiki с native fcntl и fake Responses
  создаёт страницу с нуля, добавляет сведения второй партии insert_after,
  сохраняет сведения первой. Два extraction + два merge, все medium;
  полные request/response JSON сохранены. Код компилятора взят из Git archive
  коммита 19380cc8a3c59a242d4b6a44459248d357e1c5f6, не редактировался.
  Linux Python 3.14.4, python-dotenv 1.2.4, без модельных SDK и сети.
  Копия отчёта на Windows: `storage/experiments/yunost-2024/fixture-tesla-linux-report.json`.

## Обнаружено и сохранено

Первый Windows fixture создал страницу, но вторую партию штатная проверка
отклонила с `original page hash mismatch`: одна часть native ingest считает
SHA по байтам CRLF, другая — по нормализованному тексту LF. На Linux с тем же
кодом две партии проходят. Не исправляли основной алгоритм и не подменяли хеши.
Неудачный fixture сохранён: `storage/experiments/yunost-2024/fixture-tesla-01`.
Для измерения обе системы следует запускать на одном Linux runner; проверка
общего полного окружения ещё необходима. Windows не заявляется готовым runner.

В оригинальном canon есть исторические сведения вне корпуса, включая 2026 год.
Снимок сохраняет оригинал; отдельный исследовательский профиль ещё требует
решения пользователя и проверки diff. Это блокирует строгий корпусный запуск.

Настроенный API не подтвердил доступность модели: read-only GET /models завершился
URLError. Ключи не печатались. Model alias не заменялся на доступную модель.

## Не проверено и не объявляется готовым

Живой Responses endpoint, модельная JSON Schema, полный цикл OpenWiki на Luna,
сквозные логи его запросов/ответов, общий ограничитель бюджета, изоляция процессов
и сети, orchestration всех повторов, готовый gold, Langfuse import/annotation queues.
Синтетические ответы проверяют механику, а не качество LLM.
