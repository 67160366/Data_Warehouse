import pandas as pd
from common import RAW_PATH, connect, start_run, finish_run, fail_run

def main():
    con=connect(); run=start_run(con,"load_staging")
    try:
        total=loaded=0
        for path in sorted(RAW_PATH.glob("*.csv")):
            df=pd.read_csv(path)
            total += len(df)
            df.to_sql("stg_"+path.stem,con,if_exists="replace",index=False)
            loaded += len(df)
        finish_run(con,run,total,loaded)
    except Exception as e:
        fail_run(con,run,e); raise
    finally: con.close()

if __name__ == "__main__": main()
