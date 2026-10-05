import pandas as pd
from common import ROOT, connect, start_run, finish_run, fail_run

def main():
    con=connect(); run=start_run(con,"build_marts")
    try:
        assumptions=pd.read_csv(ROOT/"config/assumptions.csv").set_index("param").value.astype(float).to_dict()
        rate=assumptions["labor_cost_per_hour"]/3600
        with con:
            con.execute("DELETE FROM fact_lot_summary")
            con.execute("""INSERT INTO fact_lot_summary
            SELECT f.lot_key,f.scenario_key,f.inspection_mode,COUNT(*),
              SUM(f.true_defect_key<>0),SUM(f.true_defect_key<>0 AND f.final_decision='FAIL'),
              SUM(f.true_defect_key<>0 AND f.final_decision='PASS'),
              SUM(f.true_defect_key=0 AND f.final_decision='FAIL'),
              SUM(f.inspect_seconds)*?,COALESCE(c.claim_cost,0)+COALESCE(c.rework_cost,0)
            FROM fact_inspection f LEFT JOIN (
              SELECT lot_key,scenario_key,SUM(claim_cost) claim_cost,SUM(rework_cost) rework_cost
              FROM fact_customer_claim GROUP BY lot_key,scenario_key
            ) c ON c.lot_key=f.lot_key AND c.scenario_key=f.scenario_key
            GROUP BY f.lot_key,f.scenario_key,f.inspection_mode""",(rate,))
            con.executescript((ROOT/"src/sql/kpi_views.sql").read_text(encoding="utf-8"))
        count=con.execute("SELECT COUNT(*) FROM fact_lot_summary").fetchone()[0]
        finish_run(con,count,count)
    except Exception as e: fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
