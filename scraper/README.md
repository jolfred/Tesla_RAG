# Social Media Post Scraper

Парсер постов из VK. Собирает посты из групп, очищает текст, извлекает хэштеги и
упоминания, сохраняет результат в JSONL. Поддерживает инкрементальный сбор:
при повторном запуске докачивает только новые посты.

## Требования

- Python 3.12+
- VK Service Token (получить: https://vk.com/dev/access_token)

## Установка

```bash
# Клонировать репозиторий (если ещё не)
git clone <repo-url> && cd <repo>

# Создать виртуальное окружение
python3 -m venv .venv

# Активировать
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Установить зависимости
pip install -r scraper/requirements.txt

# Настроить токен
cp .env.example .env  # или создать .env вручную
```

В `.env` обязательно указать:

```ini
VK_SERVICE_TOKEN=vk1.a.ваш_токен_тут
```

## Использование

```bash
# Одна группа
python -m scraper.main --url https://vk.com/rso_tesla

# Несколько групп
python -m scraper.main --url https://vk.com/rso_tesla --url https://vk.com/kgeu_official

# Файл со списком групп (по одной на строку, # — комментарий)
python -m scraper.main --url-file urls.txt

# Ограничить количество постов на группу
python -m scraper.main --url https://vk.com/rso_tesla --limit 500

# Подробные логи (DEBUG)
python -m scraper.main --url https://vk.com/rso_tesla -v
```

## Как это работает

1. Скрипт определяет `owner_id` группы через VK API (`utils.resolveScreenName`)
2. Запрашивает посты через `wall.get` пачками по 100 штук
3. Каждый пост очищается: удаляются эмодзи, извлекаются хэштеги и упоминания
4. Результат дописывается в `storage/posts/posts_{domain}.jsonl`

**При первом запуске** скачиваются все доступные посты группы.

**При повторном запуске** скрипт читает дату последнего сохранённого поста из
`.jsonl` и запрашивает только посты новее неё — дубликаты не появляются.

Чтобы собрать всё заново — удалите или переименуйте соответствующий файл:

```bash
mv storage/posts/posts_rso_tesla.jsonl storage/posts/posts_rso_tesla.jsonl.bak
python -m scraper.main --url https://vk.com/rso_tesla
```

## Формат данных

Каждая строка в `.jsonl` — один пост в формате JSON:

```json
{
  "post_id": "12345",
  "source_platform": "vk",
  "group_id": "91740386",
  "group_name": "Студенческие отряды КГЭУ «Тесла» | РСО",
  "group_domain": "rso_tesla",
  "post_url": "https://vk.com/rso_tesla?w=wall-91740386_12345",
  "published_at": "2024-01-15T14:30:00+00:00",
  "text_raw": "Оригинальный текст поста #тесла @club123",
  "text_clean": "Очищенный текст поста",
  "hashtags": ["тесла"],
  "mentions": [{"id": "123", "name": "Club Name", "raw": "@club123"}],
  "attachments": {
    "photos": ["https://...photo_url..."],
    "links": ["https://...", "https://..."],
    "docs": []
  }
}
```

## Логи

- **Консоль (stderr)**: INFO по умолчанию, DEBUG с флагом `-v`
- **Файл**: `logs/scraper.log` — ротация 5 файлов по 10 MB, UTF-8

## CLI-аргументы

| Аргумент | Описание |
|----------|----------|
| `--url` | Ссылка на группу (можно указывать несколько раз) |
| `--url-file` | Файл со списком ссылок (по одной на строку, `#` — комментарий) |
| `--limit N` | Максимум постов на группу (0 = все доступные) |
| `-v`, `--verbose` | Подробные логи (DEBUG) |

## Тестирование

```bash
pytest scraper/tests/ -v
```

## Структура проекта

```
scraper/
├── cleaners/          # Очистка текста, извлечение хэштегов и упоминаний
│   └── text_cleaner.py
├── extractors/        # Загрузчики (VK API)
│   ├── base.py
│   └── vk.py
├── orchestrator/      # Координация: resolve → fetch → clean → save
│   └── parser_orchestrator.py
├── storage/           # Запись JSONL-файлов
│   └── writer.py
├── tests/             # 45 pytest-тестов
├── utils/             # Логирование, retry
│   ├── logger.py
│   └── retry.py
├── models.py          # Pydantic-схемы (SocialMediaPost, Mention, Attachments)
├── main.py            # Точка входа (CLI)
└── requirements.txt   # Зависимости
```
