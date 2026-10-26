# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two independent single-file, no-build browser dashboards (vanilla HTML/CSS/JS, Chart.js from cdnjs):

- `index.html` — **IndustrialIQ**, an industrial maintenance dashboard (work orders, MTBF/MTTR, Weibull, Jack-Knife). Spanish UI. Documented in `README.md`. Treat as read-only unless asked.
- `aviation_dashboard.html` — **Fleet Reliability Dashboard** for CAMO/MCC aviation KPIs, computed in the browser from `aviation_fault_maintenance_dataset_enriched.csv`. KPI definitions are in `aviation_reliability_metrics_readme.md`; usage and assumptions in `README_aviation_dashboard.md`. This is the active work.

Not a git repository. There is no package manager, linter, or test framework.

## Hard requirement: aviation dashboard is English only

All user-facing text in `aviation_dashboard.html` (labels, tabs, tooltips, notifications, errors, notes, number/date locale `en-US`, `lang="en"`) must be English. `index.html` is Spanish (`lang="es"`, `toLocaleString('es')`), so anything copied from it must be translated. Chat with the user is in Spanish.

## Commands

```bash
py -m http.server 8765                       # serve this folder; open http://localhost:8765/aviation_dashboard.html
py execution/verify_aviation_kpis.py         # regenerate .tmp/kpi_golden.json (pandas reference values)
# open ...aviation_dashboard.html?selftest   # compares dashboard KPIs to the golden file (299 PASS expected)
```

- Use `py` (Windows launcher); `python` is a Store stub. `py -I` for ad-hoc scripts that read data.
- `file://` blocks the default CSV `fetch`; use the Data-tab drop zone or serve over HTTP.
- Hash deep links: `#overview`, `#dispatch`, `#components`, `#repetitive`, `#pareto`, `#aircraft`, `#data`.
- Large JS blocks pasted via Bash heredocs failed once; write them with the Write tool and splice with a small `py -I` script.
- Headless check used so far: Edge (`msedge.exe --headless=new --virtual-time-budget=15000 --dump-dom|--screenshot <url>`).

## Architecture of `aviation_dashboard.html`

One IIFE script, layered so calculations stay testable and DOM-free:

1. **Load/normalize** — `loadData` → `ingest` → `parseCSV`, `validateColumns` (fails fast on missing `REQUIRED` columns), `normalizeRows`. Dates become UTC day numbers; `techDelay = Is_Technical_Delay && Delay_Minutes > 15`.
2. **Exposure** — `buildAircraftIndex` + `calcExposure(lo, hi, aircraft)`: FH/FC by linear interpolation of cumulative counters clipped to the period; departures = `Fleet_Avg_Monthly_Departures` × active months (days / 30.4375). This is the single definition of exposure; date and aircraft filters change it, ATA and severity filters change events only.
3. **Pure calcs** — `calcKpis`, `calcMonthlySeries`, `calcUcl`, `calcPareto`, `calcRepetitive` (overlapping windows merged into episodes).
4. **Render** — `renderOverview`, `renderPareto`/`renderUcl`, `renderData`; `renderAll` re-renders only the active tab. Charts are tracked in `charts{}` and rebuilt via `destroyChart`. Reference lines (target, UCL, 80 %) are extra dashed datasets, not an annotation plugin. Axis bounds come from valid months only (`validRange`).
5. **Self-test** — `runSelfTest` compares unfiltered results to `.tmp/kpi_golden.json`.

Any text from the CSV that reaches `innerHTML` must go through `escapeHtml`.

Theming: colors are CSS variables on `:root`. Dark is the default, light comes from `prefers-color-scheme` unless `data-theme` is set on `<html>` by the header toggle (`setTheme`, persisted in `localStorage`). Charts read colors with `cssVar()` at render time, so any theme change must call `renderActive()`; when adding colors, define them for both themes (the light set appears twice in the CSS).

## Keeping Python and JS in sync

`execution/verify_aviation_kpis.py` is the reference implementation of the same definitions (exposure, UCL = mean + kσ over 2024 base months with ≥ `minFh` fleet FH, sample σ). If you change a KPI definition in the HTML, change it in the script, regenerate the golden file, and re-run `?selftest`.

## Dataset facts that drive the design

- 4,000 events, 100 aircraft, 2024-01 → 2026-09; event density collapses after 2025, so monthly rates are normalized by exposure and months under the minimum exposure (default 5,000 fleet FH) are excluded from UCL/alerts.
- Serial numbers are nearly unique, so URR/MTBUR are analyzed per part number (assumes one unit per aircraft).
- Utilization is physically implausible (91/100 aircraft > 24 FH/day), so FH-based metrics are internally consistent only; do not present absolute values as realistic.
- `Flight_Hours`, `Aircraft_Age`, `CNN_Feature_*` are unusable. No cancellation field exists (cancellations = 0).
- Control values (no filters): DR 98.29 %, TDR 1.71/100, URR 0.833/1,000 FH, MTBUR ≈ 1,200.6 FH, repetitive windows 0 (5 d) / 1 (10 cycles) / 104 (30 d), top ATA 29 with 814 events.

## Roadmap and plan

All three phases are done (Fleet Overview, Dispatch & Delays, Components, Repetitive Defects, Pareto & Alert Levels, Aircraft, Data). The approved plan is at `~/.claude/plans/linear-squishing-rain.md`. The SOP is `directives/aviation_reliability_dashboard.md` (refresh, verify, edge cases); keep it updated when definitions change. Not modelled: cancellations, Weibull suspensions.

The Health Index (`calcAircraftMetrics` → `calcHealthIndex`) is relative to the filtered fleet, so it is mirrored in `health_index()` of the Python script and compared per aircraft in `?selftest`. Aircraft scatter uses FH per active day because FH per cycle is nearly constant (~1.99) in this dataset.

Phase 2 was written fresh rather than copied from `index.html` (Weibull and Jack-Knife re-implemented as pure `calcWeibull` / `calcComponents`, checked against pandas). Weibull has no censoring by design.

## Project conventions (from AGENTS.md and `.agents/`)

- 3-layer model: directives (`directives/*.md`, SOPs) → orchestration (you) → deterministic scripts in `execution/`. Intermediates go in `.tmp/`. Do not create or overwrite directives without asking.
- Design skills in `.agents/skills/` (`dashboard-design-architect` = Storytelling with Data, `frontend-design`, `maintenance-expert`, `maintenance_data_analyst`). Palette convention: grey base, blue = on target, orange = alert, always with a second indicator (▲▼ / text); no pies, 3D, or dual axes; bars from zero.
- `.agents/rules/good-practice-development.md`: KISS/DRY/YAGNI, small single-purpose functions, fail fast at input boundaries.
