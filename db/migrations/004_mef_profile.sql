-- Marginal emissions factor profile, one row per
-- BA x spec x emissions_source x month x local_hour, estimated on the TRAIN split only
-- (src/marginalis/analysis/mef.py; method in docs/preregistration.md).
-- Pooled strata share a stratum_id and repeat the same estimate in each covered row.

CREATE TABLE mef_profile (
    ba_code                   TEXT NOT NULL REFERENCES balancing_authority,
    spec                      TEXT NOT NULL CHECK (spec IN ('demand', 'fossil_gen')),
    emissions_source          TEXT NOT NULL CHECK (emissions_source IN ('derived', 'eia')),
    month                     INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    local_hour                INTEGER NOT NULL CHECK (local_hour BETWEEN 0 AND 23),
    mef_kg_per_mwh            DOUBLE PRECISION NOT NULL,
    ci_low_95                 DOUBLE PRECISION NOT NULL,
    ci_high_95                DOUBLE PRECISION NOT NULL,
    n_obs                     INTEGER NOT NULL,
    stratum_id                TEXT NOT NULL,
    avg_intensity_kg_per_mwh  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (ba_code, spec, emissions_source, month, local_hour)
);
