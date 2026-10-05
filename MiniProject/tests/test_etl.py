import sqlite3
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"data/warehouse/threeeyes_dw.db"

def test_etl_is_repeatable():
    if not DB.exists():
        subprocess.run([sys.executable,"run.py","all"],cwd=ROOT,check=True)
    with sqlite3.connect(DB) as con:
        before=con.execute("SELECT COUNT(*),SUM(true_defects),SUM(defects_escaped) FROM fact_lot_summary").fetchone()
    subprocess.run([sys.executable,"run.py","etl"],cwd=ROOT,check=True)
    with sqlite3.connect(DB) as con:
        after=con.execute("SELECT COUNT(*),SUM(true_defects),SUM(defects_escaped) FROM fact_lot_summary").fetchone()
        fk=con.execute("SELECT COUNT(*) FROM pragma_foreign_key_check").fetchone()[0]
    assert before==after
    assert fk==0
