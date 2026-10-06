import os
from pathlib import Path
import subprocess
import sys
import pytest
from src.generate_data import make_data, load_config

ROOT = Path(__file__).resolve().parents[1]


def small_config():
    c = load_config()
    c.update(seed=42, weeks=4, lots=12, lot_size_min=80, lot_size_max=100, hot_lots=1)
    return c


def run_etl(db, raw, reports, step=None):
    env = dict(os.environ, THREEEYES_DB=str(db), THREEEYES_RAW=str(raw), THREEEYES_REPORTS=str(reports))
    args = [sys.executable, str(ROOT / step)] if step else [sys.executable, str(ROOT / "run.py"), "etl"]
    subprocess.run(args, cwd=ROOT, env=env, check=True, capture_output=True, text=True)


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory):
    folder = tmp_path_factory.mktemp("warehouse")
    raw = folder / "raw"
    raw.mkdir()
    data = make_data(small_config())
    for name, frame in data.items():
        frame.to_csv(raw / f"{name}.csv", index=False, encoding="utf-8-sig")
    db = folder / "test.db"
    reports = folder / "reports"
    run_etl(db, raw, reports)
    return db, raw, reports
