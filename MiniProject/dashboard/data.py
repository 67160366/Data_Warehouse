"""Read-only snapshot access; file fingerprints invalidate Streamlit caches."""
import hashlib
import os
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("THREEEYES_DB", ROOT / "data/warehouse/threeeyes_dw.db"))


@st.cache_data(show_spinner=False)
def fingerprint(path, size, modified_ns):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def version(path):
    stat = path.stat()
    return fingerprint(str(path), stat.st_size, stat.st_mtime_ns)


def connect_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


@st.cache_data(show_spinner=False)
def load_snapshot(path, revision):
    with connect_readonly(path) as con:
        facts = pd.read_sql_query("""SELECT f.*,d.full_date,d.period_phase,l.lot_code,l.customer_name,l.production_line,
            df.defect_name,df.is_defect,s.shift_name,i.experience_band
            FROM fact_inspection f JOIN dim_date d USING(date_key) JOIN dim_lot l USING(lot_key)
            JOIN dim_defect df ON df.defect_key=f.true_defect_key JOIN dim_shift s USING(shift_key)
            JOIN dim_inspector i USING(inspector_key)""", con)
        claims = pd.read_sql_query("SELECT * FROM fact_customer_claim", con)
        dates = pd.read_sql_query("SELECT * FROM dim_date", con)
        scenarios = pd.read_sql_query("SELECT * FROM dim_scenario WHERE scenario_key>0 ORDER BY scenario_key", con)
        runs = pd.read_sql_query("SELECT * FROM etl_run_log ORDER BY run_id DESC", con)
    return facts, claims, dates, scenarios, runs


def select(frame, mode, scenario, interval, customers, lines, shifts):
    if len(interval) != 2:
        return frame.iloc[:0].copy()
    return frame[frame.inspection_mode.eq(mode) & frame.scenario_key.eq(scenario)
                 & frame.full_date.between(str(interval[0]), str(interval[1]))
                 & frame.customer_name.isin(customers) & frame.production_line.isin(lines)
                 & frame.shift_name.isin(shifts)].copy()
