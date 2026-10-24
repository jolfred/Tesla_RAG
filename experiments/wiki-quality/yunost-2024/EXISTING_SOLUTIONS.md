# Проверка готовых решений, 24.10.2026

Решение для текущего сравнения: сохранить штатные ingest Tesla и OpenWiki.
Собственный оценочный framework не разрабатывать. Подготовленные Python/Node
адаптеры отвечают только за передачу фиксированного месяца, изоляцию и сохранение
артефактов; они не выставляют оценки. Для просмотра и проверки сохранённых Wiki
выбран готовый Promptfoo с echo provider. Его подключение ещё не выполнено:
исторических выходов пока нет. Первичные оценки остаются человеческими.

| Готовое решение | Проверенные возможности | Применимость |
| --- | --- | --- |
| OpenWiki LEDGER | Git replay, init/update, immutable artifacts, SystemUnderTest / EvaluationBackend, повторная оценка без генерации | Есть даже в закреплённом checkout. Основной знаменатель — current-tense claims, историческое повествование исключается. Штатный system adapter использует repository mode. Принимать его метрику как оценку нашей исторической Wiki нельзя. |
| Promptfoo | Внешние программы через exec, local results/viewer, echo для заранее сохранённых выходов, Codex SDK / app-server providers | Подходит для оценки без повторного построения Wiki. Последовательность месяцев, SQLite состояния native Tesla и контроль источников всё равно требуют адаптера. |
| Inspect AI / Inspect SWE | Sandbox, eval logs, epochs, failure/retry/resume | Реальная альтернатива при расширении работы. Готовый Inspect SWE Codex solver проксирует calls через Inspect provider; сохранение выбранного native subscription transport не подтверждено. Потребовался бы custom solver. |
| LangSmith | Версии datasets, experiments, external experiment upload, human/pairwise annotation queues | Полезен для коллективной разметки позже. SDK открыт; наличие SDK не означает бесплатную самостоятельную платформу. Новая отправка нашего корпуса в сервис не включалась. |
| OpenEvals | Готовые correctness / groundedness и другие evaluators | Вторичная оценка после калибровки по человеческим решениям. Не заменяет runner и не даёт независимый эталон сама по себе. |
| Bubblewrap | Готовая изоляция процессов с новым mount namespace и явными read-only/read-write mounts | Используется уже установленный bwrap. Наш код задаёт файловую конфигурацию и проверяет её, не реализует контейнер или sandbox самостоятельно. |
| Codex permission profiles | Готовые ограничения чтения путей | Рассмотрены. Штатный pinned Tesla CLI передаёт --sandbox; официальная документация предупреждает, что этот флаг выбирает legacy sandbox вместо permission profiles. Для сохранения native вызова используется внешний bwrap. |

Promptfoo поддерживает Codex с существующим ChatGPT login, выбранным model и
reasoning effort. Но документация provider задаёт отдельную версию SDK; замена
Tesla call_provider на этот SDK без проверки изменила бы транспорт. Поэтому
для текущего сравнения native вызов сохраняется. Оценка через echo вообще
не требует нового вызова генератора. Возможные LLM judges выключены.

Проверены README и исходники OpenWiki LEDGER (runner, types, system adapter),
документация и исходник Promptfoo Codex provider, интерфейсы Inspect, LangSmith
и OpenEvals. GitHub CLI отсутствует; использованы первичные страницы GitHub
и официальная документация. Сайты и main ветки меняются; рабочие реализации
генераторов по-прежнему закреплены SHA в protocol.json.

Источники:

- [OpenWiki LEDGER](https://github.com/langchain-ai/openwiki/tree/main/evals/ledger), [runner](https://github.com/langchain-ai/openwiki/blob/main/evals/ledger/run/runner.ts), [interfaces](https://github.com/langchain-ai/openwiki/blob/main/evals/ledger/core/types.ts).
- [Promptfoo exec](https://www.promptfoo.dev/docs/providers/custom-script/), [echo](https://www.promptfoo.dev/docs/providers/echo/), [Codex SDK source](https://github.com/promptfoo/promptfoo/blob/main/src/providers/openai/codex-sdk.ts).
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), [Inspect SWE Codex solver](https://meridianlabs-ai.github.io/inspect_swe/codex_cli.html).
- [LangSmith SDK](https://github.com/langchain-ai/langsmith-sdk), [existing experiments](https://docs.langchain.com/langsmith/upload-existing-experiments), [annotation queues](https://docs.langchain.com/langsmith/annotation-queues).
- [OpenEvals](https://github.com/langchain-ai/openevals).
- [Bubblewrap](https://github.com/containers/bubblewrap/blob/main/README.md).
- [Official Codex permissions](https://learn.chatgpt.com/docs/permissions).
