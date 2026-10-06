"""Shared, pure KPI and investment formulas. Undefined rates remain None."""
from __future__ import annotations
import math
import pandas as pd


def divide(numerator, denominator):
    return float(numerator / denominator) if denominator else None


def rates(frame):
    defective = frame.true_defect_key.ne(0)
    failed = frame.final_decision.eq("FAIL")
    good = ~defective
    assisted = frame.inspection_mode.eq("assisted")
    device_fail = frame.device_decision.eq("FAIL") & assisted
    counts = {
        "units": len(frame), "defects": int(defective.sum()), "good": int(good.sum()),
        "caught": int((defective & failed).sum()), "escaped": int((defective & ~failed).sum()),
        "passed": int((~failed).sum()), "final_false_rejects": int((good & failed).sum()),
        "assisted": int(assisted.sum()), "assisted_good": int((assisted & good).sum()),
        "device_false_alarms": int((good & device_fail).sum()), "device_fail": int(device_fail.sum()),
        "uncertain_count": int((assisted & frame.device_decision.eq("UNCERTAIN")).sum()),
        "overrides": int((device_fail & ~failed).sum()),
    }
    ratios = {"ppm": ("escaped", "passed"), "recall": ("caught", "defects"),
              "false_reject": ("final_false_rejects", "good"),
              "false_alarm": ("device_false_alarms", "assisted_good"),
              "uncertain": ("uncertain_count", "assisted"), "override": ("overrides", "device_fail"),
              "defect_rate": ("defects", "units")}
    result = counts.copy()
    for key, (num, den) in ratios.items():
        result[key] = divide(counts[num], counts[den])
    if result["ppm"] is not None:
        result["ppm"] *= 1e6
    result["avg_seconds"] = float(frame.inspect_seconds.mean()) if len(frame) else None
    result["throughput"] = divide(3600, result["avg_seconds"])
    return result


def quality_cost(frame, claims, labor_per_hour):
    """Complete lots only; filters are date, lot customer/line and lot shift."""
    if frame.empty:
        return None
    if frame.scenario_key.nunique() != 1 or frame.inspection_mode.nunique() != 1:
        raise ValueError("Select one mode/scenario; never sum assisted alternatives")
    matching = claims[claims.lot_key.isin(frame.lot_key.unique()) & claims.scenario_key.eq(frame.scenario_key.iloc[0])]
    claim = float(matching.claim_cost.sum())
    rework = float(matching.rework_cost.sum())
    labor = float(frame.inspect_seconds.sum() * labor_per_hour / 3600)
    total = claim + rework + labor
    return {"claim": claim, "rework": rework, "labor": labor, "total": total,
            "per_unit": total / len(frame), "returned": int(matching.qty_returned.sum())}


def monthly_volume(units, start, end):
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    if days <= 0:
        raise ValueError("Invalid baseline interval")
    return units * 30.4375 / days


def investment(manual_per, assisted_per, volume, subscription, capital):
    if manual_per is None or assisted_per is None:
        return None
    if any(not math.isfinite(x) or x < 0 for x in (manual_per, assisted_per, volume, subscription, capital)):
        raise ValueError("Investment inputs must be finite and nonnegative")
    benefit = manual_per - assisted_per
    saving = benefit * volume - subscription
    net = saving * 6 - capital
    return {"monthly_saving": saving, "net_6m": net, "roi_6m": divide(net, capital),
            "payback": capital / saving if saving > 0 else None,
            "minimum_volume": subscription / benefit if benefit > 0 else None,
            "projection": pd.DataFrame({"month": range(25),
                "Manual": [manual_per * volume * m for m in range(25)],
                "3Eyes": [capital + (assisted_per * volume + subscription) * m for m in range(25)]})}
