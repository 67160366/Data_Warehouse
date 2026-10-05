"""Cross-platform command runner: setup, data, etl, test, app, all."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STEPS=["src/etl/01_create_schema.py","src/etl/02_load_staging.py","src/etl/03_load_dimensions.py",
       "src/etl/04_load_facts.py","src/etl/05_build_marts.py","src/etl/06_validate.py"]
def run(*args): subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,check=True)
def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["setup","data","etl","test","app","all"]); p.add_argument("--reset",action="store_true"); a=p.parse_args()
    if a.command=="setup": subprocess.run([sys.executable,"-m","pip","install","-r","requirements.txt"],cwd=ROOT,check=True)
    elif a.command=="data": run("src/generate_data.py")
    elif a.command=="etl":
        for step in STEPS: run(step,*(["--reset"] if a.reset and step==STEPS[0] else []))
    elif a.command=="test": run("-m","pytest","tests","-q")
    elif a.command=="app": subprocess.run([sys.executable,"-m","streamlit","run","dashboard/app.py"],cwd=ROOT,check=True)
    else:
        run("src/generate_data.py"); run(STEPS[0],"--reset")
        for step in STEPS[1:]: run(step)
        run("-m","pytest","tests","-q")
if __name__=="__main__": main()
