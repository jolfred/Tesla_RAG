import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from scraper.extractors.vk import VkApiExtractor
from scraper.models import GroupMeta
from scraper.orchestrator.parser_orchestrator import ParserOrchestrator
from scraper.storage.writer import write_group_meta
from scraper.utils.logger import setup_logger


def _read_urls_from_file(path: str) -> list[str]:
    urls: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            urls.append(line)
    return urls


def _resolve_urls(args_url: list[str], args_url_file: str | None) -> list[str]:
    urls: list[str] = []
    if args_url:
        urls.extend(args_url)
    if args_url_file:
        urls.extend(_read_urls_from_file(args_url_file))
    if not urls:
        logging.getLogger("scraper").error("Укажите --url или --url-file")
        sys.exit(1)
    return urls


def _collect_meta(urls: list[str], token: str, logger: logging.Logger) -> None:
    errors = 0
    vk_urls = [u for u in urls if "vk." in u]
    for idx, url in enumerate(vk_urls, 1):
        logger.info("Метаданные [%d/%d]: %s", idx, len(vk_urls), url)
        try:
            extractor = VkApiExtractor(token)
            info = extractor.resolve_group(url)
            meta = extractor.fetch_group_meta()
            domain = info["group_domain"]
            out = f"storage/groups/groups_{domain}.json"
            write_group_meta(GroupMeta(**meta), out)
            logger.info("Сохранено: %s", out)
        except Exception as e:
            logger.error("Ошибка: %s", e)
            errors += 1
    logger.info("Метаданные: %d групп, %d ошибок", len(vk_urls), errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Парсер постов из социальных сетей")
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Ссылка на группу (можно несколько раз), например --url https://vk.com/rso_tesla",
    )
    parser.add_argument(
        "--url-file",
        help="Файл со списком ссылок (по одной на строку, # — комментарий)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Количество постов на группу (0 = все доступные, по умолчанию 0)",
    )
    parser.add_argument(
        "--meta",
        action="store_true",
        help="Собрать только метаданные групп (описание, контакты, ссылки) в storage/groups/",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Подробные логи (DEBUG)",
    )
    args = parser.parse_args()

    setup_logger(verbose=args.verbose)
    logger = logging.getLogger("scraper.main")

    load_dotenv()
    token = os.getenv("VK_SERVICE_TOKEN") or os.getenv("VK_SERVICE_TOKEN1")
    if not token:
        logger.error("VK_SERVICE_TOKEN не найден в .env")
        sys.exit(1)

    urls = _resolve_urls(args.urls or [], args.url_file)
    logger.info("Запуск парсера: %d групп(ы), лимит: %s", len(urls), args.limit if args.limit else "все")

    if args.meta:
        _collect_meta(urls, token, logger)
        return

    orchestrator = ParserOrchestrator()
    total = 0
    errors = 0

    for idx, url in enumerate(urls, 1):
        logger.info("Обработка [%d/%d]: %s", idx, len(urls), url)
        try:
            saved = orchestrator.run(
                platform="vk",
                group_url=url,
                limit=args.limit,
                token=token,
            )
            logger.info("Сохранено: %d", saved)
            total += saved
        except Exception as e:
            logger.error("Ошибка: %s", e)
            errors += 1

    logger.info("Итого: %d групп, %d постов, %d ошибок", len(urls), total, errors)


if __name__ == "__main__":
    main()
