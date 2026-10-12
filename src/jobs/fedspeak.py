"""Fed-speak job — refresh speeches, tone, the speaker calendar and FOMC dates.

    python -m src.jobs.fedspeak          (also run at the end of src.jobs.ingest)

Incremental: a speech is fetched and classified once (keyed by URL); re-runs
only add new speeches. If ANTHROPIC_API_KEY becomes available, speeches scored
by the lexicon are re-scored by Claude (``RESCORE_PER_RUN`` at a time).

Writes to STORE_PATH:
    fedspeak_speeches.parquet   one row per speech/remark, with summary & tone
    fedspeak_calendar.parquet   scheduled appearances (Board + manual + web)
    fomc_meetings.parquet       scheduled meetings (start, end)
    fedspeak_status.parquet     run timestamp, method, per-source errors
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src import config
from src.ingest import fedspeak as src_fs
from src.ingest import llm
from src.transform import fedspeak as tone
from src.transform import fomc

LOOKBACK_DAYS = 180       # speeches kept in the store
RESCORE_PER_RUN = 40      # lexicon → Claude upgrades per run
REF = config.PROJECT_ROOT / "reference"


def _path(name: str) -> Path:
    return config.STORE_PATH / f"{name}.parquet"


def _load(name: str) -> pd.DataFrame:
    return pd.read_parquet(_path(name)) if _path(name).exists() else pd.DataFrame()


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:40]


def _score(row: dict, roster: pd.DataFrame, use_llm: bool) -> dict:
    if len(row["text"]) < 600:
        return {"tone_score": None, "tone_label": "No transcript", "about_policy": False,
                "summary": "", "tone_method": "none"}
    if use_llm:
        who = roster.set_index("key").loc[row["speaker"]]
        try:
            out = llm.classify(who["full_name"], f"{who['position']}, {who['institution']}",
                               row["title"], f"{row['date']:%Y-%m-%d}", row["text"])
            out["about_policy"] = out.pop("about_monetary_policy")
            return out
        except Exception as exc:  # noqa: BLE001 — fall back to the lexicon
            print(f"[warn] Claude classify {row['url']}: {exc}")
    return tone.score_text(row["text"])


def run(use_llm: bool | None = None) -> dict:
    use_llm = llm.available() if use_llm is None else use_llm
    config.STORE_PATH.mkdir(parents=True, exist_ok=True)
    roster = fomc.load_roster()
    today = pd.Timestamp.today().normalize()
    since = today - pd.Timedelta(days=LOOKBACK_DAYS)

    # --- Speeches -------------------------------------------------------------
    refs, errors = src_fs.speech_index(roster)
    old = _load("fedspeak_speeches")
    known = set(old["url"]) if not old.empty else set()
    primary = {(r.speaker, _norm(r.title)) for r in refs if r.source != "BIS"}
    new_rows = []
    for r in refs:
        if r.url in known or (r.source == "BIS" and (r.speaker, _norm(r.title)) in primary):
            continue
        if r.date is not None and r.date < since:
            continue
        known.add(r.url)
        try:
            text, page_date = src_fs.fetch_document(r.url)
        except Exception as exc:  # noqa: BLE001
            errors[f"doc:{r.url}"] = str(exc)[:200]
            continue
        date = r.date if r.date is not None else page_date
        if date is None or date < since:
            continue
        row = {"speaker": r.speaker, "date": date, "title": r.title, "url": r.url,
               "source": r.source, "text": text}
        row.update(_score(row, roster, use_llm))
        new_rows.append(row)

    speeches = pd.concat([old, pd.DataFrame(new_rows)], ignore_index=True)
    if speeches.empty:
        speeches = pd.DataFrame(columns=["speaker", "date", "title", "url", "source", "text",
                                         "tone_score", "tone_label", "about_policy", "summary",
                                         "tone_method"])

    # Upgrade lexicon scores once Claude is available.
    if use_llm and not speeches.empty:
        todo = speeches.index[speeches["tone_method"] == "lexicon"][:RESCORE_PER_RUN]
        for i in todo:
            out = _score(speeches.loc[i].to_dict(), roster, True)
            for k, v in out.items():
                speeches.at[i, k] = v

    # Remarks the scrapers can't see: unreachable banks + interviews (web search).
    if use_llm:
        try:
            gaps = roster[roster["key"].isin(src_fs.UNREACHABLE.values())]
            web = llm.search_remarks(gaps, today - pd.Timedelta(days=45))
            if not web.empty:
                web = web[~web["url"].isin(speeches.get("url", pd.Series(dtype=str)))]
                speeches = pd.concat([speeches, web.assign(text="")], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            errors["web remarks"] = str(exc)[:200]

    manual = pd.read_csv(REF / "fedspeak_remarks_manual.csv", parse_dates=["date"])
    if not manual.empty:
        manual = manual.assign(source="Manual", text="", tone_method="manual",
                               about_policy=manual["tone_score"].notna(),
                               tone_label=[tone.label_for(s) for s in manual["tone_score"]])
        speeches = pd.concat([speeches[speeches.get("source") != "Manual"], manual],
                             ignore_index=True)

    speeches["date"] = pd.to_datetime(speeches["date"])
    speeches = (speeches[speeches["date"] >= since]
                .drop_duplicates("url").sort_values("date", ascending=False))
    speeches["tone_score"] = pd.to_numeric(speeches["tone_score"], errors="coerce")
    speeches.to_parquet(_path("fedspeak_speeches"), index=False)

    # --- Calendar & meetings ----------------------------------------------------
    cal_frames = []
    try:
        cal_frames.append(src_fs.board_calendar(roster))
    except Exception as exc:  # noqa: BLE001
        errors["Board calendar"] = str(exc)[:200]
    manual_cal = pd.read_csv(REF / "fedspeak_calendar_manual.csv", parse_dates=["date"])
    if not manual_cal.empty:
        cal_frames.append(manual_cal.assign(source="Manual", type="Speeches"))
    if use_llm:
        try:
            cal_frames.append(llm.search_calendar(roster, days=7))
        except Exception as exc:  # noqa: BLE001
            errors["web calendar"] = str(exc)[:200]
    calendar = pd.concat(cal_frames, ignore_index=True) if cal_frames else pd.DataFrame()
    if not calendar.empty:
        calendar["date"] = pd.to_datetime(calendar["date"])
        calendar = calendar[calendar["date"] >= today - pd.Timedelta(days=30)]
        # Board entries win over web duplicates of the same speaker/day.
        calendar["_rank"] = calendar["source"].map({"Board calendar": 0, "Manual": 1}).fillna(2)
        has_spk = calendar["speaker"].notna()
        calendar = pd.concat([
            calendar[has_spk].sort_values("_rank").drop_duplicates(["date", "speaker", "event"]),
            calendar[~has_spk]]).drop(columns="_rank").sort_values("date")
        for c in calendar.columns.drop("date"):
            calendar[c] = calendar[c].fillna("").astype(str)
        calendar.to_parquet(_path("fedspeak_calendar"), index=False)

    try:
        meetings = src_fs.fomc_meetings()
        pd.DataFrame(meetings, columns=["start", "end"]).to_parquet(_path("fomc_meetings"), index=False)
    except Exception as exc:  # noqa: BLE001
        errors["FOMC meetings"] = str(exc)[:200]

    status = pd.DataFrame([{
        "run_at": pd.Timestamp.now(tz="UTC"), "method": "claude" if use_llm else "lexicon",
        "n_speeches": len(speeches), "n_new": len(new_rows),
        "errors": "; ".join(f"{k}: {v}" for k, v in errors.items() if not k.startswith("doc:")),
        "doc_errors": sum(k.startswith("doc:") for k in errors),
    }])
    status.to_parquet(_path("fedspeak_status"), index=False)
    print(f"Fed-speak: {len(speeches)} speeches ({len(new_rows)} new, method="
          f"{'claude' if use_llm else 'lexicon'}); calendar {len(calendar)} rows; "
          f"source errors: {[k for k in errors if not k.startswith('doc:')]}")
    return status.iloc[0].to_dict()


if __name__ == "__main__":
    run()
