import pandas as pd
from common import RAW_PATH, connect, start_run, finish_run, fail_run

def main():
    con=connect(); run=start_run(con,"load_staging")
    try:
        total=loaded=0
        names = ["dim_date", "dim_shift", "dim_inspector", "dim_device", "dim_lot", "dim_defect", "dim_scenario", "fact_inspection", "fact_customer_claim"]
        paths = [RAW_PATH / f"{name}.csv" for name in names]
        if not all(path.exists() for path in paths):
            raise ValueError("All seven dimensions and two fact CSVs are required")
        for path in paths:
            df=pd.read_csv(path, keep_default_na=False, na_values=[""])
            total += len(df)
            df.to_sql("stg_"+path.stem,con,if_exists="replace",index=False)
            loaded += len(df)
        finish_run(con,run,total,loaded)
    except Exception as e:
        fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
