"""Replace facts from staging, quarantining invalid rows with explicit reasons."""
import math
import sqlite3
from common import connect, start_run, finish_run, fail_run, record_quarantine

FK = {
    "date_key": ("dim_date", "date_key"), "shift_key": ("dim_shift", "shift_key"),
    "inspector_key": ("dim_inspector", "inspector_key"), "device_key": ("dim_device", "device_key"),
    "lot_key": ("dim_lot", "lot_key"), "scenario_key": ("dim_scenario", "scenario_key"),
    "true_defect_key": ("dim_defect", "defect_key"), "defect_key": ("dim_defect", "defect_key"),
}


def reason_for(row, table, columns, dims, lots, phases):
    for col in columns:
        value = row.get(col[1])
        if (col[3] or col[5]) and (value is None or str(value).strip() == ""):
            return f"missing {col[1]}"
        if value is not None and col[2] in ("INTEGER", "REAL"):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                return f"invalid numeric {col[1]}"
            if col[2] == "INTEGER" and int(value) != value:
                return f"non-integer {col[1]}"
    for key in row.keys() & dims.keys():
        if row[key] is not None and row[key] not in dims[key]:
            return f"unknown {key}"
    lot = lots[row["lot_key"]]
    if int(row["date_key"]) != int(lot["production_date"].replace("-", "")):
        return "date must match lot production date"
    if (row["scenario_key"] == 0) != (phases[row["date_key"]] == "baseline_manual"):
        return "scenario must match baseline/assisted date phase"
    if table == "fact_inspection":
        mode = row["inspection_mode"]
        if mode == "manual" and (row["scenario_key"] != 0 or row["device_key"] is not None or row["device_decision"] is not None):
            return "manual device/scenario rule"
        if mode == "assisted" and (row["scenario_key"] == 0 or row["device_key"] is None or row["device_decision"] is None):
            return "assisted device/scenario rule"
        expected_override = int(row["device_decision"] == "FAIL" and row["final_decision"] == "PASS")
        if row["override_flag"] != expected_override:
            return "override must mean device FAIL changed to final PASS"
        if row["shift_key"] != lot["shift_key"]:
            return "shift must match lot shift"
    elif row["defect_key"] == 0:
        return "claims must refer to a defect"
    return None


def main():
    con = connect()
    run = start_run(con, "load_facts")
    try:
        dims = {col: {r[0] for r in con.execute(f"SELECT {key} FROM {table}")}
                for col, (table, key) in FK.items()}
        lots = {r["lot_key"]: dict(r) for r in con.execute("SELECT * FROM dim_lot")}
        phases = dict(con.execute("SELECT date_key,period_phase FROM dim_date"))
        total = loaded = rejected = 0
        with con:
            con.execute("DELETE FROM fact_lot_summary")
            con.execute("DELETE FROM fact_customer_claim")
            con.execute("DELETE FROM fact_inspection")
            for table in ("fact_inspection", "fact_customer_claim"):
                columns = con.execute(f"PRAGMA table_info({table})").fetchall()
                names = [col[1] for col in columns]
                sql = f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})"
                for source in con.execute(f"SELECT * FROM stg_{table}").fetchall():
                    row = dict(source)
                    total += 1
                    reason = reason_for(row, table, columns, dims, lots, phases)
                    if not reason and table == "fact_customer_claim":
                        escaped = con.execute("""SELECT COUNT(*) FROM fact_inspection
                            WHERE lot_key=? AND scenario_key=? AND true_defect_key=? AND final_decision='PASS'""",
                            (row["lot_key"], row["scenario_key"], row["defect_key"])).fetchone()[0]
                        claimed = con.execute("""SELECT COALESCE(SUM(qty_returned),0) FROM fact_customer_claim
                            WHERE lot_key=? AND scenario_key=? AND defect_key=?""",
                            (row["lot_key"], row["scenario_key"], row["defect_key"])).fetchone()[0]
                        if row["qty_returned"] + claimed > escaped:
                            reason = "returned quantity exceeds escaped defects"
                    if not reason:
                        try:
                            con.execute(sql, [row.get(k) for k in names])
                        except sqlite3.IntegrityError as exc:
                            reason = str(exc)
                    if reason:
                        record_quarantine(con, run, table, row, reason)
                        rejected += 1
                    else:
                        loaded += 1
        finish_run(con, run_id=run, read=total, loaded=loaded, rejected=rejected,
                   message="staging = loaded + quarantined; both facts validated")
    except Exception as exc:
        fail_run(con, run, exc)
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
