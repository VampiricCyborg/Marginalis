"""Fingerprint a Marginalis database so a migrated copy can be compared with the source.

    uv run python scripts/verify_db.py                      # uses DATABASE_URL / local default
    uv run python scripts/verify_db.py "postgresql://..."   # any other database

Prints row counts per BA for every hourly table/view and md5 checksums of mef_profile and
the train views, so two databases match only if their contents match.
"""

from __future__ import annotations

import json
import sys

import psycopg

from marginalis.db import database_url

COUNTS = {
    "grid_hour": "SELECT ba_code, COUNT(*) FROM grid_hour GROUP BY 1",
    "v_hour": "SELECT ba_code, COUNT(*) FROM v_hour GROUP BY 1",
    "v_hour_train": "SELECT ba_code, COUNT(*) FROM v_hour_train GROUP BY 1",
    "v_hour_delta": "SELECT ba_code, COUNT(*) FROM v_hour_delta GROUP BY 1",
    "v_hour_delta_train": "SELECT ba_code, COUNT(*) FROM v_hour_delta_train GROUP BY 1",
    "generation_by_fuel": "SELECT ba_code, COUNT(*) FROM generation_by_fuel GROUP BY 1",
    "interchange_by_pair": "SELECT ba_code, COUNT(*) FROM interchange_by_pair GROUP BY 1",
    "hourly_emissions": "SELECT ba_code, COUNT(*) FROM hourly_emissions GROUP BY 1",
    "mef_profile": "SELECT ba_code, COUNT(*) FROM mef_profile GROUP BY 1",
}
CHECKSUMS = {
    "mef_profile": "SELECT md5(string_agg(t::text, '|' ORDER BY ba_code, spec, emissions_source, month, local_hour)) FROM mef_profile t",
    "v_hour_train": ("SELECT md5(string_agg(concat_ws(',', ba_code, ts_utc, local_hour, demand_mwh, co2_kg_derived, "
                     "co2_kg_eia_generated, net_import_share), '|' ORDER BY ba_code, ts_utc)) FROM v_hour_train"),
    "v_hour_delta_train": ("SELECT md5(string_agg(concat_ws(',', ba_code, ts_utc, d_demand_mwh, d_co2_kg_eia_generated, "
                           "consecutive, imputed_either), '|' ORDER BY ba_code, ts_utc)) FROM v_hour_delta_train"),
    "schema_migrations": "SELECT string_agg(filename, ',' ORDER BY filename) FROM schema_migrations",
}


def fingerprint(url: str) -> dict:
    with psycopg.connect(url) as conn:
        out = {"counts": {}, "checksums": {}}
        for name, sql in COUNTS.items():
            out["counts"][name] = {ba: n for ba, n in conn.execute(sql).fetchall()}
        for name, sql in CHECKSUMS.items():
            out["checksums"][name] = conn.execute(sql).fetchone()[0]
        return out


if __name__ == "__main__":
    print(json.dumps(fingerprint(sys.argv[1] if len(sys.argv) > 1 else database_url()), indent=1, sort_keys=True))
