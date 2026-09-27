"""EIA-930 via the v2 API.

One generic paginator serves all three routes. Raw pulls are stored one parquet
file per (route, BA, UTC month) with values kept exactly as returned (strings),
so the raw layer is immutable and re-runs skip months already on disk.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests
from dotenv import load_dotenv

from marginalis.config import RAW_DIR

log = logging.getLogger(__name__)

BASE_URL = "https://api.eia.gov/v2/electricity/rto/"
PAGE_SIZE = 5000
MAX_RETRIES = 6


@dataclass(frozen=True)
class Route:
    name: str
    ba_facet: str  # which facet selects the BA


ROUTES = {
    "region-data": Route("region-data", "respondent"),
    "fuel-type-data": Route("fuel-type-data", "respondent"),
    "interchange-data": Route("interchange-data", "fromba"),
}


def api_key() -> str:
    load_dotenv()
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("EIA_API_KEY is not set (see .env.example)")
    return key


def _get(session: requests.Session, url: str, params: dict) -> dict:
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=120)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_RETRIES:
                raise
            log.warning("request failed (%s); retry %d in %.0fs", exc, attempt, delay)
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code != 429 and resp.status_code < 500:
                resp.raise_for_status()
            if attempt == MAX_RETRIES:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
            log.warning("HTTP %d; retry %d in %.0fs", resp.status_code, attempt, delay)
        time.sleep(delay)
        delay = min(delay * 2, 120)
    raise AssertionError("unreachable")


def paginate(
    route: str,
    params: dict,
    *,
    session: requests.Session | None = None,
    key: str | None = None,
) -> Iterator[dict]:
    """Yield every row for a query, following offset pagination to the reported total."""
    session = session or requests.Session()
    url = f"{BASE_URL}{route}/data/"
    base = {
        "api_key": key or api_key(),
        "frequency": "hourly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": PAGE_SIZE,
        **params,
    }
    offset, total = 0, None
    while total is None or offset < total:
        body = _get(session, url, {**base, "offset": offset})["response"]
        total = int(body["total"])
        rows = body["data"]
        if not rows:
            if offset < total:
                raise RuntimeError(f"{route}: empty page at offset {offset} of {total}")
            break
        yield from rows
        offset += len(rows)


def _period(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def next_month(m: datetime) -> datetime:
    return m.replace(year=m.year + m.month // 12, month=m.month % 12 + 1)


def month_starts(start: datetime, end: datetime) -> list[datetime]:
    out, cur = [], start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur < end:
        out.append(cur)
        cur = next_month(cur)
    return out


def raw_path(route: str, ba: str, month: datetime) -> Path:
    return RAW_DIR / "eia" / route / ba / f"{month:%Y-%m}.parquet"


def fetch_month(
    route: str,
    ba: str,
    month: datetime,
    *,
    session: requests.Session | None = None,
    key: str | None = None,
    force: bool = False,
) -> Path:
    """Pull one UTC month for one BA into data/raw; skip if already on disk."""
    path = raw_path(route, ba, month)
    if path.exists() and not force:
        return path
    # EIA periods are hour-ENDING and `start`/`end` are inclusive, so the hours
    # covering this month are labelled 01:00 on the 1st through 00:00 on the next 1st.
    params = {
        f"facets[{ROUTES[route].ba_facet}][]": ba,
        "start": _period(month + pd.Timedelta(hours=1)),
        "end": _period(next_month(month)),
    }
    rows = list(paginate(route, params, session=session, key=key))
    df = pd.DataFrame(rows).astype("string")
    df["fetched_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("%s %s %s: %d rows", route, ba, f"{month:%Y-%m}", len(df))
    return path


def fetch_range(
    route: str, ba: str, start: datetime, end: datetime, *, force: bool = False
) -> list[Path]:
    session, key = requests.Session(), api_key()
    return [
        fetch_month(route, ba, m, session=session, key=key, force=force)
        for m in month_starts(start, end)
    ]


def read_raw(route: str, ba: str) -> pd.DataFrame:
    files = sorted((RAW_DIR / "eia" / route / ba).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no raw {route} files for {ba}; run ingestion first")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
