# Week06 — Mini ETL Pipeline with Python

สร้าง ETL Pipeline ให้บริษัทจำลอง **CampusMart** อ่านข้อมูลจาก 4 แหล่ง ทำความสะอาด แยก record ที่ผิดปกติ
โหลดเข้า SQLite warehouse แล้วตรวจสอบผลลัพธ์ — รันซ้ำได้โดยข้อมูลไม่ซ้ำ

```
EXTRACT → TRANSFORM → LOAD → VALIDATE
```

## โครงสร้างไฟล์

```
04_etl_pipeline/
├── src/
│   ├── config.py         path ทั้งหมด + PROVINCE_MAP
│   ├── extract.py        Part 1 — อ่าน CSV / JSON / SQLite
│   ├── transform.py      Part 2 — ล้างข้อมูล กฎ reject merge และคำนวณยอดขาย
│   ├── load.py           Part 3 — upsert เข้า star schema (idempotent)
│   ├── validate.py       Part 4 — เทียบ transformed data กับ warehouse
│   └── main.py           orchestrator + logging
├── data/
│   ├── raw/              customers.csv (62), orders.csv (183), products.json (15)
│   ├── source_db/        store.db — ตาราง stores
│   └── warehouse/        warehouse.db — ผลลัพธ์ (สร้างตอนรัน)
├── output/
│   ├── rejects.csv       11 record ที่ไม่ผ่านกฎ พร้อมเหตุผล
│   └── validation.json   ผลตรวจ PASS / FAIL
├── logs/etl.log          log ทุกขั้นตอน
├── REPORT.md             รายงานตอบคำถาม 5 ข้อ
├── answers.docx          รายงานฉบับ Word (ตัวอักษรดำ พื้นขาว)
├── DATA_DICTIONARY.csv   คำอธิบายฟิลด์ต้นทาง
├── docs/LAB-ASSIGNMENT-ETL.pdf
└── 67160366_ETL_Lab.zip  ไฟล์ส่งงาน
```

## วิธีรัน

```powershell
cd 04_etl_pipeline
pip install -r requirements.txt
python -m src.main
```

รันซ้ำได้ทุกเมื่อ — `fact_sales` จะยังมี 100 แถวเท่าเดิม เพราะเขียนแบบ upsert บน `order_id`

## Star schema ที่ได้

| ตาราง | แถว | Primary key |
|---|---|---|
| `dim_customer` | 60 | `customer_id` |
| `dim_product` | 15 | `product_id` |
| `fact_sales` | 100 | `order_id` |

`fact_sales` มี FK ชี้กลับทั้งสอง dimension และไม่มีแถวกำพร้า

## ผลลัพธ์

```json
{
  "source_valid_rows": 100,
  "warehouse_rows": 100,
  "duplicate_order_ids": 0,
  "source_total_sales": 192074.63,
  "warehouse_total_sales": 192074.63,
  "status": "PASS"
}
```

เส้นทางข้อมูล: orders 183 แถว − 3 ซ้ำ − 6 ผิดกฎ = 174 แถวใช้ได้ − 74 แถวที่ไม่ใช่ paid/completed = **100 แถวเข้า fact_sales**

รายละเอียดปัญหาคุณภาพข้อมูล 16 ข้อ วิธีแก้ และผลทดสอบ idempotency อยู่ใน [REPORT.md](REPORT.md)

## สิ่งที่ต้องมีเพื่อรันโค้ด

```
python >= 3.11
pandas >= 2.2
numpy >= 1.26
```
