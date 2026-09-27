"""Generate reports/data_quality.md from the database.

Covers the TRAIN split only: hold-out periods are not summarised until the method
is frozen (config.METHOD_FROZEN), at which point their sections are added.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import psycopg

from marginalis.config import BAS, REPORTS_DIR, SPLITS, HeldOutDataError, require_split
from marginalis.ingestion import grid_monitor_xlsx
from marginalis.transform import tidy
from marginalis.transform.clean import MAX_INTERP_GAP, OUTLIER_RATIO, OUTLIER_WINDOW


def _q(conn: psycopg.Connection, sql: str, params: dict) -> pd.DataFrame:
    cur = conn.execute(sql, params)
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def _md(df: pd.DataFrame, floatfmt: str = "{:,.2f}") -> str:
    def fmt(v):
        if isinstance(v, float):
            return floatfmt.format(v)
        if isinstance(v, int) and not isinstance(v, bool):
            return f"{v:,}"
        return str(v)

    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def _sections(conn: psycopg.Connection, split) -> list[str]:
    p = {"split": split.name, "start": split.start, "end": split.end}
    out = [f"## Split: {split.name} ({split.start:%Y-%m-%d} → {split.end:%Y-%m-%d})"]

    cov = _q(conn, """
        SELECT ba_code AS "BA", EXTRACT(YEAR FROM ts_utc - INTERVAL '1 hour')::int::text AS "year",
               COUNT(*)::int AS "hours",
               ROUND(100.0 * AVG((demand_flag = 'ok')::int), 2)::float AS "demand ok %%",
               ROUND(100.0 * AVG((demand_flag = 'interpolated')::int), 2)::float AS "demand interp %%",
               ROUND(100.0 * AVG((demand_mwh IS NULL)::int), 2)::float AS "demand null %%",
               ROUND(100.0 * AVG(is_imputed::int), 2)::float AS "any imputed %%",
               ROUND(100.0 * AVG((temp_c IS NULL)::int), 2)::float AS "temp null %%"
        FROM grid_hour
        WHERE ts_utc > %(start)s AND ts_utc <= %(end)s
        GROUP BY 1, 2 ORDER BY 1, 2""", p)
    out += ["### Hourly coverage (grid_hour)", _md(cov)]

    rules = _q(conn, """
        SELECT ba_code AS "BA", table_name AS "table", column_name AS "column", rule,
               SUM(n_rows)::int AS "rows"
        FROM quality_log
        WHERE year BETWEEN EXTRACT(YEAR FROM %(start)s::timestamptz)
                       AND EXTRACT(YEAR FROM %(end)s::timestamptz - INTERVAL '1 hour')
        GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4""", p)
    out += [
        "### Rows touched by each cleaning rule",
        "Counts by calendar year of the hour's start, summed over the split's years.",
        _md(rules),
    ]

    fuels = _q(conn, """
        SELECT ba_code AS "BA", fuel_code AS "fuel",
               MIN(ts_utc - INTERVAL '1 hour')::date AS "first",
               MAX(ts_utc - INTERVAL '1 hour')::date AS "last",
               ROUND(100.0 * AVG((flag <> 'ok')::int), 3)::float AS "not ok %%",
               ROUND(100.0 * AVG((generation_mwh < 0)::int), 3)::float AS "negative %%"
        FROM generation_by_fuel
        WHERE ts_utc > %(start)s AND ts_utc <= %(end)s
        GROUP BY 1, 2 ORDER BY 1, 2""", p)
    out += ["### Generation by fuel", _md(fuels, "{:,.3f}")]

    recon = _q(conn, """
        SELECT ba_code AS "BA", EXTRACT(YEAR FROM ts_utc - INTERVAL '1 hour')::int::text AS "year",
               ROUND((100 * PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY ABS(fuel_sum_mwh - net_generation_mwh) / net_generation_mwh))::numeric, 3)::float
                   AS "median |Σfuel − NG| %%",
               ROUND((100 * PERCENTILE_CONT(0.95) WITHIN GROUP (
                   ORDER BY ABS(fuel_sum_mwh - net_generation_mwh) / net_generation_mwh))::numeric, 3)::float
                   AS "p95 |Σfuel − NG| %%"
        FROM v_hour
        WHERE split_name = %(split)s AND net_generation_mwh > 0 AND fuel_sum_mwh IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2""", p)
    out += [
        "### Fuel-type totals vs. reported net generation",
        "Not rescaled: fuel-level values are used as reported.",
        _md(recon, "{:,.3f}"),
    ]

    emis = _q(conn, """
        SELECT ba_code AS "BA", EXTRACT(YEAR FROM ts_utc - INTERVAL '1 hour')::int::text AS "year",
               ROUND(100.0 * AVG((NOT derived_complete)::int), 3)::float AS "derived incomplete %%",
               ROUND(100.0 * AVG((co2_kg_eia_generated IS NULL)::int), 3)::float AS "EIA CO2 null %%",
               ROUND((SUM(co2_kg_derived) FILTER (WHERE co2_kg_eia_generated IS NOT NULL)
                     / NULLIF(SUM(co2_kg_eia_generated) FILTER (WHERE co2_kg_derived IS NOT NULL), 0)
                     )::numeric, 4)::float AS "Σ derived / Σ EIA"
        FROM hourly_emissions
        WHERE ts_utc > %(start)s AND ts_utc <= %(end)s
        GROUP BY 1, 2 ORDER BY 1, 2""", p)
    out += [
        "### Emissions series completeness",
        "`Σ derived / Σ EIA` is a pipeline sanity check on annual totals, not an analysis result.",
        _md(emis, "{:,.4f}"),
    ]
    out += ["### EIA API vs. Grid Monitor workbook", _md(_api_vs_workbook(split), "{:,.3f}")]
    return out


def _api_vs_workbook(split) -> pd.DataFrame:
    """Two ingest paths for the same EIA series: API pull vs. the published workbook."""
    rows = []
    for ba in BAS:
        try:
            wb = pd.read_parquet(grid_monitor_xlsx.parsed_path(ba))
            api = tidy.region(ba)
        except FileNotFoundError:
            continue
        wb = wb[(wb["ts_utc"] > split.start) & (wb["ts_utc"] <= split.end)]
        wb = wb.drop_duplicates("ts_utc").set_index("ts_utc")
        for series in ("demand_mwh", "net_generation_mwh"):
            a = api[api["series"] == series].drop_duplicates("ts_utc").set_index("ts_utc")["value"]
            j = pd.concat([a.rename("api"), wb[series].rename("wb")], axis=1, join="inner").dropna()
            diff = (j["api"] - j["wb"]).abs()
            imputed_col = f"imputed_{series}"
            imputed = wb[imputed_col].notna().mean() if imputed_col in wb else float("nan")
            rows.append({
                "BA": ba, "series": series, "hours compared": len(j),
                "identical %": 100 * float((diff == 0).mean()),
                "p99 abs diff MWh": float(diff.quantile(0.99)),
                "max abs diff MWh": float(diff.max()),
                "EIA-imputed %": 100 * float(imputed),
            })
    return pd.DataFrame(rows)


def write(conn: psycopg.Connection) -> str:
    splits = []
    for s in SPLITS:
        try:
            splits.append(require_split(s))
        except HeldOutDataError:
            pass
    lines = [
        "# Data quality report",
        "",
        f"_Generated by `marginalis report` at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
        "Do not edit by hand._",
        "",
        "Cleaning rules (see `src/marginalis/transform/clean.py`): duplicates dropped or nulled "
        "if conflicting; non-numeric values nulled; demand/net generation ≤ 0 nulled; negative "
        f"COL/NG/OIL/NUC nulled; demand/net generation more than {OUTLIER_RATIO:.0%} from the "
        f"centred {OUTLIER_WINDOW}-hour rolling median nulled; interior gaps ≤ {MAX_INTERP_GAP} h "
        "linearly interpolated; longer gaps left NULL.",
        "",
        "Timestamps are hour-ending UTC; a year is the calendar year of the hour's start.",
        "",
    ]
    if len(splits) < len(SPLITS):
        lines += ["Hold-out splits are excluded until the method is frozen.", ""]
    for s in splits:
        lines += [part + "\n" for part in _sections(conn, s)]
    text = "\n".join(lines)
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "data_quality.md").write_text(text, encoding="utf-8")
    return text

