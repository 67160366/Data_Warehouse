import sqlite3
import pandas as pd
import pytest
from src.metrics import rates, quality_cost, monthly_volume, investment


def sample():
    return pd.DataFrame({"true_defect_key": [1, 1, 0, 0, 0], "final_decision": ["FAIL", "PASS", "PASS", "FAIL", "PASS"],
        "device_decision": ["FAIL", "PASS", "FAIL", "FAIL", "UNCERTAIN"], "inspection_mode": ["assisted"]*5,
        "inspect_seconds": [10]*5, "scenario_key": [2]*5, "lot_key": [1]*5})


def test_hand_calculated_rates_and_zero_denominators():
    frame = sample()
    k = rates(frame)
    assert k["ppm"] == pytest.approx(1e6/3)
    assert k["recall"] == .5
    assert k["false_alarm"] == pytest.approx(2/3)
    assert k["false_reject"] == pytest.approx(1/3)
    assert k["uncertain"] == .2
    assert k["override"] == pytest.approx(1/3)
    assert k["throughput"] == 360
    assert rates(frame.assign(true_defect_key=0))["recall"] is None
    assert rates(frame.assign(final_decision="FAIL"))["ppm"] is None
    assert rates(frame.assign(device_decision="PASS"))["override"] is None
    assert rates(frame.iloc[:0])["ppm"] is None
    assert rates(frame.assign(inspection_mode="manual", device_decision=None))["false_alarm"] is None


def test_cost_ignores_other_scenarios_and_empty_is_missing():
    claims = pd.DataFrame({"lot_key": [1,1], "scenario_key": [2,3], "claim_cost": [12,9999],
                           "rework_cost": [8,9999], "qty_returned": [1,9999]})
    cost = quality_cost(sample(), claims, 360)
    assert cost["total"] == 25
    assert cost["per_unit"] == 5
    assert cost["returned"] == 1
    assert quality_cost(sample().iloc[:0], claims, 360) is None
    with pytest.raises(ValueError):
        quality_cost(pd.concat([sample(), sample().assign(scenario_key=3)]), claims, 360)


def test_investment_table_and_projection_share_formula():
    result = investment(2, 1, 1000, 100, 1800)
    assert result["monthly_saving"] == 900
    assert result["payback"] == 2
    assert result["roi_6m"] == 2
    assert result["minimum_volume"] == 100
    curve = result["projection"].set_index("month")
    assert curve.loc[6, "Manual"] - curve.loc[6, "3Eyes"] == result["net_6m"]
    assert curve.loc[2, "Manual"] == curve.loc[2, "3Eyes"]
    assert investment(1, 2, 1000, 100, 1800)["payback"] is None
    assert investment(1, 2, 1000, 100, 1800)["minimum_volume"] is None
    assert investment(2, 1, 100, 100, 1800)["payback"] is None
    assert investment(2, 1, 1000, 100, 0)["roi_6m"] is None
    assert investment(2, None, 1000, 100, 1800) is None
    assert monthly_volume(9100, "2025-01-06", "2025-04-06") == 3043.75
    assert monthly_volume(100, "2025-01-06", "2025-01-06") == 3043.75


def test_sql_kpi_matches_facts(warehouse):
    with sqlite3.connect(warehouse[0]) as con:
        view = con.execute("SELECT SUM(units_inspected),SUM(true_defects),SUM(caught),SUM(escaped) FROM vw_kpi_weekly WHERE inspection_mode='manual'").fetchone()
        direct = con.execute("SELECT COUNT(*),SUM(true_defect_key<>0),SUM(true_defect_key<>0 AND final_decision='FAIL'),SUM(true_defect_key<>0 AND final_decision='PASS') FROM fact_inspection WHERE inspection_mode='manual'").fetchone()
        assert view == direct
