from pathlib import Path
import pandas as pd
from common import ROOT, connect, start_run, finish_run, fail_run

def main():
    con=connect(); run=start_run(con,"validate")
    checks=[]
    try:
        def check(name,sql,expect=0):
            value=con.execute(sql).fetchone()[0]
            checks.append((name,value,expect,value==expect))
        check("Foreign key violations","SELECT COUNT(*) FROM pragma_foreign_key_check")
        check("Duplicate inspection ids","SELECT COUNT(*) FROM (SELECT inspection_id FROM fact_inspection GROUP BY inspection_id HAVING COUNT(*)>1)")
        check("Invalid lot counts","SELECT COUNT(*) FROM (SELECT f.lot_key,f.scenario_key,COUNT(*) n,l.lot_size FROM fact_inspection f JOIN dim_lot l USING(lot_key) GROUP BY f.lot_key,f.scenario_key HAVING n>l.lot_size)")
        check("Catch/escape reconciliation","SELECT COUNT(*) FROM fact_lot_summary WHERE defects_caught+defects_escaped<>true_defects")
        check("Manual/assisted scenario consistency","SELECT COUNT(*) FROM fact_inspection WHERE (inspection_mode='manual' AND scenario_key<>0) OR (inspection_mode='assisted' AND scenario_key=0)")
        check("Inspection rows in quarantine","SELECT COUNT(*) FROM etl_quarantine",0)
        source_rows=sum(int(con.execute(f"SELECT COUNT(*) FROM stg_{t}").fetchone()[0]) for t in ["fact_inspection","fact_customer_claim"] if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(f"stg_{t}",)).fetchone())
        loaded=con.execute("SELECT (SELECT COUNT(*) FROM fact_inspection)+(SELECT COUNT(*) FROM fact_customer_claim)").fetchone()[0]
        checks.append(("Raw fact reconciliation",f"{loaded}/{source_rows}","equal",loaded==source_rows))
        passed=all(c[3] for c in checks)
        lines=["# Data Quality Report","",f"Validation status: **{'PASS' if passed else 'FAIL'}**","", "| Check | Result | Expected | Status |","|---|---:|---:|---|"]
        lines += [f"| {n} | {v} | {e} | {'PASS' if ok else 'FAIL'} |" for n,v,e,ok in checks]
        lines += ["",f"Quarantine rows: {con.execute('SELECT COUNT(*) FROM etl_quarantine').fetchone()[0]}"]
        (ROOT/"reports/data_quality_report.md").parent.mkdir(parents=True,exist_ok=True)
        (ROOT/"reports/data_quality_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        finish_run(con,len(checks),sum(int(x[3]) for x in checks),0,"PASS" if passed else "FAIL")
        pd.read_sql_query("SELECT * FROM etl_run_log ORDER BY run_id",con).to_csv(ROOT/"reports/etl_run_log.csv",index=False,encoding="utf-8")
        if not passed: raise RuntimeError("Data quality validation failed; see reports/data_quality_report.md")
    except Exception as e: fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
