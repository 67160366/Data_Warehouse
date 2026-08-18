# Week07 — Incremental & Idempotent Sales Pipeline

ETL Pipeline สำหรับ **Omnichannel Retail Data Warehouse** อ่านคำสั่งซื้อ 3 batch จาก Excel
ทำความสะอาด กักกันแถวเสีย แล้วโหลดเข้า SQLite star schema โดย **รันซ้ำได้ (idempotent)**
และ **โหลดเฉพาะข้อมูลที่ใหม่กว่า (incremental)**

```
EXTRACT → TRANSFORM → VALIDATE → LOAD → RUN LOG → KPI
```

## วิธีติดตั้งและรัน

```powershell
cd 05_incremental_pipeline
pip install -r requirements.txt

python pipeline.py --reset --batch 1     # รอบ 1: โหลด batch 1 ครั้งแรก
python pipeline.py --batch 1             # รอบ 2: รันซ้ำ — แถวใน fact ต้องไม่เพิ่ม
python pipeline.py --batch 2             # รอบ 3: โหลด batch 2
python pipeline.py --batch 3             # รอบ 4: โหลด batch 3
python pipeline.py --tests               # ตรวจ acceptance test ทั้ง 7 ข้อ

python pipeline.py --batch all           # หรือโหลดรวดเดียวครบ 3 batch
python pipeline.py --batch 1 --error-mode fail_fast   # โหมดเข้มงวด (ใช้เปรียบเทียบ)
```

## โครงสร้างไฟล์

```
05_incremental_pipeline/
├── pipeline.py             โค้ดหลัก รันได้ตั้งแต่ต้นจนจบ (Task 1-5 + acceptance tests)
├── requirements.txt        pandas, openpyxl
├── data/                   ไฟล์ต้นฉบับ — เปิดอ่านอย่างเดียว ไม่แก้ไข
├── output/
│   ├── retail_dw.db        SQLite warehouse หลังโหลดครบ 3 batch
│   ├── quarantine.csv      103 แถวที่ไม่ผ่าน พร้อม reason_code และ source_batch
│   └── pipeline_run_log.csv ประวัติการรัน 4 รอบพร้อมตัวชี้วัด
└── answers.docx            คำตอบฉบับ Word สำหรับส่งอาจารย์
```

## Star Schema

**Grain ของ `fact_sales`: หนึ่งรายการขายสินค้าที่ผ่านการตรวจสอบ ต่อหนึ่ง `order_id`**
→ `order_id` จึงเป็น PRIMARY KEY ซึ่งกันแถวซ้ำตั้งแต่ระดับ schema ไม่ใช่แค่ระดับโค้ด

```
        dim_date                    dim_customer                 dim_product
   date_key (PK)  ◄──┐          customer_key (PK) ◄──┐       product_key (PK) ◄──┐
   full_date         │          customer_id (UQ)     │       product_id (UQ)     │
   day month         │          customer_name        │       product_name        │
   quarter year      │          province segment     │       category            │
                     │          signup_date          │       unit_price          │
                     │                               │       active_flag         │
                     │                               │                           │
                     └───────────── fact_sales ──────┴───────────────────────────┘
                          order_id (PK)   date_key   customer_key   product_key
                          quantity  unit_price  discount_pct
                          gross_amount  net_amount
                          payment_method  sales_channel
                          updated_at  source_batch  loaded_at

        quarantine (row_uid PK, order_id, source_batch, source_row,
                    reason_code, raw_payload, quarantined_at)
        pipeline_run_log (run_id PK, batch, started_at, ended_at,
                    rows_read, rows_valid, rows_rejected, rows_duplicate,
                    rows_loaded, rows_updated, rows_skipped_stale,
                    rows_repaired, status, message)
```

`updated_at`, `source_batch`, `loaded_at` เป็นคอลัมน์ที่เพิ่มจากขั้นต่ำในโจทย์
เพราะ `updated_at` คือค่าที่ใช้ตัดสินว่า record ที่เข้ามาใหม่ควรทับของเดิมหรือไม่

## หลักฐานการรัน 4 รอบ (`output/pipeline_run_log.csv`)

| run | batch | read | valid | rejected | duplicate | inserted | updated | skipped_stale | status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | orders_batch_1 | 420 | 389 | 31 | 0 | **389** | 0 | 0 | SUCCESS |
| 2 | orders_batch_1 | 420 | 389 | 31 | 0 | **0** | 0 | 389 | SUCCESS |
| 3 | orders_batch_2 | 424 | 387 | 37 | 1 | 385 | **1** | 0 | SUCCESS |
| 4 | orders_batch_3 | 424 | 389 | 35 | 3 | 385 | 0 | **1** | SUCCESS |

- **รอบ 2** อ่านข้อมูลชุดเดิมทั้ง 420 แถว แต่ insert 0 แถว → พิสูจน์ idempotency
- **รอบ 3** `O000411` เคยโหลดจาก batch 1 แล้วถูกแก้ไข (`updated_at` 2026-03-16 ใหม่กว่า 2026-02-09) → **update** ทับ
- **รอบ 4** `O000831` มาถึงพร้อม `updated_at` 2026-03-17 ซึ่ง **เก่ากว่า** ของที่โหลดไว้แล้ว (2026-04-22) → **ข้าม** ไม่ให้ข้อมูลเก่าทับของใหม่

สูตรที่ใช้ในการนับ:

```
rows_read  = rows_valid + rows_rejected                                   (นับก่อน deduplicate)
rows_valid = rows_duplicate + rows_inserted + rows_updated + rows_skipped_stale
```

## KPI หลังโหลดครบ 3 batch

| ตัวชี้วัด | ค่า |
|---|---|
| rows read (ไม่นับรอบรันซ้ำ) | 1,268 |
| rows valid | 1,165 |
| rows rejected (quarantine) | **103** |
| rows duplicated (order_id ซ้ำ) | 4 |
| rows repaired (ซ่อมรูปแบบได้) | 29 |
| rows loaded เข้า fact_sales | **1,159** |
| ยอดขายสุทธิรวม (net_amount) | **2,841,792.16 บาท** |

แยกตามช่องทาง: Online 996,581.00 · Marketplace 934,717.07 · Store 910,494.09

## เหตุผลการปฏิเสธข้อมูล (`output/quarantine.csv`)

| reason_code | จำนวน | ตัวอย่างค่าที่เจอ |
|---|---|---|
| `INVALID_DATE` | 21 | `31/02/2026 10:00` (วันที่ไม่มีจริง), `not-a-date` |
| `QTY_OUT_OF_RANGE` | 15 | `-2`, `0` |
| `CUSTOMER_MISSING` | 15 | ค่าว่าง |
| `PRODUCT_NOT_FOUND` | 12 | `P999` |
| `DISCOUNT_OUT_OF_RANGE` | 12 | `120` |
| `QTY_NOT_NUMERIC` | 11 | `three` |
| `PRICE_MISSING` | 9 | ค่าว่าง |
| `CUSTOMER_NOT_FOUND` | 8 | `C9999` |

ส่วนปัญหา "รูปแบบ" ที่ซ่อมได้แน่นอนโดยไม่ต้องเดาค่า จะซ่อมแล้วปล่อยผ่าน ไม่กักกัน
คือ `THB 979.4 → 979.4`, `credit card → Credit Card`, `E-Commerce → Online`

## Reflection — ทำไม Availability จึงมักสำคัญกว่า Strictness ใน Production Pipeline

ในชุดข้อมูลนี้มีแถวเสียเพียง 103 จาก 1,268 แถว หรือ 8% ถ้า Pipeline ตั้งเป็น fail-fast
คือเจอแถวเสียแล้วหยุดทั้ง batch ผลคือยอดขายที่ดีอีก 1,159 แถวจะไม่ขึ้น dashboard เลย
ฝ่ายวิเคราะห์เสียข้อมูล 92% เพื่อแลกกับความถูกต้อง 8% ที่ยังไงก็ต้องกลับไปแก้ที่ต้นทางอยู่ดี
การกักกันแถวเสียไว้พร้อม `reason_code` ให้ผลดีกว่า เพราะรายงานยังออกได้ตรงเวลา
ขณะที่ทีมต้นทางเห็นชัดว่าต้องแก้อะไรบ้าง และเมื่อแก้แล้วส่ง batch ใหม่เข้ามา
Pipeline ที่ idempotent จะรับข้อมูลเวอร์ชันใหม่ทับของเดิมได้เองโดยไม่เกิดยอดซ้ำ
ความเข้มงวดยังอยู่ครบ เพียงแต่ย้ายจาก "หยุดทั้งระบบ" ไปเป็น "แยกของเสียออกมาให้เห็น"
ซึ่งเป็นการแลกที่ระบบจริงเลือกเสมอ — แต่ต้องมีคนไล่ดู quarantine จริง มิฉะนั้นของเสียจะกองเงียบ

## การจัดการความล้มเหลว

| เหตุการณ์ | พฤติกรรม |
|---|---|
| แถวใดแถวหนึ่งผิดกฎ | กักกันแถวนั้นพร้อม `reason_code` แล้วไปต่อ |
| sheet หรือไฟล์ต้นทางอ่านไม่ได้ | บันทึก `status=FAILED` พร้อมสาเหตุลง `pipeline_run_log` ไม่ crash และไม่แตะข้อมูลที่โหลดสำเร็จแล้ว |
| batch หนึ่งล้ม | batch ที่ commit ไปแล้วไม่ได้รับผลกระทบ เพราะแยก transaction ต่อ batch |
| `--error-mode fail_fast` | เจอแถวเสียแล้วทั้ง batch ล้มทันที ใช้เปรียบเทียบกับโหมด quarantine |

`pipeline.py` คืน **exit code 1** เมื่อมี batch ใดล้ม และคืน 0 เมื่อสำเร็จทั้งหมด
เพื่อให้ scheduler หรือ CI จับความล้มเหลวได้โดยไม่ต้องอ่าน log เอง

## Acceptance Tests

`python pipeline.py --tests` แปลงเกณฑ์ทั้ง 7 ข้อในโจทย์เป็น SQL ตรวจจริง ผลล่าสุดผ่าน 7/7

```
[PASS] order_id ใน fact_sales ไม่ซ้ำ  (1159 แถว / 1159 order_id)
[PASS] โหลดครบ 3 batch  (source_batch = 3 ค่า)
[PASS] foreign key เชื่อม dimension ได้ทุกแถว  (orphan = 0)
[PASS] quantity / unit_price / net_amount ไม่ติดลบ  (พบ 0 แถว)
[PASS] ทุกแถวที่ถูกปฏิเสธมี reason_code  (ไม่มี reason_code = 0 แถว)
[PASS] run log: rows_read = rows_valid + rows_rejected  (ผิดสูตร 0 รอบ)
[PASS] รัน batch เดิมซ้ำไม่เพิ่มแถว fact  (รอบที่รันซ้ำแล้ว insert เพิ่ม = 0)
```
