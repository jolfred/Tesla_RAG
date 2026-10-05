#!/usr/bin/env python3
"""Compatibility entry point; provider calls are deliberately explicit elsewhere.

The previous pilot hardcoded СПО «Юность», truncated source posts, converted
provider refusal into fake noise, and wrote done.txt before durable page writes.
Use scripts/wiki_ingest.py inventory/export/import/stage-merge/apply-merge instead.
This file remains as a discoverable pointer and never makes paid provider calls.
"""
from pathlib import Path

if __name__ == "__main__":
    print("GigaChat pilot disabled: use scripts/wiki_ingest.py for the validated offline ledger workflow.")
