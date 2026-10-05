"""Compile the readable bibliography for the Wiki site (no LLM calls)."""
import argparse
import json
import os
from pathlib import Path

from backend.wiki.sources import ROOT, build_source_index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--posts', type=Path, default=ROOT/'storage/posts')
    parser.add_argument('--wiki', type=Path, default=ROOT/'storage/wiki')
    args=parser.parse_args()
    index=build_source_index(args.posts)
    args.wiki.mkdir(parents=True, exist_ok=True)
    target=args.wiki/'_sources.json'
    temporary=target.with_suffix('.json.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(index,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    temporary.replace(target)
    print(json.dumps({'source_titles':len(index),'bibliography':str(target)},ensure_ascii=False))


if __name__=='__main__':
    main()
