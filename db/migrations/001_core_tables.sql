-- Core tables. All timestamps are hour-ENDING UTC (EIA convention).
-- Local time is derived, never stored: see 002_views.sql.

CREATE TABLE balancing_authority (
    ba_code   TEXT PRIMARY KEY,
    ba_name   TEXT NOT NULL,
    timezone  TEXT NOT NULL,          -- IANA
    region    TEXT
);

CREATE TABLE fuel_type (
    fuel_code        TEXT PRIMARY KEY,
    fuel_name        TEXT NOT NULL,
    is_fossil        BOOLEAN NOT NULL,
    is_storage       BOOLEAN NOT NULL,
    co2_kg_per_mwh   NUMERIC,          -- NULL = no rate assigned; see data/README.md
    factor_source    TEXT
);

-- Train / hold-out windows, loaded from src/marginalis/config.py (never edited here).
CREATE TABLE study_split (
    split_name  TEXT PRIMARY KEY,
    start_utc   TIMESTAMPTZ NOT NULL,  -- inclusive
    end_utc     TIMESTAMPTZ NOT NULL   -- exclusive
);

-- Quality flags used across tables:
--   ok | interpolated | missing | outlier_nulled | negative_nulled
CREATE TABLE grid_hour (
    ba_code              TEXT NOT NULL REFERENCES balancing_authority,
    ts_utc               TIMESTAMPTZ NOT NULL,
    demand_mwh           DOUBLE PRECISION,
    demand_forecast_mwh  DOUBLE PRECISION,
    net_generation_mwh   DOUBLE PRECISION,
    interchange_mwh      DOUBLE PRECISION,   -- positive = net export
    temp_c               DOUBLE PRECISION,
    demand_flag          TEXT NOT NULL,
    net_generation_flag  TEXT NOT NULL,
    interchange_flag     TEXT NOT NULL,
    is_imputed           BOOLEAN NOT NULL,   -- any column interpolated
    PRIMARY KEY (ba_code, ts_utc)
);
CREATE INDEX grid_hour_ts_idx ON grid_hour (ts_utc);

CREATE TABLE generation_by_fuel (
    ba_code         TEXT NOT NULL,
    ts_utc          TIMESTAMPTZ NOT NULL,
    fuel_code       TEXT NOT NULL REFERENCES fuel_type,
    generation_mwh  DOUBLE PRECISION,
    flag            TEXT NOT NULL,
    is_imputed      BOOLEAN NOT NULL,
    PRIMARY KEY (ba_code, ts_utc, fuel_code),
    FOREIGN KEY (ba_code, ts_utc) REFERENCES grid_hour
);

CREATE TABLE interchange_by_pair (
    ba_code   TEXT NOT NULL,
    ts_utc    TIMESTAMPTZ NOT NULL,
    to_ba     TEXT NOT NULL,
    flow_mwh  DOUBLE PRECISION,              -- positive = ba_code -> to_ba
    PRIMARY KEY (ba_code, ts_utc, to_ba),
    FOREIGN KEY (ba_code, ts_utc) REFERENCES grid_hour
);

-- Rebuildable from the tables above plus EIA's published estimates.
CREATE TABLE hourly_emissions (
    ba_code                 TEXT NOT NULL,
    ts_utc                  TIMESTAMPTZ NOT NULL,
    co2_kg_derived          DOUBLE PRECISION,  -- Option A: sum(generation x fuel rate)
    derived_complete        BOOLEAN NOT NULL,  -- all fossil fuels present for the hour
    co2_kg_eia_generated    DOUBLE PRECISION,  -- Option B: EIA published, in-BA generation
    co2_kg_eia_imported     DOUBLE PRECISION,
    co2_kg_eia_exported     DOUBLE PRECISION,
    co2_kg_eia_consumed     DOUBLE PRECISION,
    PRIMARY KEY (ba_code, ts_utc),
    FOREIGN KEY (ba_code, ts_utc) REFERENCES grid_hour
);

-- One row per (BA, cleaning rule, split, year): feeds reports/data_quality.md.
CREATE TABLE quality_log (
    ba_code     TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL,
    rule        TEXT NOT NULL,
    year        INTEGER NOT NULL,
    n_rows      INTEGER NOT NULL,
    PRIMARY KEY (ba_code, table_name, column_name, rule, year)
);
