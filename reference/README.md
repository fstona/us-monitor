# Reference files

| File | What | Source |
|---|---|---|
| `fomc_roster.csv` | FOMC participants, seat (for the voting rotation) and `hawk_itc`, a hawk/dove scale from −1 (most dovish) to +1 (most hawkish) | **ITC Markets Research, "FOMC – ITC Hawk/Dove Analysis", last update 14 September 2026** — https://www.itcmarkets.com/wp-content/uploads/2020/02/FOMC-76.png. Values were read from the bar lengths of the published chart (approximate); refresh them when ITC republishes. Names, positions and seats: Federal Reserve. |
| `fedspeak_calendar_manual.csv` | Speaking engagements to add by hand (date, time ET, speaker key, event…) | Your own entries |
| `fedspeak_remarks_manual.csv` | Remarks to add by hand, e.g. for St. Louis / Kansas City Fed presidents, whose sites block scripted access | Your own entries |

Voting status is not stored here: it is computed from the statutory rotation in `src/transform/fomc.py`.
