"""Job-раннер индексации проекта: состав из admin.db -> process_indexer.

Запуск: .venv/bin/python -m backend.admin.run_index <slug>
        [--model gigachat] [--extractor transformer] [--min-date ''] [--force]
Ключи подхватываются из env сабпроцесса (jobs._env_with_secrets уже
подставил override из admin.db).
"""

from __future__ import annotations

import argparse

from backend.admin.db import init_admin_db
from backend.admin.indexing import load_doc_posts, project_composition, project_posts_paths
from backend.indexer.indexer import process_indexer


def main() -> None:
    parser = argparse.ArgumentParser(description="Index project into its own namespace")
    parser.add_argument("slug", help="Project slug")
    parser.add_argument("--model", default="gigachat", choices=["gigachat", "gemma", "proxyapi"])
    parser.add_argument("--extractor", default="transformer", choices=["legacy", "transformer"])
    parser.add_argument("--min-date", default="", help="ISO date or empty = all")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init_admin_db()
    comp = project_composition(args.slug)
    paths = project_posts_paths(args.slug)
    docs = load_doc_posts(comp["docs"])
    print(f"Project {args.slug}: {len(paths)} posts files, {len(docs)} docs", flush=True)
    process_indexer(
        paths,
        model=args.model,
        min_date=args.min_date,
        extractor=args.extractor,
        force=args.force,
        project_slug=args.slug,
        extra_posts=docs,
    )


if __name__ == "__main__":
    main()
