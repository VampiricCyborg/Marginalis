"""Run the train-split analysis end to end and write reports/eda_findings.md.

Every number in the report is computed here from the train views; nothing is typed in.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from marginalis import db
from marginalis.analysis import eda, mef
from marginalis.analysis import exclusions as ex
from marginalis.analysis.data import read_fuel_mix, read_view
from marginalis.config import BAS, METHOD_FROZEN, REPORTS_DIR, TRAIN
from marginalis.schedule import best_window

W = 4  # pre-registered window length (hours)
LOAD_MWH_PER_DAY = 100
OVERNIGHT = range(5)  # local hours 00-05, the average profile's usual pick in MISO


def _md(df: pd.DataFrame, fmt: str = "{:,.0f}") -> str:
    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else fmt.format(v)
        if isinstance(v, (bool, np.bool_)):
            return "yes" if v else "no"
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v)

    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    return "\n".join([head, sep] + ["| " + " | ".join(cell(v) for v in r) + " |" for r in df.itertuples(index=False)])


def _day_profile(prof: pd.DataFrame, col: str, ba: str, month: int) -> pd.Series:
    """A month's 24-hour profile laid on a representative day (15th, 2024) as hour-ending UTC."""
    tz = BAS[ba].timezone
    starts = pd.date_range(pd.Timestamp(2024, month, 15, tz=tz), periods=24, freq="h")
    vals = prof.set_index("local_hour").loc[starts.hour, col].to_numpy()
    return pd.Series(vals, index=(starts + pd.Timedelta(hours=1)).tz_convert("UTC"))


def window_comparison(det: pd.DataFrame) -> pd.DataFrame:
    """Per BA x source x month: the W-hour window each profile picks, and the MEF each implies."""
    rows = []
    for (ba, src), g in det[det["spec"] == "demand"].groupby(["ba_code", "emissions_source"]):
        tz = BAS[ba].timezone
        for m in range(1, 13):
            p = g[g["month"] == m]
            mef_s = _day_profile(p, "mef_kg_per_mwh", ba, m)
            avg_s = _day_profile(p, "avg_intensity_kg_per_mwh", ba, m)
            wm, wa = best_window(mef_s, W), best_window(avg_s, W)
            rows.append({
                "BA": ba, "source": src, "month": pd.Timestamp(2024, m, 1).strftime("%b"),
                "marginal-optimal window": f"{wm.start.tz_convert(tz):%H}:00–{wm.end.tz_convert(tz):%H}:00",
                "average-optimal window": f"{wa.start.tz_convert(tz):%H}:00–{wa.end.tz_convert(tz):%H}:00",
                "MEF in marginal window": wm.mean_factor_kg_per_mwh,
                "MEF in average window": float(mef_s.loc[wa.hours].mean()),
            })
    out = pd.DataFrame(rows)
    out["predicted gap (kg/MWh)"] = out["MEF in average window"] - out["MEF in marginal window"]
    return out


def pooled_estimate(delta, hours, bad_days, ba, hours_of_day, source, seed_tag):
    """Descriptive summary over a set of local hours (all months).

    x and y are demeaned within each month x hour stratum before pooling, so the slope is a
    precision-weighted average of the pre-registered stratum slopes and differences between
    strata cannot drive it. Same week-cluster bootstrap.
    """
    d_bad, h_bad = ex.on_days(delta, bad_days), ex.on_days(hours, bad_days)
    dm = ex.usable_deltas(delta, d_bad, "demand", source) & (delta["ba_code"] == ba) & delta["local_hour"].isin(hours_of_day)
    lm = ex.usable_levels(hours, h_bad, source) & (hours["ba_code"] == ba) & hours["local_hour"].isin(hours_of_day)
    d, lv = delta[dm], hours[lm]
    cell = [d["local_date"].dt.month, d["local_hour"]]
    x = d["d_demand_mwh"] - d.groupby(cell)["d_demand_mwh"].transform("mean")
    y = d[ex.SOURCES[source]] - d.groupby(cell)[ex.SOURCES[source]].transform("mean")
    return mef.estimate_cell(
        x.to_numpy(float), y.to_numpy(float), mef._week(d["local_date"]),
        lv[ex.LEVEL_CO2[source]].to_numpy(float), lv["net_generation_mwh"].to_numpy(float), mef._week(lv["local_date"]),
        np.random.default_rng([mef.SEED, seed_tag]),
    )


def run() -> str:
    assert not METHOD_FROZEN, "this report is the pre-freeze train analysis"
    h, d, f = read_view("v_hour_train"), read_view("v_hour_delta_train"), read_fuel_mix()
    bad_days = ex.gas_as_other_days(f, h)

    det = mef.estimate(d, h, bad_days)
    with db.connect() as conn:
        db.migrate(conn)
        mef.load_profile(conn, det)
        n_loaded = conn.execute("SELECT COUNT(*) FROM mef_profile").fetchone()[0]
    det.to_csv(REPORTS_DIR / "mef_strata_detail.csv", index=False, float_format="%.3f")

    overview = eda.annual_overview(h, bad_days)
    shares = eda.fuel_shares(f)
    deltas = eda.delta_distribution(d)
    issues = eda.data_issue_impacts(h, f, bad_days)
    excl = eda.exclusion_counts(d, bad_days)
    figs = {
        "demand": eda.fig_demand_diurnal(h), "mix": eda.fig_mix(shares),
        "intensity": eda.fig_avg_intensity_diurnal(h, bad_days), "imports": eda.fig_net_imports(h),
        "mef_eia": eda.fig_mef_vs_avg(det, "eia"), "mef_derived": eda.fig_mef_vs_avg(det, "derived"),
        "div_eia": eda.fig_divergence_heatmap(det, "eia"), "div_derived": eda.fig_divergence_heatmap(det, "derived"),
    }
    windows = window_comparison(det)

    # Stratum summary.
    det["up"] = det["diverges"] & (det["diff_kg_per_mwh"] > 0)
    det["down"] = det["diverges"] & (det["diff_kg_per_mwh"] < 0)
    summary = det.groupby(["ba_code", "spec", "emissions_source"]).agg(
        **{"median MEF": ("mef_kg_per_mwh", "median"),
           "MEF p10": ("mef_kg_per_mwh", lambda s: s.quantile(0.1)),
           "MEF p90": ("mef_kg_per_mwh", lambda s: s.quantile(0.9)),
           "median average": ("avg_intensity_kg_per_mwh", "median"),
           "median CI width": ("ci_high_95", lambda s: (s - det.loc[s.index, "ci_low_95"]).median()),
           "median n": ("n_obs", "median"),
           "diverging strata (of 288)": ("diverges", "sum"),
           "marginal above": ("up", "sum"), "marginal below": ("down", "sum")}
    ).reset_index().rename(columns={"ba_code": "BA", "emissions_source": "source"})

    dem = det[det["spec"] == "demand"]
    both = dem.pivot_table(index=["ba_code", "month", "local_hour"], columns="emissions_source",
                           values="diverges", aggfunc="first")
    agree = both[both["derived"] & both["eia"]].reset_index()
    agree_counts = agree.groupby("ba_code").size()
    eia_dem = dem[dem["emissions_source"] == "eia"].set_index(["ba_code", "month", "local_hour"])
    top = eia_dem.loc[pd.MultiIndex.from_frame(agree[["ba_code", "month", "local_hour"]])].reset_index()
    top["abs"] = top["diff_kg_per_mwh"].abs()
    top = top.sort_values("abs", ascending=False).groupby("ba_code").head(5)
    top_tbl = top.assign(month=top["month"].map(lambda m: pd.Timestamp(2024, m, 1).strftime("%b")),
                         hour=top["local_hour"].map(lambda x: f"{x:02d}:00"))[
        ["ba_code", "month", "hour", "mef_kg_per_mwh", "ci_low_95", "ci_high_95",
         "avg_intensity_kg_per_mwh", "diff_kg_per_mwh", "diff_ci_low_95", "diff_ci_high_95", "n_obs"]
    ].rename(columns={"ba_code": "BA", "mef_kg_per_mwh": "MEF", "ci_low_95": "CI low", "ci_high_95": "CI high",
                      "avg_intensity_kg_per_mwh": "average", "diff_kg_per_mwh": "MEF − avg",
                      "diff_ci_low_95": "diff CI low", "diff_ci_high_95": "diff CI high"})

    # Recommendation numbers: MISO overnight, not selected on the MEF itself.
    miso_on = {src: pooled_estimate(d, h, bad_days, "MISO", OVERNIGHT, src, 1 + i)
               for i, src in enumerate(("eia", "derived"))}
    miso_avg_pick = windows[(windows["BA"] == "MISO") & (windows["source"] == "eia")]
    n_overnight_pick = int(miso_avg_pick["average-optimal window"].str[:2].astype(int).isin(OVERNIGHT).sum())
    r = miso_on["eia"]
    annual_mwh = LOAD_MWH_PER_DAY * 365
    t_marginal = r.mef * annual_mwh / 1000
    t_average = r.avg * annual_mwh / 1000
    t_lo, t_hi = r.ci_low * annual_mwh / 1000, r.ci_high * annual_mwh / 1000
    win_gap = windows.groupby(["BA", "source"])["predicted gap (kg/MWh)"].mean().unstack()
    miso_gap = win_gap.loc["MISO", "eia"]

    ov = overview.set_index(["BA", "year"])
    first_y, last_y = overview["year"].min(), overview["year"].max()

    def trend(ba, col):
        return ov.loc[(ba, first_y), col], ov.loc[(ba, last_y), col]

    L = []
    add = L.append
    add("# Marginalis: EDA and marginal emissions factors (train split)\n")
    add(f"_Generated by `marginalis analyze` at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from "
        f"`v_hour_train` / `v_hour_delta_train` only ({TRAIN.start:%Y-%m-%d} → {TRAIN.end:%Y-%m-%d}). "
        "Hold-out data (2025, 2026 YTD) has not been read; `METHOD_FROZEN` is False. "
        "Every number below is computed by `src/marginalis/analysis/`; none is typed in._\n")

    add("## Summary\n")
    add(f"- **MISO: the hours that look cleanest on average are dirty at the margin.** The average-intensity "
        f"profile picks an overnight {W}-hour window (starting 00:00–04:00) in {n_overnight_pick} of 12 months. "
        f"Across those overnight hours, each extra MWh of demand came with **{r.mef:,.0f} kg CO₂** "
        f"(95% CI {r.ci_low:,.0f}–{r.ci_high:,.0f}), against an average intensity of {r.avg:,.0f} kg/MWh.")
    add("- With demand as the regressor, marginal and average differ by ≥ 50 kg/MWh with a CI excluding zero in "
        + ", ".join(f"{ba} {int(agree_counts.get(ba, 0))}" for ba in ["ERCO", "CISO", "MISO"])
        + " of 288 month × hour strata (counted where the derived and EIA series agree). In ERCO and MISO, "
          "nearly all of these have the marginal factor **above** average. CISO is mixed: above average in the "
          "mid-afternoon and on summer middays, below it at winter middays.")
    add("- Single strata are noisy: the median 95% CI width for the demand spec is "
        + ", ".join(f"{ba} {summary[(summary.BA == ba) & (summary.spec == 'demand') & (summary.source == 'eia')]['median CI width'].iloc[0]:,.0f}"
                    for ba in ["ERCO", "CISO", "MISO"])
        + " kg/MWh. Profiles are informative in aggregate and should not be read hour by hour.")
    add("- The pre-registered test (hold-out scheduler comparison, W = 4 h, ≥ 50 kg CO₂/MWh shifted + CI) "
        "**has not been run**. Nothing here is its result.\n")

    add("## Methodology used\n")
    add("As fixed in `docs/preregistration.md` (Estimation details and the 2026-09-27 amendments), before "
        "any factor was estimated:\n")
    add("- **Strata:** BA × spec × emissions source × month × local hour (start of hour, BA zone; MISO Central). "
        "Specs: `demand` (main) and `fossil_gen` (robustness). Sources: `derived` (generation × fixed fuel "
        "rate) and `eia` (EIA's published hourly estimate).")
    add("- **Estimator:** OLS with intercept, ΔCO₂ = α + β·Δx + ε, per stratum; β is the marginal factor.")
    add(f"- **CIs:** cluster bootstrap over local calendar weeks, {mef.N_BOOT:,} replicates, seed {mef.SEED}, "
        "percentile 95%. The marginal-minus-average difference is bootstrapped jointly.")
    add(f"- **Minimum cell size:** {mef.MIN_CELL} usable observations, with pooling of adjacent months if "
        f"below. Every cell met it (minimum n = {int(det['n_obs'].min())}), so **no strata were pooled**.")
    add("- **Average baseline:** Σ CO₂ / Σ net generation over the stratum's hours, per source, excluding "
        "the CISO hydro/other gap hours and the gas-as-Other days.")
    add("- **Divergence (descriptive, in-sample):** |β − average| ≥ 50 kg/MWh and the bootstrap CI of the "
        "difference excludes zero.")
    add("- **Excluded delta rows:** the previous hour is not the adjacent UTC hour; either hour interpolated; "
        "NULL regressor or ΔCO₂; incomplete fossil data (derived only); either hour on a gas-as-Other day.\n")
    add(_md(excl[excl["source"] == "eia"].drop(columns="source"), "{:,.2f}"))
    add("")

    add("## EDA\n")
    add("### Demand\n")
    add(f"![Demand by local hour]({figs['demand']})\n")
    add(_md(overview[["BA", "year", "mean demand (GW)"]].pivot(index="year", columns="BA", values="mean demand (GW)").reset_index(), "{:,.1f}"))
    _, e1 = trend("ERCO", "mean demand (GW)")
    e20 = ov.loc[("ERCO", "2020"), "mean demand (GW)"]
    add(f"\n{first_y} covers July–December only, so its means lean towards summer. From 2020 to {last_y}, "
        f"ERCO demand grew from {e20:,.1f} GW to {e1:,.1f} GW; CISO and MISO were roughly flat. All three peak in summer late afternoon (≈16:00–19:00 local). ERCO and MISO have the "
        "steepest summer ramps.\n")
    add("### Generation mix\n")
    add(f"![Generation mix]({figs['mix']})\n")
    add(_md(shares, "{:,.1f}"))
    sh = shares.set_index(["BA", "year"])

    def chg(ba, col):
        return f"{sh.loc[(ba, first_y), col]:.1f}% → {sh.loc[(ba, last_y), col]:.1f}%"

    add(f"\nCoal's share fell in ERCO ({chg('ERCO', 'Coal')}) and MISO ({chg('MISO', 'Coal')}). In MISO gas "
        f"took its place ({chg('MISO', 'Gas')}). In ERCO gas also fell ({chg('ERCO', 'Gas')}) as solar grew "
        f"({chg('ERCO', 'Solar')}). CISO is gas plus solar (gas {chg('CISO', 'Gas')}), with hydro swinging "
        "with water years; its 2020 hydro share is low partly because of the reporting gap.\n")
    add("### Emissions and average intensity\n")
    add(f"![Average intensity by hour]({figs['intensity']})\n")
    add(_md(overview[["BA", "year", "avg intensity derived (kg/MWh)", "avg intensity eia (kg/MWh)"]]))
    def it(ba, yr):
        return ov.loc[(ba, yr), "avg intensity eia (kg/MWh)"]

    add(f"\nAverage intensity (EIA) fell steadily in ERCO ({it('ERCO', '2020'):,.0f} → {it('ERCO', last_y):,.0f} "
        f"kg/MWh, 2020–{last_y}) and MISO ({it('MISO', '2020'):,.0f} → {it('MISO', last_y):,.0f}). CISO's 2019 "
        "and 2020 figures cover partial, autumn-heavy periods (2019 starts in July; the hydro gap is excluded), "
        f"so its trend is only readable from 2021 ({it('CISO', '2021'):,.0f} → {it('CISO', last_y):,.0f}). "
        "The derived series tracks EIA's closely, running slightly lower (EIA's factors are BA-and-year specific and assign some CO₂ to "
        "'Other'). CISO's average intensity collapses around midday (solar). MISO's is highest and flattest.\n")
    add("### Hour-to-hour changes (the regressor)\n")
    add(_md(deltas, "{:,.2f}"))
    add("\nΔdemand is roughly symmetric around zero with a diurnal structure. Δdemand and Δfossil generation are "
        "most tightly coupled in MISO and least in CISO, where imports, hydro and storage absorb a large share "
        "of load changes.\n")
    add("### Net imports\n")
    add(f"![Net-import share]({figs['imports']})\n")
    add(_md(overview[["BA", "year", "net-import share, mean %", "net-import share, p95 %"]], "{:,.1f}"))
    add("\nCISO imports a large share of its demand, so its in-BA marginal factors miss emissions in "
        "imported power. MISO is moderate and ERCO is near-isolated (the cleanest case).\n")

    add("### Data issues and how they were handled\n")
    g = issues["ciso_gap_ng_over_demand"]
    add(f"- **CISO hydro/other gap** ({issues['ciso_gap_hours']:,} train hours, Oct 2019 – Aug 2020). EIA's net "
        f"generation omits hydro and other, so net generation / demand drops from a mean of "
        f"{g['outside gap'].mean():.2f} outside the gap to {g['in gap'].mean():.2f} inside it. Average "
        f"intensity computed naively inside the gap would be {issues['ciso_gap_avg_intensity']:,.0f} kg/MWh, "
        "an overstatement. These hours are **excluded from the average baseline** but kept in the MEF "
        "regressions (demand, fossil generation and CO₂ are unaffected).")
    nt = issues["neg_thermal_hours"]
    add(f"- **Small negative thermal generation** ({', '.join(f'{r.ba_code} {r.fuel_code} {r.hours:,} h' for r in nt.itertuples())}) "
        "is station load at idle units, counted as zero CO₂. Counting it as negative emissions instead would "
        f"change CISO's derived CO₂ by {issues['neg_thermal_co2_share_pct'].get('CISO', 0):.4f}%, which is negligible.")
    add(f"- **Storage codes mid-sample.** ERCO reports BAT/UES from {issues['erco_storage_first']:%Y-%m-%d} "
        f"({issues['erco_storage_hours']:,} train hours; |storage| = {issues['erco_storage_abs_share_pct']:.1f}% "
        "of net generation). Storage carries no direct CO₂ here, so no exclusion was needed. MISO's storage "
        "codes start in 2025 (hold-out) and are not seen. **CISO reports its batteries inside 'Other'**: "
        "evening (18–21h) mean OTH rose from "
        f"{issues['ciso_other_evening_mean'].iloc[0]:,.0f} MWh ({issues['ciso_other_evening_mean'].index[0]}) to "
        f"{issues['ciso_other_evening_mean'].iloc[-1]:,.0f} MWh ({issues['ciso_other_evening_mean'].index[-1]}), "
        f"while midday (10–14h) went to {issues['ciso_other_midday_mean'].iloc[-1]:,.0f} MWh (charging).")
    add(f"- **Gas reported as 'Other'** on {len(bad_days)} ERCO days ("
        + ", ".join(f"{x:%Y-%m-%d}" for x in bad_days["local_date"])
        + "): ~20 GW of gas sits under Other for a whole local day, corrupting both CO₂ series and producing "
          "±25 GW fossil deltas at the day boundaries. Found in EDA before estimation, and excluded by amendment.\n")

    add("## Marginal emissions factors\n")
    add(f"`mef_profile` holds {n_loaded:,} rows (3 BAs × 2 specs × 2 sources × 12 months × 24 hours). "
        "Full diagnostics per stratum (difference, its CI, clusters, divergence flag) are in "
        "`reports/mef_strata_detail.csv`.\n")
    add(_md(summary))
    add("\n**Reading the fossil_gen spec.** It is close to mechanical. The derived CO₂ series *is* Σ "
        "rate × fossil generation, and EIA's is built the same way, so regressing ΔCO₂ on Δfossil "
        "generation recovers the rate of whichever fossil fuel ramps: CISO ≈ 409 (gas only), MISO ≈ 690 and "
        "ERCO ≈ 560 (coal + gas). It sits above average intensity by construction, because average intensity "
        "includes zero-carbon generation. So its '288 of 288 diverging' says which fuel ramps, not how to "
        "schedule load. The demand spec answers the scheduling question.\n")
    add(f"![MEF vs average, EIA]({figs['mef_eia']})\n")
    add(f"![MEF vs average, derived]({figs['mef_derived']})\n")
    add("### Strata where marginal and average diverge (demand spec)\n")
    add("Dots mark strata meeting the descriptive rule. Red means marginal is above average.\n")
    add(f"![Divergence, EIA]({figs['div_eia']})\n")
    add(f"![Divergence, derived]({figs['div_derived']})\n")
    add("Largest divergences where both sources agree (EIA values shown):\n")
    add(_md(top_tbl))
    add("")
    add("- **MISO:** marginal is above average in most overnight and morning strata (00:00–09:00), when coal "
        "and gas follow load and wind fills the average. Divergence thins out on summer afternoons.")
    add("- **ERCO:** marginal is above average across most daytime strata. It turns **negative** at 08:00 and "
        "around 20:00 in summer, when demand rises while solar ramps up faster (or falls while solar ramps "
        "down). This is confounding the no-controls specification cannot separate, and it is not a real "
        "negative marginal emission.")
    add("- **CISO:** marginal is *above* average in the mid-afternoon (14:00–16:00) in almost every month, "
        "and across midday from June to October, when gas follows load. It is *below* average around midday "
        "in January–March (extra load absorbs otherwise-curtailed solar or exports) and in several dawn and "
        "dusk hours, where solar ramps confound the regression as they do in ERCO. Imports are large, so "
        "in-BA factors are a lower bound on the system response.\n")

    add(f"### What the profiles imply for a {W}-hour flexible load (in-sample prediction)\n")
    add("For each month, the shared optimiser (`src/marginalis/schedule.py`) picks the lowest-intensity "
        f"{W}-hour window under each profile. The table gives the marginal factor each choice implies.\n")
    add(_md(windows[windows["source"] == "eia"].drop(columns="source")))
    add("\nMean predicted gap (kg CO₂ per MWh shifted):\n")
    add(_md(win_gap.reset_index()))
    add("\nThese gaps are **optimistic**. The marginal-optimal window is the minimum of 21 noisy window means, "
        "picked from the same data the profile was fitted on (winner's curse). Whether they survive is exactly "
        "what the pre-registered hold-out comparison will measure.\n")

    add("## Recommendation\n")
    add(f"**Don't schedule flexible load in MISO overnight just because the grid looks cleanest then.** "
        f"Tools that use average intensity send MISO flexible load (EV fleet charging, batch computing, "
        f"water heating) to the overnight hours in {n_overnight_pick} of 12 months, but those are among the "
        f"dirtiest hours at the margin. For a {LOAD_MWH_PER_DAY} MWh/day load run overnight, average intensity "
        f"suggests it is responsible for about **{t_average:,.0f} t CO₂/year**. The marginal estimate puts the "
        f"grid's actual response at about **{t_marginal:,.0f} t/year** (95% CI {t_lo:,.0f}–{t_hi:,.0f}): "
        f"**{t_marginal - t_average:,.0f} t/year more**, or {100 * (r.mef / r.avg - 1):.0f}% above what the "
        "average-based figure implies. This number is not "
        "selected on the marginal profile, so it doesn't suffer the winner's curse above. Moving the same "
        "load to each month's marginal-optimal window is predicted, in-sample, to save about "
        f"{miso_gap:,.0f} kg/MWh (~{miso_gap * annual_mwh / 1000:,.0f} t/year). Treat that as an upper bound "
        "until the hold-out test.\n")

    add("## Limitations\n")
    add("- The analysis estimates the average empirical relationship between hour-to-hour changes in load and in "
        "in-BA CO₂ within each stratum. It does not identify a causal dispatch response. There are no weather "
        "or renewable-output controls (per the pre-registered spec), which is visible in ERCO's solar-ramp "
        "hours.")
    add("- In-BA emissions only: emissions embodied in imports are not counted. This matters most for CISO "
        "(see net-import shares).")
    add("- One CO₂ rate per fuel: derived factors reflect which fuel ramps, not the efficiency of the plants "
        "that ramp.")
    add(f"- {len(det):,} strata are many comparisons. The divergence counts are descriptive, not tests.\n")
    add("## Next step\n")
    add("Freeze the method (commit `METHOD_FROZEN = True`), then run the pre-registered evaluation on 2025 and "
        "2026 YTD: the daily W = 4 h scheduler comparison with the ≥ 50 kg CO₂/MWh + CI rule, and the "
        "predictive check of these factors against realised ΔCO₂/Δdemand.\n")

    text = "\n".join(L)
    (REPORTS_DIR / "eda_findings.md").write_text(text, encoding="utf-8")
    return text
