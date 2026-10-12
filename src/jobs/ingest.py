"""Refresh everything: every catalog series (FRED + BEA) and the Fed-speak data.

Same thing as the dashboard's "Refresh all data" button, for scheduled use
(e.g. a Databricks job):  python -m src.jobs.ingest
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config, data
from src.jobs import fedspeak


def run() -> list[str]:
    failures = data.refresh([s.id for s in config.SERIES])
    print(f"Series: {len(config.SERIES) - len(failures)}/{len(config.SERIES)} refreshed"
          + (f"; failed (kept previous data): {failures}" if failures else ""))
    fedspeak.run()
    return failures


if __name__ == "__main__":
    run()
