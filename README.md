# Data Warehouse

งานปฏิบัติการรายวิชา Data Warehouse

| โฟลเดอร์ | หัวข้อ |
|---|---|
| `01_star_schema_etl/` | ETL pipeline จาก raw CSV เข้า SQLite star schema |
| `02_retail_star_schema/` | Week04 — Retail logs ETL to star schema warehouse |
| [`03_data_quality_cleaning/`](03_data_quality_cleaning/) | Week05 — Data Quality & Data Cleaning ด้วย Pandas |
| [`04_etl_pipeline/`](04_etl_pipeline/) | Week06 — Mini ETL Pipeline: Extract → Transform → Load → Validate |
| [`05_incremental_pipeline/`](05_incremental_pipeline/) | Week07 — Incremental & Idempotent Pipeline เข้า Star Schema พร้อม quarantine และ run log |
| [`06_data_integration/`](06_data_integration/) | Week08 — Data Integration Pipeline รวม CSV/Excel/JSON เข้า Fact/Dimension พร้อม Data Quality Report |

## สิ่งที่ต้องมีเพื่อรันโค้ด

```
python >= 3.11
pandas
matplotlib
jupyter / nbconvert   (สำหรับเปิดและรัน notebook)
```
