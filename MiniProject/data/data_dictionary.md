# Data Dictionary

All data are deterministic simulations generated with seed 42. Fact grain is one inspected unit per scenario execution; scenario 1–3 reuse the same assisted lot/unit truth set.

## Dimensions

| Table | Columns |
|---|---|
| `dim_date` | `date_key` YYYYMMDD, `full_date`, `year`, `quarter`, `month`, `month_name`, ISO `week_of_year`, Monday-based `day_of_week`, `is_weekend`, `period_phase` (`baseline_manual` / `assisted_3eyes`) |
| `dim_shift` | `shift_key`, `shift_name`, `start_hour`, `end_hour` |
| `dim_inspector` | `inspector_key`, anonymous `inspector_code`, `tenure_years`, `experience_band` |
| `dim_device` | `device_key`, `device_code`, simulated `model_version`, `deployed_date` |
| `dim_lot` | `lot_key`, `lot_code`, `customer_name`, `production_line`, `lot_size`, `production_date` |
| `dim_defect` | `defect_key`, `defect_name`, `defect_group`, `location`, `severity`, `is_defect` (0/1); key 0 is good product |
| `dim_scenario` | `scenario_key` (0 manual, 1–3 assisted), `scenario_name`, `description` |

## Facts

| Table | Grain and columns |
|---|---|
| `fact_inspection` | One unit inspected once in a mode/scenario. `inspection_id`; `date_key`, `shift_key`, `inspector_key`, nullable `device_key`, `lot_key`, `scenario_key`, `true_defect_key`; `inspection_mode`; `hour_in_shift`; `lighting_cond`; nullable `device_decision`, `anomaly_score`, `strictness_level` (NULL for manual); `final_decision`; `override_flag`; `inspect_seconds`. |
| `fact_customer_claim` | One lot × defect × scenario. `claim_id`, `date_key`, `lot_key`, `defect_key`, `scenario_key`, `qty_returned`, `claim_cost`, `rework_cost`. |
| `fact_lot_summary` | Rebuilt mart, one lot × scenario × inspection mode. `lot_key`, `scenario_key`, `inspection_mode`, `units_inspected`, `true_defects`, `defects_caught`, `defects_escaped`, `false_alarms`, `labor_cost`, and combined claim/rework cost. |

## ETL tables

`stg_*` are replace-on-load CSV copies. `etl_run_log` records each step and row counts. `etl_quarantine` stores rejected source rows with reason and run id.
