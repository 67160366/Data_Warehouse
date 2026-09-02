# Week08 — Data Integration Pipeline (TechTrove E-Commerce)

รวมข้อมูลจาก 4 ระบบต้นทางที่ schema ไม่ตรงกัน (คำสั่งซื้อรายเดือน, CRM, product master, payment gateway)
ให้กลายเป็น Fact/Dimension ที่ใช้วิเคราะห์ยอดขายได้ โดย **ทุกแถวที่ถูกแก้หรือถูกคัดออกมีหลักฐานกำกับ**

```
EXTRACT → COMBINE (schema alignment) → TRANSFORM → INTEGRATE (merge) → VALIDATE → LOAD → ANALYZE
```

## วิธีติดตั้งและรัน

```powershell
cd 06_data_integration
pip install -r requirements.txt

python integration_pipeline.py           # รันทั้ง pipeline แล้วเขียนผลลัพธ์ลง output/ และ figures/
python integration_pipeline.py --quiet   # รันแบบไม่พิมพ์ profile ยาว ๆ
jupyter notebook data_integration_lab.ipynb   # ดูขั้นตอน 5.1-5.6 แบบทีละ cell
```

## โครงสร้างไฟล์

```
06_data_integration/
├── integration_pipeline.py       โค้ดหลัก รันได้ตั้งแต่ต้นจนจบในคำสั่งเดียว
├── data_integration_lab.ipynb    notebook แบ่ง cell ตามหัวข้อ 5.1-5.6 (เรียกฟังก์ชันจากไฟล์ .py)
├── requirements.txt
├── data/                         ไฟล์ต้นฉบับ 5 ไฟล์ — เปิดอ่านอย่างเดียว ไม่แก้ไข
├── output/
│   ├── dim_customer.csv          160 แถว
│   ├── dim_product.csv           40 แถว
│   ├── fact_sales.csv            660 แถว
│   ├── data_quality_report.csv   37 รายการตรวจ ครอบคลุมทุกขั้นตอน
│   ├── summary_by_province.csv
│   ├── summary_by_category.csv
│   ├── rejected_rows.csv         92 แถวที่ถูกคัดออก พร้อม reason_code
│   └── kpi_summary.json          ตัวเลขสรุปที่ใช้อ้างอิงในรายงาน
├── figures/
│   ├── dq_funnel.png             Data Quality Funnel
│   └── dq_before_after.png       เทียบคุณภาพข้อมูลก่อน/หลัง
└── answers.docx                  คำตอบ 6 ข้อ + สรุปคุณภาพข้อมูล สำหรับส่งอาจารย์
```

## Schema drift ระหว่างสองเดือน

| ประเด็น | `orders_2026_01.csv` | `orders_2026_02.csv` |
|---|---|---|
| คอลัมน์วันที่ | `order_date` | `ordered_at` |
| คอลัมน์จำนวน | `quantity` | `qty` |
| คอลัมน์ส่วนลด | `discount` (0.05) | `discount_pct` (`"5%"`) |
| รูปแบบวันที่ | `2026-01-08 17:11:00` | `19/02/2026 02:59` |

ต้องระบุ `format=` ตอน `to_datetime()` ตรง ๆ ห้ามให้ pandas เดา มิฉะนั้น `08/02/2026`
จะถูกอ่านสลับวันกับเดือน

## Star Schema

**Grain ของ `fact_sales`: หนึ่งคำสั่งซื้อที่ตรวจผ่านและชำระเงินสำเร็จ ต่อหนึ่ง `order_id`**

```
        dim_customer                                        dim_product
   customer_key (PK) ◄──┐                             ┌──► product_key (PK)
   customer_id          │                             │    product_id
   full_name  email     │                             │    product_name
   province             │                             │    category
   signup_date          │                             │    standard_price
                        │                             │    active_flag
                        └───────── fact_sales ────────┘
                             order_id      order_date
                             customer_key  product_key
                             quantity  unit_price  discount
                             gross_sales   net_sales
                             payment_method  payment_status  paid_at
                             channel  source_file

   net_sales = quantity × unit_price × (1 - discount)
```

## Data Quality Funnel

| ขั้นตอน | แถวคงเหลือ | % | หายไป |
|---|---|---|---|
| ข้อมูลดิบ 2 เดือน (raw) | 752 | 100.0% | — |
| หลังลบ `order_id` ซ้ำ | 750 | 99.7% | 2 |
| ค่าถูกต้องตามกติกา | 746 | 99.2% | 4 |
| จับคู่ master ได้ | 722 | 96.0% | 24 |
| ชำระเงินสำเร็จ (fact) | **660** | 87.8% | 62 |

เหตุผลของแถวที่ถูกคัดออกทั้ง 92 แถวอยู่ใน `output/rejected_rows.csv`

| `reason_code` | แถว |
|---|---|
| `PAYMENT_NOT_PAID` | 62 |
| `CUSTOMER_NOT_IN_MASTER` | 22 |
| `DUPLICATE_ORDER_ID` | 2 |
| `MISSING_UNIT_PRICE` | 2 |
| `QTY_NOT_POSITIVE` | 2 |
| `PRODUCT_NOT_IN_MASTER` | 2 |

## คุณภาพข้อมูลก่อนและหลัง Data Integration

| ประเด็น | ก่อน | หลัง |
|---|---|---|
| `order_id` ซ้ำ | 2 แถว | 0 |
| `unit_price` ว่าง | 2 แถว | 0 |
| `quantity ≤ 0` | 2 แถว | 0 |
| `customer_id` ซ้ำใน CRM | 3 แถว | 0 |
| email ไม่เป็นมาตรฐาน | 9 แถว | 0 |
| ชื่อจังหวัดไม่เป็นมาตรฐาน | 66 แถว (14 รูปแบบ) | 0 (6 จังหวัด) |
| อ้าง Master Data ไม่ได้ | 24 แถว | 0 |
| ชำระเงินไม่สำเร็จ/ไม่มี | 62 แถว | 0 |

## ผลวิเคราะห์

**ยอดขายสุทธิรวม 10,224,044.09 บาท จาก 660 ธุรกรรม**

| จังหวัด | ธุรกรรม | ยอดขายสุทธิ | สัดส่วน |
|---|---|---|---|
| กรุงเทพมหานคร | 154 | 2,612,955.88 | 25.56% |
| ขอนแก่น | 110 | 2,031,943.40 | 19.87% |
| ระยอง | 120 | 1,523,168.61 | 14.90% |
| เชียงใหม่ | 104 | 1,477,338.01 | 14.45% |
| ภูเก็ต | 86 | 1,427,388.73 | 13.96% |
| ชลบุรี | 86 | 1,151,249.46 | 11.26% |

| หมวดสินค้า | ธุรกรรม | ยอดขายสุทธิ | สัดส่วน |
|---|---|---|---|
| Smartphone | 178 | 3,092,117.34 | 30.24% |
| Accessory | 180 | 2,710,582.77 | 26.51% |
| Notebook | 161 | 2,221,495.49 | 21.73% |
| Smart Home | 141 | 2,199,848.49 | 21.52% |

## ทำไม cleaning ต้องมาก่อน merge

CRM มี `customer_id` ซ้ำ 3 รายการ ถ้า merge ทันทีโดยไม่ dedup ก่อน:

```python
orders.merge(customers_raw, on="customer_id", how="left", validate="m:1")
# MergeError: Merge keys are not unique in right dataset; not a many-to-one merge
```

ถ้าไม่ใส่ `validate=` แถวคำสั่งซื้อจะถูกคูณซ้ำจนยอดขายเกินจริง และถ้ายังไม่ทำมาตรฐานชื่อจังหวัด
ยอดของกรุงเทพฯ จะถูกแยกเป็น `Bangkok` / `กทม.` / `กรุงเทพมหานคร` คนละกลุ่ม
(notebook มีเซลล์ที่รันให้ดูจริง)

## Challenge (+2 คะแนน)

- `validate_data(df, dim_customer, dim_product)` ตรวจ uniqueness, referential integrity
  และค่าที่อยู่นอกช่วง โดยเก็บทุกข้อที่ไม่ผ่านแล้วค่อย `raise DataValidationError` ทีเดียว
  ทำให้เห็นปัญหาครบในรอบเดียวแทนที่จะหยุดที่ assert ตัวแรก
- กราฟ `dq_funnel.png` และ `dq_before_after.png` วาดเป็นภาพขาว-ดำ

## การรันซ้ำ (reproducibility)

รัน `python integration_pipeline.py` สองครั้งติดกัน ไฟล์ใน `output/` มีค่า hash เท่าเดิมทุกไฟล์
เพราะไม่มีการเขียน timestamp ลงในผลลัพธ์ และไฟล์ต้นฉบับใน `data/` ไม่ถูกแก้ไขเลย
