"""Export audited defaults and the actual temporary quarantine test evidence."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.generate_data import load_assumptions
from src.metrics import quality_cost, rates, monthly_volume, investment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarantine-db", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.quarantine_db) as con:
        quarantine = pd.read_sql_query("SELECT run_id,source_table,raw_row_json,reject_reason FROM etl_quarantine", con)
        runs = pd.read_sql_query("SELECT * FROM etl_run_log", con)
    assert len(quarantine) == 10 and quarantine.reject_reason.notna().all()
    quarantine.to_csv(ROOT / "reports/quarantine_test.csv", index=False, encoding="utf-8-sig")
    runs.to_csv(ROOT / "reports/quarantine_test_runs.csv", index=False, encoding="utf-8-sig")
    with sqlite3.connect((ROOT / "data/warehouse/threeeyes_dw.db").as_uri() + "?mode=ro", uri=True) as con:
        frame = pd.read_sql_query("SELECT * FROM fact_inspection", con)
        claims = pd.read_sql_query("SELECT * FROM fact_customer_claim", con)
        scenarios = pd.read_sql_query("SELECT * FROM dim_scenario", con)
    params = load_assumptions()
    manual = frame[frame.scenario_key.eq(0)]
    mc = quality_cost(manual, claims, params["labor_cost_per_hour"])
    volume = monthly_volume(len(manual), "2025-01-06", "2025-04-06")
    rows = []
    for s in scenarios.itertuples():
        part = frame[frame.scenario_key.eq(s.scenario_key)]
        cost = quality_cost(part, claims, params["labor_cost_per_hour"])
        row = {"scenario": s.scenario_name, **rates(part), **cost}
        if s.scenario_key:
            result = investment(mc["per_unit"], cost["per_unit"], volume,
                params["device_count"]*params["device_subscription_per_month"], params["device_count"]*params["device_unit_price"])
            row.update({k: v for k, v in result.items() if k != "projection"})
        rows.append(row)
    pd.DataFrame(rows).to_csv(ROOT / "reports/default_kpis.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({"monthly_volume": volume, "scenarios": rows}, indent=2))


if __name__ == "__main__":
    main()
