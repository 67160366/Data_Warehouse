"""Create deterministic, explicitly simulated 3Eyes data in CSV form."""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFECTS = [
    (0, "งานดี", "ดี", "ไม่มีตำหนิ", "none", 0),
    (1, "บ่ากระแทก", "บ่า-หัว", "บ่า/หน้าแปลนใต้หัว", "minor", 1),
    (2, "แชฟเฟอร์กระแทก", "ผิวเกลียว", "มุมลบคมปลายเกลียว", "minor", 1),
    (3, "เกลียวกระแทก", "ผิวเกลียว", "ผิวเกลียว", "major", 1),
    (4, "เกลียวรูด", "ผิวเกลียว", "เกลียวเสียรูป", "critical", 1),
    (5, "เหลี่ยมเป็นรอย", "หกเหลี่ยม", "ผิวหกเหลี่ยม", "minor", 1),
    (6, "เหลี่ยมเสีย", "หกเหลี่ยม", "หกเหลี่ยมผิดรูป", "major", 1),
    (7, "สนิม", "ทั่วผิว", "ทั่วผิว", "major", 1),
]
DEFECT_WEIGHTS = np.array([.15, .10, .20, .08, .15, .07, .25])
BASE_RECALL = np.array([.78, .75, .82, .65, .80, .90, .70])


def load_config():
    with (ROOT / "config/generator_params.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_assumptions():
    frame = pd.read_csv(ROOT / "config/assumptions.csv")
    if frame.source.isna().any() or (frame.source.astype(str).str.strip() == "").any():
        raise ValueError("Every assumption must have a source (use ASSUMPTION where appropriate).")
    return dict(zip(frame.param, frame.value.astype(float)))


def make_data(config=None, assumptions=None):
    c = config or load_config()
    a = assumptions or load_assumptions()
    rng = np.random.default_rng(c["seed"])
    start = date(2025, 1, 6)
    weeks = c["weeks"]
    week_starts = [start + timedelta(days=7 * i) for i in range(weeks)]
    dates = [start + timedelta(days=i) for i in range(weeks * 7)]
    n_lots = c["lots"]
    hot = set(rng.choice(np.arange(1, n_lots + 1), size=min(c["hot_lots"], n_lots), replace=False).tolist())

    date_rows = []
    for d in dates:
        phase = "baseline_manual" if (d - start).days < 7 * (weeks // 2) else "assisted_3eyes"
        date_rows.append(dict(date_key=int(d.strftime("%Y%m%d")), full_date=d.isoformat(), year=d.year,
                              quarter=(d.month - 1) // 3 + 1, month=d.month, month_name=d.strftime("%B"),
                              week_of_year=int(d.isocalendar().week), day_of_week=d.isoweekday(),
                              is_weekend=int(d.weekday() >= 5), period_phase=phase))
    dim_date = pd.DataFrame(date_rows)
    dim_shift = pd.DataFrame([
        {"shift_key": 1, "shift_name": "เช้า", "start_hour": 6, "end_hour": 14},
        {"shift_key": 2, "shift_name": "บ่าย", "start_hour": 14, "end_hour": 22},
        {"shift_key": 3, "shift_name": "ดึก", "start_hour": 22, "end_hour": 6},
    ])
    tenure = np.array([.4, .7, 1.2, 1.8, 2.4, 3.2, 4.1, 5.0, 6.2, 7.0])[:c["inspectors"]]
    dim_inspector = pd.DataFrame([{"inspector_key": i + 1, "inspector_code": f"QC-{i+1:03}",
        "tenure_years": float(t), "experience_band": "<1 ปี" if t < 1 else ("1-3 ปี" if t <= 3 else ">3 ปี")}
        for i, t in enumerate(tenure)])
    dim_device = pd.DataFrame([{"device_key": i + 1, "device_code": f"3EYES-{i+1:02}",
        "model_version": "SIM-1.0", "deployed_date": week_starts[weeks // 2].isoformat()} for i in range(c["devices"])])
    dim_defect = pd.DataFrame(DEFECTS, columns=["defect_key", "defect_name", "defect_group", "location", "severity", "is_defect"])
    scenarios = [{"scenario_key": 0, "scenario_name": "N/A", "description": "Manual baseline"}]
    scenarios += [{"scenario_key": s["key"], "scenario_name": s["name"],
                   "description": "สถานการณ์จำลอง ไม่ใช่ผลทดสอบ"} for s in c["scenarios"]]
    dim_scenario = pd.DataFrame(scenarios)

    lots, inspections, claims = [], [], []
    inspection_id = claim_id = 1
    half = weeks // 2
    for lot_idx in range(1, n_lots + 1):
        assisted = lot_idx > n_lots // 2
        local = lot_idx - n_lots // 2 - 1 if assisted else lot_idx - 1
        week_idx = min(weeks - 1, (half if assisted else 0) + int(local * half / max(1, n_lots // 2)))
        day = week_starts[week_idx] + timedelta(days=int(rng.integers(0, 5)))
        lot_size = int(rng.integers(c["lot_size_min"], c["lot_size_max"] + 1))
        lot_code = f"LOT-{lot_idx:04}"
        customer = ["ลูกค้า A", "ลูกค้า B", "ลูกค้า C"][int(rng.integers(0, 3))]
        line = ["LINE-1", "LINE-2", "LINE-3"][lot_idx % 3]
        lots.append({"lot_key": lot_idx, "lot_code": lot_code, "customer_name": customer,
                     "production_line": line, "lot_size": lot_size, "production_date": day.isoformat()})
        defect_rate = float(rng.beta(c["defect_rate_mean"] * 67, (1-c["defect_rate_mean"]) * 67))
        if lot_idx in hot:
            defect_rate = float(rng.uniform(.08, .14))
        defect_keys = np.zeros(lot_size, dtype=int)
        defective = rng.random(lot_size) < defect_rate
        defect_keys[defective] = rng.choice(np.arange(1, 8), size=int(defective.sum()), p=DEFECT_WEIGHTS)
        shift_key = int(rng.integers(1, 4))
        lots[-1]["shift_key"] = shift_key
        hours = rng.integers(1, 9, size=lot_size)
        inspector_keys = rng.integers(1, len(dim_inspector) + 1, size=lot_size)
        lighting = rng.choice(["good", "dim", "glare"], size=lot_size, p=[.65, .2, .15])
        # Pair truth, human behavior, timing and random draws across scenarios.
        human_draw, reject_draw, uncertain_draw, device_draw, confirm_draw, rescue_draw = rng.random((6, lot_size))
        base_seconds = rng.lognormal(np.log(6.8 if assisted else 8.0), .24, lot_size)
        assigned_devices = rng.integers(1, len(dim_device) + 1, size=lot_size)
        claim_draw = rng.uniform(1-c["claim_noise"], 1+c["claim_noise"], 8)
        for scenario in ([None] if not assisted else c["scenarios"]):
            skey = 0 if scenario is None else scenario["key"]
            mode = "manual" if scenario is None else "assisted"
            final = np.zeros(lot_size, dtype=int)
            good = defect_keys == 0
            fatigue = np.clip(1 - np.maximum(hours - 4, 0) * .025 - (shift_key == 3) * .06, .55, 1)
            experience = np.array([.88 if t < 1 else (1.0 if t <= 3 else 1.06) for t in tenure])[inspector_keys - 1]
            light_factor = np.select([lighting == "dim", lighting == "glare"], [.9, .88], default=1.0)
            human_prob = np.zeros(lot_size)
            mask = ~good
            human_prob[mask] = BASE_RECALL[defect_keys[mask] - 1] * fatigue[mask] * experience[mask] * light_factor[mask]
            human_catches = human_draw < human_prob
            dev_decision = np.full(lot_size, None, dtype=object)
            override = np.zeros(lot_size, dtype=int)
            if mode == "manual":
                final[mask] = human_catches[mask]
                final[good] = (reject_draw[good] < .015)
                seconds = base_seconds.copy()
                device_keys = np.full(lot_size, np.nan)
            else:
                uncertain_p = scenario["uncertain_rate"]
                uncertain = uncertain_draw < uncertain_p
                device_fail = np.zeros(lot_size, dtype=bool)
                # Conditional recall among non-uncertain defective items.
                dm = mask & ~uncertain
                device_fail[dm] = device_draw[dm] < min(.995, scenario["device_recall"] / (1 - uncertain_p))
                gm = good & ~uncertain
                device_fail[gm] = device_draw[gm] < scenario["false_alarm"] / (1 - uncertain_p)
                dev_decision[:] = "PASS"
                dev_decision[uncertain] = "UNCERTAIN"
                dev_decision[device_fail] = "FAIL"
                # FAIL recommendations are mostly confirmed; rare override can release a defect.
                confirm = confirm_draw < .94
                final[device_fail] = confirm[device_fail]
                override[device_fail & ~confirm] = 1
                final[uncertain] = human_catches[uncertain]
                final[good & uncertain] = reject_draw[good & uncertain] < .015
                # Human can occasionally catch a device PASS missed defect.
                missed = mask & ~device_fail & ~uncertain
                final[missed] = rescue_draw[missed] < (human_prob[missed] * .18)
                final[good & ~device_fail & ~uncertain] = 0
                seconds = base_seconds + (device_fail | uncertain) * a["confirmation_seconds"]
                device_keys = assigned_devices
            rows = []
            for i in range(lot_size):
                rows.append({"inspection_id": inspection_id, "unit_id": f"{lot_code}-{i+1:04}", "date_key": int(day.strftime("%Y%m%d")),
                    "shift_key": shift_key, "inspector_key": int(inspector_keys[i]),
                    "device_key": None if mode == "manual" else int(device_keys[i]), "lot_key": lot_idx,
                    "scenario_key": skey, "true_defect_key": int(defect_keys[i]), "inspection_mode": mode,
                    "hour_in_shift": int(hours[i]), "lighting_cond": str(lighting[i]),
                    "device_decision": None if mode == "manual" else str(dev_decision[i]),
                    "final_decision": "FAIL" if final[i] else "PASS", "override_flag": int(override[i]),
                    "inspect_seconds": float(seconds[i])})
                inspection_id += 1
            inspections.extend(rows)
            # At most one claim row per defective defect type in each lot/scenario.
            escaped = {}
            for row in rows:
                if row["true_defect_key"] and row["final_decision"] == "PASS":
                    escaped[row["true_defect_key"]] = escaped.get(row["true_defect_key"], 0) + 1
            for dkey, qty in escaped.items():
                returned = min(qty, max(0, int(round(qty * a["customer_detection_rate"] * claim_draw[dkey]))))
                claims.append({"claim_id": claim_id, "date_key": int(day.strftime("%Y%m%d")), "lot_key": lot_idx,
                    "defect_key": dkey, "scenario_key": skey, "qty_returned": returned,
                    "claim_cost": returned * a["claim_cost_per_returned_unit"],
                    "rework_cost": returned * a["rework_cost_per_returned_unit"]})
                claim_id += 1
    dim_lot = pd.DataFrame(lots)
    return {"dim_date": dim_date, "dim_shift": dim_shift, "dim_inspector": dim_inspector,
            "dim_device": dim_device, "dim_lot": dim_lot, "dim_defect": dim_defect,
            "dim_scenario": dim_scenario, "fact_inspection": pd.DataFrame(inspections),
            "fact_customer_claim": pd.DataFrame(claims, columns=["claim_id", "date_key", "lot_key", "defect_key", "scenario_key", "qty_returned", "claim_cost", "rework_cost"])}


def generate(out_dir=None):
    out = Path(out_dir) if out_dir else ROOT / "data/raw"
    out.mkdir(parents=True, exist_ok=True)
    data = make_data()
    for name, frame in data.items():
        frame.to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
    (out / "generation_metadata.json").write_text(json.dumps({"config": load_config(), "assumptions": load_assumptions()},
                                                           ensure_ascii=False, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "data/raw")
    args = parser.parse_args()
    result = generate(args.out)
    print("Generated " + ", ".join(f"{k}={len(v):,}" for k, v in result.items()))
