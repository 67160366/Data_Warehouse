import pandas as pd
from src.generate_data import make_data
from conftest import small_config


def test_seed_pairing_and_grain():
    a, b = make_data(small_config()), make_data(small_config())
    for table in a:
        pd.testing.assert_frame_equal(a[table], b[table])
    fact = a["fact_inspection"]
    manual = fact[fact.inspection_mode.eq("manual")]
    assisted = fact[fact.inspection_mode.eq("assisted")]
    assert manual[["device_key", "device_decision"]].isna().all().all()
    assert assisted.device_decision.notna().all()
    assert fact.hour_in_shift.between(1, 8).all()
    assert not fact.duplicated(["unit_id", "inspection_mode", "scenario_key"]).any()
    assert assisted.groupby("unit_id").scenario_key.nunique().eq(3).all()
    assert assisted.groupby("unit_id")[["true_defect_key", "inspector_key", "hour_in_shift", "lighting_cond", "device_key"]].nunique().eq(1).all().all()
    assert fact.groupby("lot_key")[["date_key", "shift_key"]].nunique().eq(1).all().all()
    assert fact.unit_id.nunique() == a["dim_lot"].lot_size.sum()
    assert a["dim_lot"].groupby("customer_name").production_line.nunique().max() > 1
    assert set(a["dim_defect"].defect_key) == set(range(8))


def test_defect_mean_and_confirmation_time_are_effective():
    low = small_config()
    low.update(defect_rate_mean=.001, hot_lots=0)
    high = dict(low, defect_rate_mean=.7)
    assert make_data(high)["fact_inspection"].true_defect_key.ne(0).mean() > .5
    assert make_data(low)["fact_inspection"].true_defect_key.ne(0).mean() < .02
    from src.generate_data import load_assumptions
    a = load_assumptions()
    normal = make_data(low, a)["fact_inspection"]
    a["confirmation_seconds"] = 0
    zero = make_data(low, a)["fact_inspection"]
    expected = normal.device_decision.isin(["FAIL", "UNCERTAIN"]).astype(int) * 5
    assert ((normal.inspect_seconds - zero.inspect_seconds - expected).abs() < 1e-10).all()
