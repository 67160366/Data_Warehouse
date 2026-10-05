from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data/warehouse/threeeyes_dw.db"
RAW_PATH = ROOT / "data/raw"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def start_run(con, step):
    cur = con.execute("INSERT INTO etl_run_log(started_at,step_name,status) VALUES(?,?,?)",
                      (datetime.now(timezone.utc).isoformat(), step, "success"))
    con.commit()
    return cur.lastrowid

def finish_run(con, run_id, read, loaded, rejected=0, message=""):
    status = "partial" if rejected else "success"
    con.execute("UPDATE etl_run_log SET finished_at=?,rows_read=?,rows_loaded=?,rows_rejected=?,status=?,message=? WHERE run_id=?",
                (datetime.now(timezone.utc).isoformat(), read, loaded, rejected, status, message, run_id))
    con.commit()

def fail_run(con, run_id, exc):
    con.rollback()
    con.execute("UPDATE etl_run_log SET finished_at=?,status='failed',message=? WHERE run_id=?",
                (datetime.now(timezone.utc).isoformat(), str(exc), run_id))
    con.commit()

def record_quarantine(con, run_id, table, row, reason):
    con.execute("INSERT INTO etl_quarantine(run_id,source_table,raw_row_json,reject_reason,created_at) VALUES(?,?,?,?,?)",
                (run_id, table, json.dumps(row, ensure_ascii=False, default=str), reason, datetime.now(timezone.utc).isoformat()))
