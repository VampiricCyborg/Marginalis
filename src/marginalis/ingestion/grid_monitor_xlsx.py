"""EIA's published hourly CO2 estimates (Option B), from the per-BA Grid Monitor workbooks.

These are not in the JSON API. Each workbook is a live snapshot covering 2015 to
the present, so the raw download is stored with its download date in the name and
never overwritten. Parsing keeps the columns needed for the emissions series and
for cross-checking the API pull.

Units, verified against the workbook's own columns (emissions = factor x generation):
  "CO2 Factor: <fuel>"   lb CO2 per kWh
  "CO2 Emissions: ..."   metric tonnes CO2
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from marginalis.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

URL = "https://www.eia.gov/electricity/gridmonitor/knownissues/xls/{ba}.xlsx"
SHEET = "Published Hourly Data"

# workbook column -> tidy column
COLUMNS = {
    "UTC time": "ts_utc",
    "Demand": "demand_mwh",
    "Net generation": "net_generation_mwh",
    "Total interchange": "interchange_mwh",
    "Imputed demand": "imputed_demand_mwh",
    "Imputed net generation": "imputed_net_generation_mwh",
    "Adjusted demand": "adjusted_demand_mwh",
    "Adjusted net generation": "adjusted_net_generation_mwh",
    "CO2 Factor: COL": "eia_factor_col_lb_per_kwh",
    "CO2 Factor: NG": "eia_factor_ng_lb_per_kwh",
    "CO2 Factor: OIL": "eia_factor_oil_lb_per_kwh",
    "CO2 Emissions: COL": "co2_t_col",
    "CO2 Emissions: NG": "co2_t_ng",
    "CO2 Emissions: OIL": "co2_t_oil",
    "CO2 Emissions: Other": "co2_t_other",
    "CO2 Emissions Generated": "co2_t_generated",
    "CO2 Emissions Imported": "co2_t_imported",
    "CO2 Emissions Exported": "co2_t_exported",
    "CO2 Emissions Consumed": "co2_t_consumed",
}


def raw_dir(ba: str) -> Path:
    return RAW_DIR / "eia_grid_monitor" / ba


def download(ba: str, *, force: bool = False) -> Path:
    """Download today's snapshot unless one from today already exists."""
    path = raw_dir(ba) / f"{ba}_{date.today():%Y-%m-%d}.xlsx"
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".xlsx.tmp")
    with requests.get(URL.format(ba=ba), stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(path)
    log.info("grid monitor %s: %.1f MB", ba, path.stat().st_size / 1e6)
    return path


def latest_snapshot(ba: str) -> Path:
    files = sorted(raw_dir(ba).glob(f"{ba}_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"no Grid Monitor workbook for {ba}; run ingestion first")
    return files[-1]


def parse(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET, engine="calamine")
    missing = [c for c in ("BA", "UTC time", "CO2 Emissions Generated") if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: workbook layout changed, missing {missing}")
    out = df[[c for c in COLUMNS if c in df.columns]].rename(columns=COLUMNS)
    out["ts_utc"] = pd.to_datetime(out["ts_utc"]).dt.tz_localize("UTC")
    out.insert(0, "ba_code", df["BA"].astype("string"))
    out["source_file"] = path.name
    return out


def parsed_path(ba: str) -> Path:
    return PROCESSED_DIR / "eia_grid_monitor" / f"{ba}.parquet"


def build(ba: str, *, force_download: bool = False) -> Path:
    """Download (if needed) and parse to parquet."""
    src = download(ba, force=force_download)
    out = parsed_path(ba)
    if out.exists() and pd.read_parquet(out, columns=["source_file"]).iat[0, 0] == src.name:
        return out
    df = parse(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    log.info("grid monitor %s parsed: %d rows", ba, len(df))
    return out
