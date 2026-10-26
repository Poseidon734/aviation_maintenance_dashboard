"""Reference (golden) KPI calculation for the aviation reliability dashboard.

Uses the same definitions as aviation_dashboard.html (see plan):
  - departures = Fleet_Avg_Monthly_Departures x active months (days between first and last event / 30.4375)
  - FH/FC per month = linear interpolation of Cumulative_* between events, clipped to the month
  - UCL = mean + k*sigma over the 2024 base months that meet the minimum exposure

Usage: py execution/verify_aviation_kpis.py [csv_path] [out_json]
Output: .tmp/kpi_golden.json (compared by the dashboard's ?selftest mode)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DAYS_PER_MONTH = 30.4375
MIN_MONTH_FH = 5000
BASE_YEAR = "2024"
MIN_ACTIVE_MONTHS = 3
MIN_QUALITY_EVENTS = 20
HEALTH_WEIGHTS = {"defectRate": 35, "tdr": 25, "urr": 20, "highPct": 10, "safetyGap": 10}
REQUIRED = ["Aircraft_ID", "Event_Date", "ATA_Chapter", "Is_Technical_Delay", "Unscheduled_Removal",
            "Part_Number", "Cumulative_Flight_Hours", "Cumulative_Flight_Cycles",
            "Fleet_Avg_Monthly_Departures", "Delay_Minutes"]


def load(path):
    df = pd.read_csv(path, parse_dates=["Event_Date"])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    return df.sort_values(["Aircraft_ID", "Event_Date"]).reset_index(drop=True)


def monthly_fleet_fh(df, months):
    fh = np.zeros(len(months))
    for _, g in df.groupby("Aircraft_ID"):
        t = g.Event_Date.values.astype("datetime64[D]").astype(float)
        h = g.Cumulative_Flight_Hours.values.astype(float)
        for i, m in enumerate(months):
            lo = max(m.start_time.to_datetime64().astype("datetime64[D]").astype(float), t[0])
            hi = min((m.end_time.to_datetime64().astype("datetime64[D]") + 1).astype(float), t[-1])
            if hi > lo:
                fh[i] += np.interp(hi, t, h) - np.interp(lo, t, h)
    return fh


def repetitive(df, max_days=None, max_cycles=None):
    """Count 1st->3rd windows and distinct aircraft x ATA pairs."""
    windows, pairs = 0, set()
    for key, s in df.groupby(["Aircraft_ID", "ATA_Chapter"]):
        d, c = s.Event_Date.values, s.Cumulative_Flight_Cycles.values
        for i in range(len(s) - 2):
            hit = (max_days is not None and (d[i + 2] - d[i]) / np.timedelta64(1, "D") <= max_days) or \
                  (max_cycles is not None and c[i + 2] - c[i] <= max_cycles)
            if hit:
                windows += 1
                pairs.add(key)
    return {"windows": windows, "pairs": len(pairs)}


def weibull_fit(intervals):
    """Rank regression (Bernard median ranks, y on x). No censoring: only observed removal-to-removal intervals."""
    t = np.sort(np.asarray([x for x in intervals if x > 0], dtype=float))
    n = len(t)
    if n < 3:
        return None
    f = (np.arange(1, n + 1) - 0.3) / (n + 0.4)
    x, y = np.log(t), np.log(-np.log(1 - f))
    beta, intercept = np.polyfit(x, y, 1)
    return {"beta": float(beta), "eta": float(np.exp(-intercept / beta)), "n": n}


def weibull_by_pn(df):
    removals = df[df.Unscheduled_Removal]
    out = {}
    for pn, s in removals.groupby("Part_Number"):
        intervals = s.groupby("Aircraft_ID").Cumulative_Flight_Hours.diff().dropna()
        fit = weibull_fit(intervals)
        if fit:
            out[pn] = fit
    return out


def fleet_quality(df, fleet_fh):
    """Complementary fleet-level KPIs (defect rate, severity mix, maintenance effectiveness, condition scores)."""
    n = len(df)
    out = {"defect_rate_per_1000fh": 1000 * n / fleet_fh,
           "high_severity_pct": 100 * float((df.Fault_Severity == "High").sum()) / n}
    if "Maintenance_Effectiveness" in df:
        eff = df.Maintenance_Effectiveness.value_counts()
        out["effective_pct"] = 100 * float(eff.get("Effective", 0)) / eff.sum()
        out["needs_improvement_pct"] = 100 * float(eff.get("Needs Improvement", 0)) / eff.sum()
    for col, key in (("Safety_Score", "mean_safety"), ("Inspection_Score", "mean_inspection")):
        if col in df:
            out[key] = float(df[col].mean())
    return out


def quality_monthly(df, col, min_events=MIN_QUALITY_EVENTS):
    """Monthly mean and sample sd of a condition score, only for months with enough events."""
    if col not in df:
        return {}
    s = df.groupby(df.Event_Date.dt.to_period("M"))[col].agg(["count", "mean", "std"])
    s = s[s["count"] >= min_events]
    return {str(k): {"n": int(r["count"]), "mean": float(r["mean"]), "sd": float(r["std"])} for k, r in s.iterrows()}


def health_index(df):
    """Fleet Health Index 0-100 (higher = healthier): 100 - weighted percentile rank of each metric within the fleet.

    Aircraft with fewer than MIN_ACTIVE_MONTHS active months are excluded. Ties use the average rank.
    """
    g = df.groupby("Aircraft_ID")
    dep = g.Fleet_Avg_Monthly_Departures.first()
    span = (g.Event_Date.max() - g.Event_Date.min()).dt.days
    departures = dep * span / DAYS_PER_MONTH
    fh = g.Cumulative_Flight_Hours.max() - g.Cumulative_Flight_Hours.min()
    n = g.size()
    tech = (df.Is_Technical_Delay & (df.Delay_Minutes > 15)).groupby(df.Aircraft_ID).sum()
    removals = df.Unscheduled_Removal.groupby(df.Aircraft_ID).sum()
    high = (df.Fault_Severity == "High").groupby(df.Aircraft_ID).sum()
    metrics = pd.DataFrame({"defectRate": 1000 * n / fh, "tdr": 100 * tech / departures,
                            "urr": 1000 * removals / fh, "highPct": 100 * high / n})
    if "Safety_Score" in df:
        metrics["safetyGap"] = 100 - g.Safety_Score.mean()
    metrics = metrics[departures >= MIN_ACTIVE_MONTHS * dep]
    pct = (metrics.rank(method="average") - 1) / (len(metrics) - 1) * 100
    w = pd.Series({k: v for k, v in HEALTH_WEIGHTS.items() if k in metrics})
    score = 100 - (pct[w.index] * w).sum(axis=1) / w.sum()
    return {str(k): float(v) for k, v in score.items()}


def main(csv_path, out_path):
    df = load(csv_path)
    g = df.groupby("Aircraft_ID")
    tech = df.Is_Technical_Delay & (df.Delay_Minutes > 15)
    fleet_fh = float((g.Cumulative_Flight_Hours.max() - g.Cumulative_Flight_Hours.min()).sum())
    active_months = (g.Event_Date.max() - g.Event_Date.min()).dt.days / DAYS_PER_MONTH
    departures = float((g.Fleet_Avg_Monthly_Departures.first() * active_months).sum())
    removals = df.Unscheduled_Removal.sum()

    months = pd.period_range(df.Event_Date.min(), df.Event_Date.max(), freq="M")
    fh_m = monthly_fleet_fh(df, months)
    ev_m = df.groupby([df.Event_Date.dt.to_period("M"), "ATA_Chapter"]).size().unstack(fill_value=0).reindex(months, fill_value=0)
    ucl = {}
    for ata in ev_m.columns:
        rate = ev_m[ata].values / np.where(fh_m > 0, fh_m, np.nan) * 1000
        ok = (fh_m >= MIN_MONTH_FH)
        base = ok & np.array([str(m).startswith(BASE_YEAR) for m in months])
        mu, sd = np.nanmean(rate[base]), np.nanstd(rate[base], ddof=1)
        ucl[int(ata)] = {"mu": mu, "sigma": sd, "ucl2": mu + 2 * sd, "ucl3": mu + 3 * sd,
                         "breaches_k3": [str(m) for m, r, o in zip(months, rate, ok) if o and r > mu + 3 * sd]}

    golden = {
        "events": len(df), "aircraft": int(df.Aircraft_ID.nunique()),
        "fleet_fh": fleet_fh, "fleet_fc": float((g.Cumulative_Flight_Cycles.max() - g.Cumulative_Flight_Cycles.min()).sum()),
        "departures": departures, "tech_delays": int(tech.sum()),
        "dispatch_reliability_pct": 100 * (1 - tech.sum() / departures),
        "tech_delay_rate_per_100": 100 * tech.sum() / departures,
        "unscheduled_removals": int(removals),
        "urr_per_1000fh": 1000 * removals / fleet_fh, "mtbur_fh": fleet_fh / removals,
        "mtbur_by_pn": {k: fleet_fh / v for k, v in df[df.Unscheduled_Removal].Part_Number.value_counts().items()},
        "repetitive_5d": repetitive(df, max_days=5), "repetitive_10cyc": repetitive(df, max_cycles=10),
        "near_repetitive_30d": repetitive(df, max_days=30),
        "pareto_ata": {int(k): int(v) for k, v in df.ATA_Chapter.value_counts().items()},
        "tech_delay_minutes": float(df[tech].Delay_Minutes.sum()),
        "tech_delay_minutes_by_ata": {int(k): float(v) for k, v in df[tech].groupby("ATA_Chapter").Delay_Minutes.sum().items()},
        "weibull_by_pn": weibull_by_pn(df),
        "fleet_quality": fleet_quality(df, fleet_fh),
        "quality_safety_monthly": quality_monthly(df, "Safety_Score"),
        "quality_inspection_monthly": quality_monthly(df, "Inspection_Score"),
        "health_index": health_index(df),
        "mttr_by_pn": ({k: float(v) for k, v in df.groupby("Part_Number").Repair_Time_Hours.mean().items()}
                       if "Repair_Time_Hours" in df.columns else {}),
        "monthly_fleet_fh": {str(m): float(v) for m, v in zip(months, fh_m)},
        "ucl_by_ata": ucl,
        "info_alt_departures": {"33_months_all_aircraft": float(g.Fleet_Avg_Monthly_Departures.first().sum() * 33)},
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(golden, indent=2, default=float), encoding="utf-8")
    for k in ["departures", "dispatch_reliability_pct", "tech_delay_rate_per_100", "urr_per_1000fh", "mtbur_fh",
              "repetitive_5d", "repetitive_10cyc", "near_repetitive_30d"]:
        print(k, golden[k])
    print("pareto", golden["pareto_ata"])
    print("UCL k=3 breaches", {a: v["breaches_k3"] for a, v in ucl.items()})
    print("written", out_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "aviation_fault_maintenance_dataset_enriched.csv",
         sys.argv[2] if len(sys.argv) > 2 else ".tmp/kpi_golden.json")
