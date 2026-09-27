-- Analysis-facing views. Local time is derived here from the BA's IANA zone.
-- ts_utc is hour-ending, so the hour an observation covers BEGINS at ts_utc - 1h.

CREATE VIEW v_hour AS
WITH fuel AS (
    SELECT g.ba_code, g.ts_utc,
           SUM(g.generation_mwh) FILTER (WHERE f.is_fossil)          AS fossil_generation_mwh,
           SUM(g.generation_mwh) FILTER (WHERE f.fuel_code IN ('SUN', 'WND')) AS wind_solar_mwh,
           SUM(g.generation_mwh)                                       AS fuel_sum_mwh
    FROM generation_by_fuel g
    JOIN fuel_type f USING (fuel_code)
    GROUP BY g.ba_code, g.ts_utc
)
SELECT
    h.ba_code,
    h.ts_utc,
    (h.ts_utc - INTERVAL '1 hour') AT TIME ZONE b.timezone            AS local_start,
    EXTRACT(HOUR FROM (h.ts_utc - INTERVAL '1 hour') AT TIME ZONE b.timezone)::int AS local_hour,
    ((h.ts_utc - INTERVAL '1 hour') AT TIME ZONE b.timezone)::date     AS local_date,
    s.split_name,
    h.demand_mwh,
    h.demand_forecast_mwh,
    h.net_generation_mwh,
    h.interchange_mwh,
    h.temp_c,
    fu.fossil_generation_mwh,
    fu.wind_solar_mwh,
    fu.fuel_sum_mwh,
    h.demand_mwh - fu.wind_solar_mwh                                   AS net_load_mwh,
    -- Share of demand met by net imports (0 when the BA is a net exporter).
    GREATEST(-h.interchange_mwh, 0) / NULLIF(h.demand_mwh, 0)          AS net_import_share,
    e.co2_kg_derived,
    e.derived_complete,
    e.co2_kg_eia_generated,
    e.co2_kg_eia_consumed,
    -- Average intensities: generation-based (in-BA CO2 / in-BA generation) and
    -- EIA's consumption-based (includes imported, excludes exported CO2).
    e.co2_kg_derived       / NULLIF(h.net_generation_mwh, 0)           AS avg_intensity_derived_kg_per_mwh,
    e.co2_kg_eia_generated / NULLIF(h.net_generation_mwh, 0)           AS avg_intensity_eia_kg_per_mwh,
    e.co2_kg_eia_consumed  / NULLIF(h.demand_mwh, 0)                   AS avg_intensity_eia_consumed_kg_per_mwh,
    h.demand_flag,
    h.net_generation_flag,
    h.interchange_flag,
    h.is_imputed
FROM grid_hour h
JOIN balancing_authority b USING (ba_code)
LEFT JOIN study_split s ON h.ts_utc > s.start_utc AND h.ts_utc <= s.end_utc
LEFT JOIN fuel fu USING (ba_code, ts_utc)
LEFT JOIN hourly_emissions e USING (ba_code, ts_utc);

-- The only view analysis code should read until the method is frozen.
CREATE VIEW v_hour_train AS
SELECT * FROM v_hour WHERE split_name = 'train';
