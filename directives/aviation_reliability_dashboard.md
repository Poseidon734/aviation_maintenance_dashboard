# Directive: Aviation Reliability Dashboard

## Goal

Maintain and refresh `aviation_dashboard.html`, a single-file browser dashboard of CAMO/MCC reliability KPIs computed from a fault-maintenance CSV, and prove that its numbers match an independent reference calculation.

## Inputs

- `aviation_fault_maintenance_dataset_enriched.csv` (default) or any CSV with the same columns, loaded through the Data-tab drop zone.
- Required columns (the dashboard fails fast without them): `Aircraft_ID`, `Event_Date`, `ATA_Chapter`, `Is_Technical_Delay`, `Unscheduled_Removal`, `Part_Number`, `Cumulative_Flight_Hours`, `Cumulative_Flight_Cycles`, `Fleet_Avg_Monthly_Departures`, `Delay_Minutes`.
- Optional columns that enable more views: `Subsystem`, `Fault_Severity`, `Repair_Time_Hours` (MTTR), `Safety_Score`, `Inspection_Score`, `Maintenance_Effectiveness`.
- KPI definitions: `aviation_reliability_metrics_readme.md`. Assumptions and expected values: `README_aviation_dashboard.md`.

## Tools

| Layer | File | Role |
| --- | --- | --- |
| Execution | `execution/verify_aviation_kpis.py` | Reference (pandas) calculation of every KPI; writes `.tmp/kpi_golden.json` |
| Deliverable | `aviation_dashboard.html` | The dashboard. Pure `calc*` functions are checked by `?selftest` |
| Docs | `README_aviation_dashboard.md`, `CLAUDE.md` | Usage, definitions, project guidance |

## Procedure

1. **Refresh the reference values**: `py -I execution/verify_aviation_kpis.py [csv] [out_json]`. Use `py`, not `python` (Windows Store stub).
2. **Serve the folder**: `py -m http.server 8765`, then open `http://localhost:8765/aviation_dashboard.html`. `file://` blocks the default CSV fetch.
3. **Run the self-test**: open `...aviation_dashboard.html?selftest`. Every row must be PASS (299 with the current dataset). Any FAIL means the HTML and the Python script disagree; fix the one that deviates from the definition in the README, never loosen the tolerance (0.01).
4. **Spot-check the control values** (current dataset, no filters): Dispatch Reliability 98.29 %, technical delay rate 1.71 per 100 departures, URR 0.833 per 1,000 FH, MTBUR 1,200.6 FH, repetitive windows 0 (5 d) / 1 (10 cycles) / 104 (30 d), top ATA 29 with 814 events. With a new dataset these change; the self-test is the authority.
5. **Check the UI**: no console errors, every tab renders, no horizontal scroll at 390 px, and no Spanish text.
6. **Update docs** if a definition, tab, or expected value changed (README, CLAUDE.md, this directive).

## Rules

- The dashboard UI is **English only** (`lang="en"`, `en-US` formats). Chat with the user is in Spanish.
- A KPI definition change must be made in both the HTML and `verify_aviation_kpis.py`, then the golden file regenerated.
- Text from the CSV that goes into `innerHTML` must pass through `escapeHtml`.
- Deliverable stays a single HTML file (Chart.js 4.4.1 from cdnjs); intermediates live in `.tmp/`.

## Edge cases and learnings

- **Departures definition**: `Fleet_Avg_Monthly_Departures` × active months (days between first and last event / 30.4375). Counting 33 months for every aircraft gives DR 98.98 %; using cumulative cycles as departures gives 99.61 %. These are shown on the Data tab for information only.
- **Exposure by period**: cumulative hours and cycles are interpolated linearly between events and clipped to the period. Months below the minimum fleet exposure (default 5,000 FH) are greyed out and excluded from UCL and alerts; late months have very few events.
- **Impossible utilization**: 91 of 100 aircraft exceed 24 FH per day and cycles imply ~4× the declared departures. FH-based metrics are internally consistent but not absolute truths. FH per cycle is almost constant (~1.99), so the aircraft scatter uses FH per active day.
- **Repetitive defects**: count episodes, not windows (overlapping windows merge). 104 windows at 30 days correspond to 89 episodes and 86 aircraft×ATA pairs.
- **Pareto by ATA is nearly flat** (775–814 events); use the part-number dimension for prioritisation.
- **Weibull** uses intervals between consecutive removals of the same part number on the same aircraft, with Bernard median ranks and no suspensions, so β may be biased.
- **Health Index** is relative to the filtered fleet (percentile ranks), needs at least 2 aircraft, and excludes aircraft with fewer than 3 active months. Ties use the average rank, matching `pandas.rank(method="average")`.
- **Large code blocks**: pasting big JS blocks through Bash heredocs failed once. Write them with the Write tool and splice with a small `py -I` script, asserting each anchor appears exactly once.
- **Test server**: the headless checks use Edge (`msedge.exe --headless=new --virtual-time-budget=... --dump-dom|--screenshot`). Stop `http.server` by its own PID, not by killing every Python process.
- **Not modelled**: technical cancellations (assumed 0), Weibull suspensions.
