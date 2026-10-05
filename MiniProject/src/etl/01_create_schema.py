from common import ROOT, connect

def main(reset=False):
    if reset and (ROOT / "data/warehouse/threeeyes_dw.db").exists():
        (ROOT / "data/warehouse/threeeyes_dw.db").unlink()
    con = connect()
    con.executescript((ROOT / "src/schema.sql").read_text(encoding="utf-8"))
    con.commit(); con.close()

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--reset", action="store_true"); main(p.parse_args().reset)
