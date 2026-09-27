"""Hourly 2 m temperature from the Open-Meteo historical archive (no key needed)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from marginalis.config import BAS, RAW_DIR, City

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def raw_path(ba: str, city: City) -> Path:
    return RAW_DIR / "weather" / ba / f"{city.name.replace(' ', '_').lower()}.parquet"


def fetch_city(
    ba: str, city: City, start: datetime, end: datetime, *, force: bool = False
) -> Path:
    path = raw_path(ba, city)
    if path.exists() and not force:
        return path
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "start_date": f"{start:%Y-%m-%d}",
        "end_date": f"{end - timedelta(hours=1):%Y-%m-%d}",
        "hourly": "temperature_2m",
        "timezone": "UTC",
    }
    delay = 5.0
    for attempt in range(5):
        resp = requests.get(ARCHIVE_URL, params=params, timeout=180)
        if resp.status_code == 200:
            break
        if (resp.status_code != 429 and resp.status_code < 500) or attempt == 4:
            resp.raise_for_status()
        log.warning("Open-Meteo HTTP %d; retry in %.0fs", resp.status_code, delay)
        time.sleep(delay)
        delay *= 2
    body = resp.json()
    df = pd.DataFrame(
        {
            "time_utc": body["hourly"]["time"],
            "temperature_2m": body["hourly"]["temperature_2m"],
        }
    )
    df["city"] = city.name
    df["lat"], df["lon"] = body["latitude"], body["longitude"]
    df["units"] = body["hourly_units"]["temperature_2m"]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("weather %s %s: %d rows", ba, city.name, len(df))
    return path


def fetch_ba(ba: str, start: datetime, end: datetime, *, force: bool = False) -> list[Path]:
    return [fetch_city(ba, c, start, end, force=force) for c in BAS[ba].weather_cities]


def read_raw(ba: str) -> pd.DataFrame:
    files = sorted((RAW_DIR / "weather" / ba).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no raw weather files for {ba}; run ingestion first")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
