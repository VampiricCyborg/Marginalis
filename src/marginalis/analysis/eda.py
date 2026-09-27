"""Descriptive EDA on the train split: tables (DataFrames) and figures (PNG)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import logging

logging.getLogger("matplotlib").setLevel(logging.WARNING)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from marginalis.analysis import exclusions as ex
from marginalis.config import REPORTS_DIR
from marginalis.emission_factors import fuel_factors

FIG_DIR = REPORTS_DIR / "figures"
BAS = ["ERCO", "CISO", "MISO"]

# Palette (validated with the dataviz validator, light surface).
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MARGINAL, AVERAGE = "#2a78d6", "#eb6834"  # reserved: marginal = blue, average = orange
SEASON_COLORS = {"Winter (DJF)": "#1baf7a", "Spring (MAM)": "#eda100",
                 "Summer (JJA)": "#e87ba4", "Autumn (SON)": "#008300"}
FUEL_GROUPS = {"Coal": ["COL"], "Gas": ["NG"], "Nuclear": ["NUC"], "Hydro": ["WAT"],
               "Wind": ["WND"], "Solar": ["SUN"], "Other + storage": ["OIL", "OTH", "BAT", "UES", "SNB", "PS", "OES", "WNB", "GEO", "UNK"]}
FUEL_COLORS = ["#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948", "#a3a29d"]
SEASON = {12: "Winter (DJF)", 1: "Winter (DJF)", 2: "Winter (DJF)", 3: "Spring (MAM)", 4: "Spring (MAM)",
          5: "Spring (MAM)", 6: "Summer (JJA)", 7: "Summer (JJA)", 8: "Summer (JJA)",
          9: "Autumn (SON)", 10: "Autumn (SON)", 11: "Autumn (SON)"}


def _style(ax, title=None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=INK, fontsize=10, loc="left")


def _fig(ncols, nrows=1, w=4.2, h=3.0):
    fig, axes = plt.subplots(nrows, ncols, figsize=(w * ncols, h * nrows), squeeze=False,
                             facecolor=SURFACE)
    return fig, axes


def _save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return f"figures/{name}"


def _prep(h: pd.DataFrame) -> pd.DataFrame:
    h = h.copy()
    h["year"] = h["local_start"].dt.year
    h["month"] = h["local_start"].dt.month
    h["season"] = h["month"].map(SEASON)
    return h


# --- Tables -----------------------------------------------------------------------------

def annual_overview(h: pd.DataFrame, bad_days: pd.DataFrame) -> pd.DataFrame:
    """Mean demand, avg intensity (both sources) and net-import share by BA-year."""
    h = _prep(h)
    rows = []
    for (ba, yr), g in h.groupby(["ba_code", "year"]):
        row = {"BA": ba, "year": str(yr), "mean demand (GW)": g["demand_mwh"].mean() / 1000,
               "net-import share, mean %": 100 * g["net_import_share"].mean(),
               "net-import share, p95 %": 100 * g["net_import_share"].quantile(0.95)}
        for src in ("derived", "eia"):
            ok = ex.usable_levels(g, ex.on_days(g, bad_days), src)
            row[f"avg intensity {src} (kg/MWh)"] = (
                g.loc[ok, ex.LEVEL_CO2[src]].sum() / g.loc[ok, "net_generation_mwh"].sum()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def fuel_shares(f: pd.DataFrame) -> pd.DataFrame:
    """Annual generation shares (%) by fuel group; negatives (storage charging) excluded."""
    f = f.copy()
    f["year"] = f["local_date"].dt.year
    grp = {code: name for name, codes in FUEL_GROUPS.items() for code in codes}
    f["group"] = f["fuel_code"].map(grp)
    s = f.assign(g=f["generation_mwh"].clip(lower=0)).groupby(["ba_code", "year", "group"])["g"].sum()
    s = (100 * s / s.groupby(level=[0, 1]).transform("sum")).unstack("group").fillna(0)
    return s[[c for c in FUEL_GROUPS if c in s.columns]].reset_index().rename(
        columns={"ba_code": "BA"}).assign(year=lambda d: d["year"].astype(str))


def delta_distribution(d: pd.DataFrame) -> pd.DataFrame:
    q = d.groupby("ba_code")["d_demand_mwh"].quantile([0.01, 0.05, 0.5, 0.95, 0.99]).unstack()
    q.columns = [f"p{int(c * 100)}" for c in q.columns]
    q.insert(0, "sd", d.groupby("ba_code")["d_demand_mwh"].std())
    q["corr(Δdemand, Δfossil)"] = d.groupby("ba_code").apply(
        lambda x: x["d_demand_mwh"].corr(x["d_fossil_generation_mwh"]), include_groups=False)
    return q.reset_index().rename(columns={"ba_code": "BA"})


def data_issue_impacts(h: pd.DataFrame, f: pd.DataFrame, bad_days: pd.DataFrame) -> dict:
    """Magnitudes of the documented data issues, for the write-up."""
    out = {}
    c = _prep(h[h["ba_code"] == "CISO"])
    gap = (c["ts_utc"] > ex.CISO_HYDRO_GAP[0]) & (c["ts_utc"] <= ex.CISO_HYDRO_GAP[1])
    ratio = c.groupby([gap.rename("in_gap"), "month"]).apply(
        lambda x: x["net_generation_mwh"].sum() / x["demand_mwh"].sum(), include_groups=False
    ).unstack(0)
    out["ciso_gap_ng_over_demand"] = ratio.rename(columns={False: "outside gap", True: "in gap"})
    out["ciso_gap_hours"] = int(gap.sum())
    naive = c.loc[gap, "co2_kg_derived"].sum() / c.loc[gap, "net_generation_mwh"].sum()
    out["ciso_gap_avg_intensity"] = naive
    rates = fuel_factors()
    neg = f[f["fuel_code"].isin(rates) & (f["generation_mwh"] < 0)]
    out["neg_thermal_hours"] = neg.groupby(["ba_code", "fuel_code"]).size().rename("hours").reset_index()
    neg_co2 = (neg["generation_mwh"] * neg["fuel_code"].map(rates)).groupby(neg["ba_code"]).sum()
    out["neg_thermal_co2_share_pct"] = (100 * neg_co2 / h.groupby("ba_code")["co2_kg_derived"].sum()).dropna()
    st = f[(f["ba_code"] == "ERCO") & f["fuel_code"].isin(["BAT", "UES"])]
    since = st["ts_utc"].min()
    ng = h[(h["ba_code"] == "ERCO") & (h["ts_utc"] >= since)]["net_generation_mwh"].sum()
    out["erco_storage_first"] = since
    out["erco_storage_abs_share_pct"] = 100 * st["generation_mwh"].abs().sum() / ng
    out["erco_storage_hours"] = int(st["ts_utc"].nunique())
    out["gas_as_other_days"] = bad_days
    c_oth = f[(f["ba_code"] == "CISO") & (f["fuel_code"] == "OTH")].copy()
    c_oth["year"] = c_oth["local_date"].dt.year
    out["ciso_other_evening_mean"] = c_oth[c_oth["local_hour"].between(18, 21)].groupby("year")["generation_mwh"].mean()
    out["ciso_other_midday_mean"] = c_oth[c_oth["local_hour"].between(10, 14)].groupby("year")["generation_mwh"].mean()
    return out


def exclusion_counts(d: pd.DataFrame, bad_days: pd.DataFrame) -> pd.DataFrame:
    bad = ex.on_days(d, bad_days)
    rows = []
    for ba, g in d.groupby("ba_code"):
        for spec in ex.SPECS:
            for src in ex.SOURCES:
                ok = ex.usable_deltas(g, bad.loc[g.index], spec, src)
                rows.append({"BA": ba, "spec": spec, "source": src, "delta rows": len(g),
                             "usable": int(ok.sum()), "excluded": int((~ok).sum()),
                             "excluded %": 100 * (~ok).mean(),
                             "on gas-as-Other days": int((bad.loc[g.index] & ~ok).sum())})
    return pd.DataFrame(rows)


# --- Figures ----------------------------------------------------------------------------

def fig_demand_diurnal(h: pd.DataFrame) -> str:
    h = _prep(h)
    fig, axes = _fig(3)
    for ax, ba in zip(axes[0], BAS):
        g = h[h["ba_code"] == ba].groupby(["season", "local_hour"])["demand_mwh"].mean().unstack(0) / 1000
        for season, color in SEASON_COLORS.items():
            ax.plot(g.index, g[season], color=color, linewidth=2, label=season)
        _style(ax, f"{ba}: mean demand by local hour (GW)")
        ax.set_xticks(range(0, 24, 3))
    axes[0][0].legend(frameon=False, fontsize=7, labelcolor=INK2)
    return _save(fig, "01_demand_diurnal.png")


def fig_mix(shares: pd.DataFrame) -> str:
    fig, axes = _fig(3)
    groups = [c for c in FUEL_GROUPS if c in shares.columns]
    for ax, ba in zip(axes[0], BAS):
        s = shares[shares["BA"] == ba].set_index("year")[groups]
        bottom = np.zeros(len(s))
        for name, color in zip(groups, FUEL_COLORS):
            ax.bar(s.index, s[name], bottom=bottom, color=color, width=0.7, label=name,
                   edgecolor=SURFACE, linewidth=1)
            bottom += s[name].to_numpy()
        _style(ax, f"{ba}: generation share by fuel (%)")
        ax.set_ylim(0, 100)
    axes[0][2].legend(frameon=False, fontsize=7, labelcolor=INK2, loc="center left", bbox_to_anchor=(1, 0.5))
    return _save(fig, "02_generation_mix.png")


def fig_avg_intensity_diurnal(h: pd.DataFrame, bad_days: pd.DataFrame) -> str:
    h = _prep(h)
    h = h[ex.usable_levels(h, ex.on_days(h, bad_days), "eia")]
    fig, axes = _fig(3)
    for ax, ba in zip(axes[0], BAS):
        g = h[h["ba_code"] == ba].groupby(["season", "local_hour"])[["co2_kg_eia_generated", "net_generation_mwh"]].sum()
        g = (g["co2_kg_eia_generated"] / g["net_generation_mwh"]).unstack(0)
        for season, color in SEASON_COLORS.items():
            ax.plot(g.index, g[season], color=color, linewidth=2, label=season)
        _style(ax, f"{ba}: average intensity, EIA (kg/MWh)")
        ax.set_xticks(range(0, 24, 3))
        ax.set_ylim(bottom=0)
    axes[0][0].legend(frameon=False, fontsize=7, labelcolor=INK2)
    return _save(fig, "03_avg_intensity_diurnal.png")


def fig_net_imports(h: pd.DataFrame) -> str:
    fig, axes = _fig(3)
    for ax, ba in zip(axes[0], BAS):
        g = h[h["ba_code"] == ba].groupby("local_hour")["net_import_share"]
        q = g.quantile([0.25, 0.5, 0.75]).unstack() * 100
        ax.fill_between(q.index, q[0.25], q[0.75], color=INK2, alpha=0.15, linewidth=0)
        ax.plot(q.index, q[0.5], color=INK2, linewidth=2)
        _style(ax, f"{ba}: net-import share of demand (%)")
        ax.set_xticks(range(0, 24, 3))
        ax.set_ylim(bottom=0)
    return _save(fig, "04_net_import_share.png")


def fig_mef_vs_avg(det: pd.DataFrame, source: str) -> str:
    months = [1, 4, 7, 10]
    fig, axes = _fig(4, 3, w=3.2, h=2.5)
    x = det[(det["spec"] == "demand") & (det["emissions_source"] == source)]
    ymin = min(x["ci_low_95"].min(), 0)
    ymax = x["ci_high_95"].max()
    for r, ba in enumerate(BAS):
        for c, m in enumerate(months):
            ax = axes[r][c]
            g = x[(x["ba_code"] == ba) & (x["month"] == m)].sort_values("local_hour")
            ax.fill_between(g["local_hour"], g["ci_low_95"], g["ci_high_95"], color=MARGINAL, alpha=0.18, linewidth=0)
            ax.plot(g["local_hour"], g["mef_kg_per_mwh"], color=MARGINAL, linewidth=2, label="Marginal (95% CI)")
            ax.plot(g["local_hour"], g["avg_intensity_kg_per_mwh"], color=AVERAGE, linewidth=2, label="Average")
            ax.axhline(0, color=GRID, linewidth=0.8)
            _style(ax, f"{ba} · {pd.Timestamp(2024, m, 1):%b}")
            ax.set_ylim(ymin, ymax)
            ax.set_xticks(range(0, 24, 6))
    axes[0][0].legend(frameon=False, fontsize=7, labelcolor=INK2)
    fig.suptitle(f"Marginal vs average CO₂ intensity by local hour (kg/MWh), demand spec, {source} emissions",
                 color=INK, fontsize=10, x=0.01, ha="left")
    return _save(fig, f"05_mef_vs_avg_{source}.png")


def fig_divergence_heatmap(det: pd.DataFrame, source: str) -> str:
    x = det[(det["spec"] == "demand") & (det["emissions_source"] == source)]
    lim = 600
    fig, axes = _fig(3, w=4.4, h=3.2)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "div", ["#1c5cab", "#86b6ef", "#f0efec", "#f19a9a", "#b52c2c"])
    for ax, ba in zip(axes[0], BAS):
        g = x[x["ba_code"] == ba]
        grid = g.pivot(index="month", columns="local_hour", values="diff_kg_per_mwh")
        im = ax.imshow(grid, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto",
                       extent=(-0.5, 23.5, 12.5, 0.5))
        dv = g[g["diverges"]]
        ax.scatter(dv["local_hour"], dv["month"], s=6, color=INK, marker="o", linewidths=0)
        _style(ax, f"{ba}: marginal − average (kg/MWh)")
        ax.grid(False)
        ax.set_xticks(range(0, 24, 3))
        ax.set_yticks(range(1, 13))
        ax.set_yticklabels([pd.Timestamp(2024, m, 1).strftime("%b") for m in range(1, 13)])
    cb = fig.colorbar(im, ax=axes[0].tolist(), shrink=0.85, pad=0.01)
    cb.ax.tick_params(labelsize=7, colors=INK2)
    # Shared colorbar: save with bbox_inches instead of tight_layout.
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    name = f"06_divergence_{source}.png"
    fig.savefig(FIG_DIR / name, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return f"figures/{name}"
