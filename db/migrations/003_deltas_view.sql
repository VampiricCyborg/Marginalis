-- Hour-over-hour first differences: a data interface for the regression, not a model.
-- No filtering is applied here; each row carries both hours' flags so the analysis
-- decides what to exclude. `consecutive` is false when the previous hour is absent.

CREATE VIEW v_hour_delta AS
SELECT
    ba_code,
    ts_utc,
    local_start,
    local_hour,
    local_date,
    split_name,
    LAG(ts_utc) OVER w = ts_utc - INTERVAL '1 hour'                    AS consecutive,
    demand_mwh             - LAG(demand_mwh)             OVER w        AS d_demand_mwh,
    net_generation_mwh     - LAG(net_generation_mwh)     OVER w        AS d_net_generation_mwh,
    fossil_generation_mwh  - LAG(fossil_generation_mwh)  OVER w        AS d_fossil_generation_mwh,
    wind_solar_mwh         - LAG(wind_solar_mwh)         OVER w        AS d_wind_solar_mwh,
    net_load_mwh           - LAG(net_load_mwh)           OVER w        AS d_net_load_mwh,
    interchange_mwh        - LAG(interchange_mwh)        OVER w        AS d_interchange_mwh,
    temp_c                 - LAG(temp_c)                 OVER w        AS d_temp_c,
    co2_kg_derived         - LAG(co2_kg_derived)         OVER w        AS d_co2_kg_derived,
    co2_kg_eia_generated   - LAG(co2_kg_eia_generated)   OVER w        AS d_co2_kg_eia_generated,
    co2_kg_eia_consumed    - LAG(co2_kg_eia_consumed)    OVER w        AS d_co2_kg_eia_consumed,
    temp_c,
    net_import_share,
    avg_intensity_derived_kg_per_mwh,
    avg_intensity_eia_kg_per_mwh,
    demand_flag,
    LAG(demand_flag)       OVER w                                      AS prev_demand_flag,
    derived_complete AND LAG(derived_complete) OVER w                  AS derived_complete_both,
    is_imputed OR LAG(is_imputed) OVER w                               AS imputed_either
FROM v_hour
WINDOW w AS (PARTITION BY ba_code ORDER BY ts_utc);

CREATE VIEW v_hour_delta_train AS
SELECT * FROM v_hour_delta WHERE split_name = 'train';
