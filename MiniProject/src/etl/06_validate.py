import json
import hashlib
import pandas as pd
from common import DB_PATH, RAW_PATH, REPORT_PATH, connect, start_run, finish_run, fail_run


def main():
    con = connect()
    run = start_run(con, "validate")
    checks = []
    try:
        latest = con.execute("SELECT * FROM etl_run_log WHERE step_name='load_facts' ORDER BY run_id DESC LIMIT 1").fetchone()
        if latest is None or latest["status"] not in ("success", "partial"):
            raise RuntimeError("No completed fact load to validate")

        def check(name, sql, expected=0):
            actual = con.execute(sql).fetchone()[0]
            checks.append((name, actual, expected, actual == expected))

        check("Foreign key violations", "SELECT COUNT(*) FROM pragma_foreign_key_check")
        check("SQLite integrity", "PRAGMA integrity_check", "ok")
        check("Catch + escape = true defects", "SELECT COUNT(*) FROM fact_lot_summary WHERE defects_caught+defects_escaped<>true_defects")
        check("One date and shift per lot", "SELECT COUNT(*) FROM (SELECT lot_key FROM fact_inspection GROUP BY lot_key HAVING COUNT(DISTINCT date_key)>1 OR COUNT(DISTINCT shift_key)>1)")
        check("Consistent paired truth and factors", """SELECT COUNT(*) FROM (SELECT unit_id FROM fact_inspection GROUP BY unit_id
            HAVING COUNT(DISTINCT true_defect_key)>1 OR COUNT(DISTINCT inspector_key)>1 OR COUNT(DISTINCT hour_in_shift)>1
            OR COUNT(DISTINCT lighting_cond)>1 OR COUNT(DISTINCT lot_key)>1)""")
        check("No inflated lot counts", "SELECT COUNT(*) FROM (SELECT f.lot_key,f.scenario_key,COUNT(*) n,l.lot_size FROM fact_inspection f JOIN dim_lot l USING(lot_key) GROUP BY f.lot_key,f.scenario_key HAVING n>l.lot_size)")
        for table in ("fact_inspection", "fact_customer_claim"):
            raw = con.execute(f"SELECT COUNT(*) FROM stg_{table}").fetchone()[0]
            loaded = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            rejected = con.execute("SELECT COUNT(*) FROM etl_quarantine WHERE run_id=? AND source_table=?", (latest["run_id"], table)).fetchone()[0]
            checks.append((f"{table}: staging = loaded + rejected", f"{raw} = {loaded} + {rejected}", "equal", raw == loaded + rejected))
        check("Run log reconciliation", f"SELECT rows_read-rows_loaded-rows_rejected FROM etl_run_log WHERE run_id={latest['run_id']}")
        if latest["rows_rejected"] == 0:
            check("Clean data: complete lot/scenario counts", "SELECT COUNT(*) FROM fact_lot_summary s JOIN dim_lot l USING(lot_key) WHERE s.units_inspected<>l.lot_size")
            check("Clean data: all assisted units have three scenarios", "SELECT COUNT(*) FROM (SELECT unit_id FROM fact_inspection WHERE inspection_mode='assisted' GROUP BY unit_id HAVING COUNT(DISTINCT scenario_key)<>3)")
        passed = all(x[3] for x in checks)
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("fact_inspection", "fact_customer_claim", "fact_lot_summary")}
        units = con.execute("SELECT COUNT(DISTINCT unit_id) FROM fact_inspection").fetchone()[0]
        lines = ["# Data Quality Report", "", f"Validation status: **{'PASS' if passed else 'FAIL'}**",
                 f"Fact load run: {latest['run_id']}; current rejected rows: {latest['rows_rejected']}.",
                 "Clean data checks run only when the current fact load has no rejects. Historical quarantine is retained.",
                 "", "| Check | Actual | Expected | Status |", "|---|---|---|---|"]
        lines += [f"| {name} | {actual} | {expected} | {'PASS' if ok else 'FAIL'} |" for name, actual, expected, ok in checks]
        lines += ["", f"Inspection rows: {counts['fact_inspection']:,}; distinct physical simulated units: {units:,}.",
                  "Assisted scenario rows must not be summed as production volume."]
        REPORT_PATH.mkdir(parents=True, exist_ok=True)
        (REPORT_PATH / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not passed:
            raise RuntimeError("Data quality validation failed")
        finish_run(con, run_id=run, read=len(checks), loaded=len(checks), message="PASS")
        pd.read_sql_query("SELECT * FROM etl_run_log ORDER BY run_id", con).to_csv(REPORT_PATH / "etl_run_log.csv", index=False, encoding="utf-8-sig")
        metadata_path = RAW_PATH / "generation_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        manifest = {"status": "PASS", "generation": metadata, "fact_load_run": latest["run_id"], "rejected": latest["rows_rejected"],
                    "rows": counts, "distinct_units": units,
                    "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(RAW_PATH.glob('*.csv'))},
                    "database_sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest()}
        (REPORT_PATH / "data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as exc:
        fail_run(con, run, exc)
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
