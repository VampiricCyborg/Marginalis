"""Project-wide constants. The train/hold-out split lives here and nowhere else."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = ROOT / "reports"


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


# --- Time windows (UTC, half-open [start, end)) -------------------------------
# EIA-930 fuel-type data begins mid-2019; the study runs through 2026-08.
DATA_START = _utc(2019, 7, 1)
DATA_END = _utc(2026, 9, 1)


@dataclass(frozen=True)
class Split:
    name: str
    start: datetime
    end: datetime


TRAIN = Split("train", _utc(2019, 7, 1), _utc(2025, 1, 1))
HOLDOUT = Split("holdout_2025", _utc(2025, 1, 1), _utc(2026, 1, 1))
HOLDOUT_YTD = Split("holdout_2026ytd", _utc(2026, 1, 1), DATA_END)
SPLITS = (TRAIN, HOLDOUT, HOLDOUT_YTD)

# Flip to True only once the method is frozen (see docs/preregistration.md).
METHOD_FROZEN = False


class HeldOutDataError(RuntimeError):
    pass


def require_split(split: Split) -> Split:
    """Gate for analysis-facing reads. Held-out splits are refused until frozen."""
    if split is not TRAIN and not METHOD_FROZEN:
        raise HeldOutDataError(
            f"{split.name} is held out; set METHOD_FROZEN only after the method is frozen"
        )
    return split


# --- Balancing authorities ----------------------------------------------------
@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class BA:
    code: str
    name: str
    timezone: str
    region: str
    weather_cities: tuple[City, ...]


# Order is the build order: ERCO first (near-isolated, cleanest case), then CISO, MISO.
BAS: dict[str, BA] = {
    "ERCO": BA(
        "ERCO",
        "Electric Reliability Council of Texas",
        "America/Chicago",
        "TEX",
        (
            City("Houston", 29.76, -95.37),
            City("Dallas", 32.78, -96.80),
            City("San Antonio", 29.42, -98.49),
            City("Austin", 30.27, -97.74),
        ),
    ),
    "CISO": BA(
        "CISO",
        "California Independent System Operator",
        "America/Los_Angeles",
        "CAL",
        (
            City("Los Angeles", 34.05, -118.24),
            City("San Francisco", 37.77, -122.42),
            City("Sacramento", 38.58, -121.49),
            City("San Diego", 32.72, -117.16),
        ),
    ),
    "MISO": BA(
        "MISO",
        "Midcontinent Independent System Operator",
        "America/Chicago",  # MISO spans two zones; verified against EIA-930 reference table at ingest.
        "MIDW",
        (
            City("Minneapolis", 44.98, -93.27),
            City("Detroit", 42.33, -83.05),
            City("St. Louis", 38.63, -90.20),
            City("New Orleans", 29.95, -90.07),
        ),
    ),
}
