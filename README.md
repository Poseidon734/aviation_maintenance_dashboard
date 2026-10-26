# Fleet Reliability Dashboard

Single-file dashboard (`index.html`) that computes CAMO/MCC reliability KPIs in the browser from `aviation_fault_maintenance_dataset_enriched.csv`. 

**Status: all three phases done.** Tabs: Fleet Overview, Dispatch & Delays, Components, Repetitive Defects, Pareto & Alert Levels, Aircraft, Data.

## Overview

**Fleet Reliability Dashboard** is a single-file, no-build web dashboard for aviation continuing airworthiness (CAMO) and maintenance control (MCC) teams. It loads a fault and maintenance event CSV and computes reliability KPIs entirely in the browser:

- **Fleet Overview**: dispatch reliability, technical delay rate and monthly trends, normalized by flight-hour exposure
- **Dispatch & Delays**: technical delays by ATA chapter and severity
- **Components**: unscheduled removal rate (URR), MTBUR, Weibull analysis and Jack-Knife diagrams
- **Repetitive Defects**: overlapping-window detection merged into episodes
- **Pareto & Alert Levels**: UCL-based alerts (mean + kσ) that exclude low-exposure months
- **Aircraft**: a relative Health Index and utilization scatter

Calculations are pure and DOM-free, and are verified against a pandas reference implementation through a built-in self-test. Built with vanilla HTML/CSS/JS and Chart.js.

> **Note:** the bundled dataset is not very realistic. Utilization values are physically implausible, so FH-based metrics are internally consistent only.

## Run

```bash
py -m http.server 8765        # from this folder
# open http://localhost:8765/index.html
```

Opening the file directly (`file://`) blocks loading the default CSV; use the drop zone in the **Data** tab instead.

Theme: the dashboard follows the system light/dark setting. The header button (☀ Light mode / ☾ Dark mode) overrides it and the choice is remembered in the browser (`localStorage`, key `fleet-reliability-theme`).

Deep links: `#overview`, `#dispatch`, `#components`, `#repetitive`, `#pareto`, `#aircraft`, `#data`. Add `?selftest` to compare the dashboard against the reference values.

## Verify

```bash
py execution/verify_aviation_kpis.py     # writes .tmp/kpi_golden.json (pandas reference calculation)
# then open http://localhost:8765/index.html?selftest  -> 299 PASS expected (fleet KPIs, UCL, delay minutes, MTBUR / MTTR / Weibull per part number, fleet quality, Health Index per aircraft, condition trends)
```

## Tabs added in Phase 2

- **Dispatch & Delays**: DR target and delay-rate scale (per 100 / 1,000 departures) controls; monthly DR and delay rate; technical delay minutes by ATA and by fault severity; top 10 aircraft by delay rate (aircraft with at least 3 active months).
- **Components**: sortable part-number table (removals, URR, MTBUR, MTTR, Weibull β and η, strategy), MTBUR chart, Jack-Knife (URR vs MTTR, quadrants by means) and a reliability curve per part number.
- **Repetitive Defects**: sliders for the day and cycle limits, episode table, and an aircraft × ATA event heatmap with repetitive pairs marked.

Weibull: rank regression on FH between consecutive unscheduled removals of the same part number on the same aircraft (28–48 intervals per part number). Units that have not yet failed are not modelled (no suspensions), so β may be biased. β &lt; 0.9 infant mortality, 0.9–1.1 random, &gt; 1.1 wear-out.

## Aircraft tab (Phase 3)

- **Fleet cards**: defect rate per 1,000 FH, high-severity share, maintenance effectiveness (% Effective, % Needs Improvement), average safety and inspection scores, FH per cycle.
- **Fleet Health Index (0–100, higher = healthier)** = 100 − weighted percentile rank, within the selected fleet, of: defects per 1,000 FH (35 %), technical delays per 100 departures (25 %), URR (20 %), high-severity share (10 %), 100 − safety score (10 %). Ties share the average rank. Aircraft with fewer than 3 active months are excluded, and at least 2 aircraft are needed. The index is relative: it changes when filters change the fleet being compared.
- **Ranking table** (15 least healthy; ▼ = worst 10 %), click a row for the **aircraft detail** (metrics and events per month).
- **Utilization vs defect rate** scatter uses flight hours per active day. FH per cycle is almost identical across aircraft (about 1.99) and the downward trend is mostly an exposure artifact (similar event counts regardless of hours).
- **Condition trend**: monthly mean ± 1 sd of the safety or inspection score; months with fewer than 20 events are omitted.
- **Defect rate by ATA** per 1,000 FH.

### How the Health Index is calculated

The index scores each aircraft **against the rest of the filtered fleet**, not against an absolute standard.

1. **Compute five metrics per aircraft** (all "lower is better"):

   | Metric | Definition | Weight |
   | --- | --- | --- |
   | Defect rate | Events per 1,000 FH | 35 % |
   | Technical delay rate | Technical delays per 100 departures | 25 % |
   | URR | Unscheduled removals per 1,000 FH | 20 % |
   | High-severity share | % of events with `Fault_Severity` = High | 10 % |
   | Safety gap | 100 − mean `Safety_Score` | 10 % |

2. **Convert each metric to a percentile rank** within the fleet, from 0 (best) to 100 (worst): `(rank − 1) / (N − 1) × 100`. Tied aircraft share the average rank.
3. **Take the weighted average** of the five percentiles (weights sum to 100 %).
4. **Invert it**: `Health Index = 100 − weighted percentile`. Higher means healthier.

Rules and consequences:

- Aircraft with fewer than 3 active months are excluded, and at least 2 aircraft are needed to compute the index.
- Because it is rank-based, the index shows *relative* position only. It does not say whether an aircraft is good in absolute terms, and the size of a metric gap is ignored (only the order matters).
- It changes whenever a filter changes the set of aircraft being compared.
- If the dataset has no `Safety_Score` column, the safety gap is dropped and the remaining weights are renormalized.
- The Python reference (`health_index()` in `execution/verify_aviation_kpis.py`) uses the same definition, and `?selftest` compares the index per aircraft.

## KPIs (Phase 1)

| KPI | Definition |
| --- | --- |
| Dispatch Reliability % | (departures − technical delays) / departures × 100. No cancellation field exists, so cancellations = 0. Target 99.0 %. |
| Technical delay rate | Technical delays (`Is_Technical_Delay` and `Delay_Minutes` > 15) per 100 departures. |
| URR / MTBUR | Unscheduled removals per 1,000 fleet FH; fleet FH per unscheduled removal. One unit of each part number per aircraft assumed. |
| Repetitive defects | 3 events, same aircraft and ATA, 1st→3rd within 5 days or 10 cycles. Overlapping windows merge into one episode. |
| Pareto | By ATA or part number; events, technical delays, delay minutes or removals. |
| Alert level (UCL) | Monthly defect rate per 1,000 FH per ATA; UCL = mean + k·sigma (k = 2 or 3) over 2024 months meeting the exposure threshold. |

## Exposure assumptions

- **Departures** = `Fleet_Avg_Monthly_Departures` × active months per aircraft (days between first and last event / 30.4375).
- **FH / FC in a period** = linear interpolation of cumulative values between events, clipped to the period.
- **Minimum monthly exposure** (default 5,000 fleet FH): lower months are shown grey and excluded from UCL and alerts.
- Date and aircraft filters change exposure; ATA and severity filters change events only.

## Expected values (no filters)

| KPI | Value |
| --- | --- |
| Dispatch Reliability | 98.29 % |
| Technical delay rate | 1.71 per 100 departures |
| URR | 0.833 per 1,000 FH |
| MTBUR | 1,200.6 FH |
| Repetitive (5 d / 10 cycles / 30 d windows) | 0 / 1 / 104 |
| Top Pareto ATA | 29 (814 events) |

## Data quality caveats

- 91 of 100 aircraft accumulate more than 24 flight hours per day, so FH-based metrics are internally consistent but not realistic in absolute terms.
- `Flight_Hours`, `Aircraft_Age` and `CNN_Feature_*` are not used.
- Event density drops sharply after 2025; late-period rates rest on little exposure.
- Pareto by ATA is nearly flat (775–814 events), so the 80/20 pattern does not appear by ATA.
