from common import ROOT, DB_PATH, connect

def main(reset=False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    con = connect()
    con.executescript((ROOT / "src/schema.sql").read_text(encoding="utf-8"))
    con.commit(); con.close()

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--reset", action="store_true"); main(p.parse_args().reset)
