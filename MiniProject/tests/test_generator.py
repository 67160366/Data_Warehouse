import pandas as pd
from src.generate_data import make_data, load_config

def small_config():
    c=load_config(); c.update(seed=7,weeks=4,lots=6,lot_size_min=20,lot_size_max=24,inspectors=10,devices=5,hot_lots=1)
    return c

def test_seed_reproducible_and_mode_nulls():
    a=make_data(small_config()); b=make_data(small_config())
    pd.testing.assert_frame_equal(a["fact_inspection"],b["fact_inspection"])
    fact=a["fact_inspection"]
    manual=fact[fact.inspection_mode=="manual"]; assisted=fact[fact.inspection_mode=="assisted"]
    assert manual[["device_key","device_decision","anomaly_score"]].isna().all().all()
    assert assisted.device_decision.notna().all()
    assert fact.groupby(["lot_key","scenario_key"]).size().groupby(level=0).nunique().max()==1
    assert set(a["dim_defect"].defect_key)==set(range(8))
