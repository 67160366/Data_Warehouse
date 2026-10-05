# ETL Design

`generate_data.py` writes reproducible dimension and fact CSVs. ETL then copies the CSVs to replaceable staging tables, upserts dimensions, validates and loads fact rows, rebuilds the lot mart and KPI views, then runs quality checks and writes `reports/data_quality_report.md`.

Inspection rows with invalid dimensions, manual/device inconsistencies, invalid scenarios, or invalid decisions/timing are captured in `etl_quarantine`. A fact load replaces the fact contents transactionally, so rerunning with the same input is idempotent. Quarantine and run logs retain execution evidence.
