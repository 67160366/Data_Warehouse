import json
import shutil
import sqlite3
import pandas as pd
from conftest import run_etl


def test_repeatable_staging_and_reject_reconciliation(warehouse, tmp_path):
    db = tmp_path / "dirty.db"
    shutil.copy2(warehouse[0], db)
    raw, reports = warehouse[1], tmp_path / "reports"
    with sqlite3.connect(db) as con:
        before = con.execute("SELECT COUNT(*),SUM(true_defects),SUM(defects_escaped),SUM(labor_cost),SUM(claim_cost) FROM fact_lot_summary").fetchone()
    run_etl(db, raw, reports)
    with sqlite3.connect(db) as con:
        assert before == con.execute("SELECT COUNT(*),SUM(true_defects),SUM(defects_escaped),SUM(labor_cost),SUM(claim_cost) FROM fact_lot_summary").fetchone()
        ins = pd.read_sql_query("SELECT * FROM stg_fact_inspection LIMIT 1", con)
        clm = pd.read_sql_query("SELECT * FROM stg_fact_customer_claim LIMIT 1", con)
        assert len(clm) == 1
        # Ten bad appended rows, leaving valid originals untouched.
        for i, (col, value) in enumerate([("true_defect_key", 999), ("unit_id", None),
                                         ("lighting_cond", "invalid"), ("hour_in_shift", 9), ("inspect_seconds", -1)]):
            row = ins.copy()
            row["inspection_id"] = 100000+i
            row["unit_id"] = f"BAD-{i}"
            row[col] = value
            row.to_sql("stg_fact_inspection", con, if_exists="append", index=False)
        for i, (col, value) in enumerate([("lot_key", 999), ("defect_key", None),
                                         ("scenario_key", 999), ("qty_returned", -1), ("claim_cost", -1)]):
            row = clm.copy()
            row["claim_id"] = 100000+i
            row[col] = value
            row.to_sql("stg_fact_customer_claim", con, if_exists="append", index=False)
    # Do not reload raw CSV: downstream steps must consume the altered staging.
    for step in ("04_load_facts", "05_build_marts", "06_validate"):
        run_etl(db, raw, reports, f"src/etl/{step}.py")
    with sqlite3.connect(db) as con:
        latest = con.execute("SELECT run_id,rows_read,rows_loaded,rows_rejected,status FROM etl_run_log WHERE step_name='load_facts' ORDER BY run_id DESC LIMIT 1").fetchone()
        assert latest[1] == latest[2] + latest[3]
        assert latest[3:] == (10, "partial")
        reasons = con.execute("SELECT source_table,reject_reason FROM etl_quarantine WHERE run_id=?", (latest[0],)).fetchall()
        assert len(reasons) == 10 and all(reason for _, reason in reasons)
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert before == con.execute("SELECT COUNT(*),SUM(true_defects),SUM(defects_escaped),SUM(labor_cost),SUM(claim_cost) FROM fact_lot_summary").fetchone()
    assert json.loads((reports / "data_manifest.json").read_text())["status"] == "PASS"
    # Clean rerun ignores historical quarantines in current reconciliation.
    run_etl(db, raw, reports)
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM etl_quarantine").fetchone()[0] == 10
        assert con.execute("SELECT rows_rejected FROM etl_run_log WHERE step_name='load_facts' ORDER BY run_id DESC LIMIT 1").fetchone()[0] == 0


def test_snapshot_is_readonly(warehouse):
    from dashboard.data import connect_readonly
    import pytest
    with connect_readonly(warehouse[0]) as con:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            con.execute("DELETE FROM fact_inspection")
