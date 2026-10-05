import sqlite3
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"data/warehouse/threeeyes_dw.db"

def test_weekly_kpi_matches_direct_aggregation():
    if not DB.exists(): pytest.skip("Run `python run.py all` to build the warehouse")
    with sqlite3.connect(DB) as con:
        view=con.execute("SELECT SUM(units_inspected),SUM(true_defects),SUM(caught),SUM(escaped) FROM vw_kpi_weekly WHERE inspection_mode='manual' AND scenario_key=0").fetchone()
        direct=con.execute("""SELECT COUNT(*),SUM(true_defect_key<>0),SUM(true_defect_key<>0 AND final_decision='FAIL'),SUM(true_defect_key<>0 AND final_decision='PASS') FROM fact_inspection WHERE inspection_mode='manual' AND scenario_key=0""").fetchone()
        scenario_counts=con.execute("SELECT scenario_key,COUNT(*) FROM fact_inspection WHERE inspection_mode='assisted' GROUP BY scenario_key ORDER BY scenario_key").fetchall()
    assert view==direct
    assert len({n for _,n in scenario_counts})==1
    assert [s for s,_ in scenario_counts]==[1,2,3]
