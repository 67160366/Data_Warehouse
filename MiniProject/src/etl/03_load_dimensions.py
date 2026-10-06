import pandas as pd
from common import RAW_PATH, connect, start_run, finish_run, fail_run

TABLES={"dim_date":"date_key","dim_shift":"shift_key","dim_inspector":"inspector_key","dim_device":"device_key","dim_lot":"lot_key","dim_defect":"defect_key","dim_scenario":"scenario_key"}
def main():
    con=connect(); run=start_run(con,"load_dimensions")
    try:
        total=loaded=0
        with con:
            for table,key in TABLES.items():
                df=pd.read_sql_query(f"SELECT * FROM stg_{table}", con)
                total+=len(df)
                if df[key].duplicated().any(): raise ValueError(f"duplicate {key} in {table}")
                cols=list(df.columns); marks=",".join("?" for _ in cols)
                updates=",".join(f"{col}=excluded.{col}" for col in cols if col != key)
                sql=f"INSERT INTO {table}({','.join(cols)}) VALUES({marks}) ON CONFLICT({key}) DO UPDATE SET {updates}"
                con.executemany(sql,df.itertuples(index=False,name=None)); loaded+=len(df)
        finish_run(con,run,total,loaded)
    except Exception as e: fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
