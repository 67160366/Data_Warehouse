import json
import math
import pandas as pd
from common import RAW_PATH, connect, start_run, finish_run, fail_run, record_quarantine

INSPECTION_COLS="inspection_id,date_key,shift_key,inspector_key,device_key,lot_key,scenario_key,true_defect_key,inspection_mode,hour_in_shift,lighting_cond,device_decision,anomaly_score,strictness_level,final_decision,override_flag,inspect_seconds".split(",")
CLAIM_COLS="claim_id,date_key,lot_key,defect_key,scenario_key,qty_returned,claim_cost,rework_cost".split(",")
FK={"date_key":"dim_date","shift_key":"dim_shift","inspector_key":"dim_inspector","device_key":"dim_device","lot_key":"dim_lot","scenario_key":"dim_scenario","true_defect_key":"dim_defect"}

def clean(v):
    if v is None: return None
    try:
        if math.isnan(float(v)): return None
    except (TypeError,ValueError): pass
    if hasattr(v,"item"): return v.item()
    return v

def main():
    con=connect(); run=start_run(con,"load_facts")
    try:
        accepted=[]; rejected=[]
        df=pd.read_csv(RAW_PATH/"fact_inspection.csv")
        dims={col:{r[0] for r in con.execute(f"SELECT {col} FROM {name}")} for col,name in FK.items()}
        for row in df.to_dict("records"):
            row={k:clean(v) for k,v in row.items()}; reason=None
            for key,table in FK.items():
                if row[key] is not None and row[key] not in dims[key]: reason=f"unknown {key}"; break
                if key != "device_key" and row[key] is None: reason=f"missing {key}"; break
            if not reason and row["inspection_mode"]=="manual" and (row["device_key"] is not None or row["device_decision"] is not None or row["anomaly_score"] is not None or row["scenario_key"]!=0): reason="manual device/scenario rule"
            if not reason and row["inspection_mode"]=="assisted" and (row["device_decision"] is None or row["scenario_key"] not in (1,2,3) or row["device_key"] is None): reason="assisted device/scenario rule"
            if not reason and (row["final_decision"] not in ("PASS","FAIL") or row["hour_in_shift"] not in range(1,13) or row["inspect_seconds"] is None or row["inspect_seconds"]<=0): reason="decision/hour/time rule"
            if not reason and row["override_flag"] and row["inspection_mode"]!="assisted": reason="override only allowed when assisted"
            if reason: rejected.append((row,reason))
            else: accepted.append(tuple(row.get(k) for k in INSPECTION_COLS))
        claim_df=pd.read_csv(RAW_PATH/"fact_customer_claim.csv")
        claim_rows=[tuple(clean(row.get(k)) for k in CLAIM_COLS) for row in claim_df.to_dict("records")]
        with con:
            con.execute("DELETE FROM fact_inspection"); con.execute("DELETE FROM fact_customer_claim")
            marks=",".join("?" for _ in INSPECTION_COLS)
            con.executemany(f"INSERT INTO fact_inspection({','.join(INSPECTION_COLS)}) VALUES({marks})",accepted)
            marks=",".join("?" for _ in CLAIM_COLS)
            con.executemany(f"INSERT INTO fact_customer_claim({','.join(CLAIM_COLS)}) VALUES({marks})",claim_rows)
            for row,reason in rejected: record_quarantine(con,run,"fact_inspection",row,reason)
        finish_run(con,len(df)+len(claim_df),len(accepted)+len(claim_rows),len(rejected),f"quarantined inspection rows: {len(rejected)}")
    except Exception as e: fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
