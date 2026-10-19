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
from src.nowcast import run as nowcast_run


def run() -> list[str]:
    res = data.refresh([s.id for s in config.SERIES] + nowcast_run.FRED_INPUTS)
    print(res.summary())
    fedspeak.run()
    print(nowcast_run.safe_update(refresh_inputs=False))
    return res.failed


if __name__ == "__main__":
    run()
