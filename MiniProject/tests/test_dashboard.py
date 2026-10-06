import shutil
import sqlite3
from datetime import date
import pytest
from streamlit.testing.v1 import AppTest
from conftest import ROOT


def app(db, monkeypatch):
    import dashboard.data as data
    monkeypatch.setattr(data, "DB", db)
    return AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=30).run()


@pytest.mark.parametrize("state", ["normal", "no_defects", "no_pass"])
def test_all_five_pages_and_empty_filters(warehouse, tmp_path, monkeypatch, state):
    db = tmp_path / f"{state}.db"
    shutil.copy2(warehouse[0], db)
    with sqlite3.connect(db) as con:
        if state == "no_defects":
            con.execute("UPDATE fact_inspection SET true_defect_key=0")
        elif state == "no_pass":
            con.execute("UPDATE fact_inspection SET final_decision='FAIL'")
    at = app(db, monkeypatch)
    assert not at.exception
    for page in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
    at.sidebar.multiselect[0].set_value([]).run()
    for page in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
        assert any("ไม่มีข้อมูล" in x.value or "ข้อมูลไม่พอเปรียบเทียบ" in x.value for x in [*at.info, *at.warning])


def test_missing_comparison_sides_and_scenario_selection(warehouse, tmp_path, monkeypatch):
    at = app(warehouse[0], monkeypatch)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[4]).run()
    for scenario in at.sidebar.selectbox[0].options:
        at.sidebar.selectbox[0].set_value(scenario).run()
        assert not at.exception
        assert scenario in at.info[0].value
    for side, day in [("baseline", date(2025, 1, 19)), ("assisted", date(2025, 2, 2))]:
        at = app(warehouse[0], monkeypatch)
        at.sidebar.date_input(key=side).set_value((day, day)).run()
        for page in at.sidebar.radio[0].options[3:]:
            at.sidebar.radio[0].set_value(page).run()
            assert not at.exception
            assert any("ข้อมูลไม่พอเปรียบเทียบ" in x.value for x in at.warning)
            assert len(at.number_input) == 0
