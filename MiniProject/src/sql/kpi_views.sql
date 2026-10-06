DROP VIEW IF EXISTS vw_kpi_weekly;
CREATE VIEW vw_kpi_weekly AS
SELECT d.year,d.week_of_year,d.period_phase,f.inspection_mode,f.scenario_key,
 COUNT(*) units_inspected,
 SUM(f.true_defect_key<>0) true_defects,
 SUM(f.true_defect_key<>0 AND f.final_decision='FAIL') caught,
 SUM(f.true_defect_key<>0 AND f.final_decision='PASS') escaped,
 SUM(f.true_defect_key=0 AND f.final_decision='FAIL') final_false_rejects,
 SUM(f.true_defect_key=0 AND f.device_decision='FAIL') device_false_alarms,
 SUM(f.true_defect_key=0) good_units,SUM(f.final_decision='PASS') passed_units,
 SUM(COALESCE(f.device_decision='UNCERTAIN',0)) uncertain_units,
 SUM(COALESCE(f.device_decision='FAIL',0)) device_fail_units,SUM(f.override_flag) overrides,
 AVG(f.inspect_seconds) avg_seconds
FROM fact_inspection f JOIN dim_date d USING(date_key)
GROUP BY d.year,d.week_of_year,d.period_phase,f.inspection_mode,f.scenario_key;
DROP VIEW IF EXISTS vw_recall_by_defect;
CREATE VIEW vw_recall_by_defect AS
SELECT df.defect_name,f.inspection_mode,f.scenario_key,COUNT(*) defects,
 SUM(f.final_decision='FAIL') caught,1.0*SUM(f.final_decision='FAIL')/COUNT(*) recall
FROM fact_inspection f JOIN dim_defect df ON df.defect_key=f.true_defect_key
WHERE df.is_defect=1 GROUP BY df.defect_name,f.inspection_mode,f.scenario_key;
DROP VIEW IF EXISTS vw_human_miss_by_hour;
CREATE VIEW vw_human_miss_by_hour AS
SELECT f.hour_in_shift,s.shift_name,COUNT(*) defects,
 1.0*SUM(f.final_decision='PASS')/COUNT(*) miss_rate
FROM fact_inspection f JOIN dim_shift s USING(shift_key)
WHERE f.inspection_mode='manual' AND f.true_defect_key<>0
GROUP BY f.hour_in_shift,s.shift_name;
DROP VIEW IF EXISTS vw_defect_rate_by_lot;
CREATE VIEW vw_defect_rate_by_lot AS
SELECT l.lot_key,l.lot_code,l.customer_name,l.production_line,f.scenario_key,
 COUNT(*) units,1.0*SUM(f.true_defect_key<>0)/COUNT(*) defect_rate
FROM fact_inspection f JOIN dim_lot l USING(lot_key)
WHERE f.inspection_mode='manual' OR f.scenario_key=2
GROUP BY l.lot_key,l.lot_code,l.customer_name,l.production_line,f.scenario_key;
DROP VIEW IF EXISTS vw_lighting_recall;
CREATE VIEW vw_lighting_recall AS
SELECT lighting_cond,inspection_mode,scenario_key,COUNT(*) units,
 1.0*SUM(true_defect_key<>0 AND final_decision='FAIL')/NULLIF(SUM(true_defect_key<>0),0) recall
FROM fact_inspection GROUP BY lighting_cond,inspection_mode,scenario_key;
