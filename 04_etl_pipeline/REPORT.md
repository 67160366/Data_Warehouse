# ETL Lab Report

Student ID: 67160366
Name: 67160366@go.buu.ac.th

Pipeline: `python -m src.main` → Extract → Transform → Load → Validate

---

## 1. Data Quality Problems Found

ข้อมูลต้นทาง 3 แหล่ง (customers.csv 62 แถว, orders.csv 183 แถว, products.json 15 แถว) และตาราง `stores` ใน store.db พบปัญหาดังนี้

| # | แหล่ง | ปัญหา | จำนวน | ตัวอย่าง |
|---|---|---|---|---|
| 1 | customers | `customer_id` ซ้ำ | 2 | C004, C009 (ซ้ำแถวท้ายไฟล์) |
| 2 | customers | `province` เขียนไม่เป็นมาตรฐาน 16 แบบ | 16 ค่า → 4 จังหวัด | `BKK`, `bangkok`, `กรุงเทพฯ` ล้วนหมายถึง Bangkok |
| 3 | customers | สะกดผิด | 1 ค่า | `chantaburi` (ควรเป็น Chanthaburi) |
| 4 | customers | `province` / `email` ว่าง | อย่างละ 1 | C006 ไม่มี email |
| 5 | products | JSON ซ้อนชั้น (nested) | ทุกแถว | `category.name`, `pricing.price` |
| 6 | products | `price` เป็น string มี comma | 1 | P005 = `"1,299.00"` |
| 7 | products | `category` เป็น null | 1 | P009 |
| 8 | orders | `order_id` ซ้ำ | 3 | O0011, O0041, O0101 |
| 9 | orders | รูปแบบวันที่ปนกัน 4 แบบ | ทั้งไฟล์ | `2026/08/02`, `01/08/2026`, `2026-08-01`, `03-Aug-2026` |
| 10 | orders | วันที่ใช้ไม่ได้ | 1 | O0034 = `not-a-date` |
| 11 | orders | `status` พิมพ์เล็ก/ใหญ่ไม่ตรงกัน | 5 ค่า | `PAID` 42 แถว vs `paid` 37 แถว |
| 12 | orders | `qty` ติดลบ | 1 | O0007 = -2 |
| 13 | orders | `unit_price` ติดลบ | 1 | O0091 = -100.00 |
| 14 | orders | `discount_pct` เกินช่วง 0–100 | 1 | O0021 = 150 |
| 15 | orders | อ้าง `customer_id` ที่ไม่มีใน master | 1 | O0049 → C999 |
| 16 | orders | อ้าง `product_id` ที่ไม่มีใน master | 1 | O0076 → P999 |

---

## 2. Cleaning / Transformation Rules

**Customers** (`_clean_customers`)
- `drop_duplicates("customer_id", keep="first")` — เก็บแถวแรก แถวที่ทิ้งบันทึกไว้ใน rejects
- `province` → `.strip().lower()` แล้ว map ผ่าน `PROVINCE_MAP` ใน `config.py` — การ lower ก่อน map ทำให้ `BKK`/`bkk`, `CHONBURI`/`chon buri` เข้ากฎเดียวกันหมด ค่าที่ map ไม่ได้ (รวมค่าว่าง) → `"Unknown"`
- `email` ว่าง → `"Unknown"` — ไม่ทิ้งแถว เพราะ email ไม่ใช่ข้อมูลที่ใช้คำนวณยอดขาย

**Products** (`_clean_products`)
- `pd.json_normalize()` ตอน extract แผ่ nested JSON ออกเป็น `category.name` / `pricing.price` แล้ว rename เป็น `category` / `price`
- `price` → ตัด comma ทิ้งก่อน `pd.to_numeric(errors="coerce")` ทำให้ `"1,299.00"` → `1299.0` (ถ้าใช้ `to_numeric` ตรง ๆ จะกลายเป็น NaN)
- `category` ว่าง → `"Unknown"`

**Orders** (`_clean_orders`)
- `drop_duplicates("order_id", keep="first")`
- วันที่: ไล่ parse ตามลำดับ `%Y/%m/%d` → `%d/%m/%Y` → `%Y-%m-%d` → `%d-%b-%Y` **ลำดับสำคัญ** ต้องลอง `%Y/%m/%d` ก่อน ไม่งั้น `2026/08/02` จะถูกตีความเป็น day=2026 ค่าที่ไม่เข้าฟอร์แมตไหนเลยได้ `NaT` แล้วเข้า rejects
- `status` → `.strip().lower()` รวม `PAID` กับ `paid` เป็นค่าเดียวกัน
- **กฎ reject** (แถวเดียวผิดได้หลายกฎ เก็บเหตุผลรวมกันคั่นด้วย `;`): `qty <= 0`, `unit_price <= 0`, `discount_pct < 0 หรือ > 100`, วันที่ parse ไม่ได้, `customer_id`/`product_id` ไม่มีใน master

**Merge & คำนวณ**
- เก็บเฉพาะ `status ∈ {paid, completed}` → เหลือ 100 แถว
- join กับ `dim_customer` / `dim_product` แบบ inner (ออเดอร์กำพร้าถูกคัดออกไปตั้งแต่ขั้น reject แล้ว จึง join ติดครบทุกแถว — มี `assert` คุมไว้)
- `gross_amount = qty × unit_price` → `discount_amount = gross_amount × discount_pct / 100` → `sales_amount = gross_amount − discount_amount` (ปัดทศนิยม 2 ตำแหน่งทุกขั้น)

**ข้อตัดสินใจ 2 ข้อที่ควรอธิบาย**

1. **`pending` / `cancelled` ไม่นับเป็น reject** — 74 แถว (pending 44, cancelled 30) ถูกกรองออกด้วยกฎธุรกิจ "นับเฉพาะยอดที่เกิดรายได้จริง" ไม่ใช่เพราะข้อมูลผิด จึงไม่ปนเข้า `rejects.csv` (แต่ log จำนวนไว้ใน `logs/etl.log`) เพื่อให้ `rejects.csv` เป็นรายการ *ข้อมูลที่มีปัญหา* ล้วน ๆ
2. **ตรวจ foreign key ก่อนกรอง status** — ออเดอร์กำพร้าทั้ง 2 แถว (O0049, O0076) บังเอิญเป็น `cancelled` ถ้าตรวจหลังกรอง status ตามลำดับใน PDF ทั้งคู่จะหลุดหายไปเงียบ ๆ โดยไม่มีใครรู้ว่าต้นทางมี FK เสีย จึงย้ายการตรวจมาไว้ก่อน ผลลัพธ์ใน `fact_sales` เท่ากันทุกประการ ต่างแค่ `rejects.csv` มีหลักฐานเพิ่ม 2 แถว

---

## 3. Rejected Records

จำนวน: **11 แถว** (บันทึกไว้ใน `output/rejects.csv` พร้อมคอลัมน์ `reject_stage` และ `reject_reason` โดยแสดง**ค่าดิบจากไฟล์ต้นทาง** เพื่อให้ตรวจย้อนหลังได้ว่าผิดตรงไหน)

เหตุผลหลัก:

| เหตุผล | จำนวน | order_id / customer_id |
|---|---|---|
| `duplicate_order_id` | 3 | O0011, O0041, O0101 |
| `duplicate_customer_id` | 2 | C004, C009 |
| `qty_not_positive` | 1 | O0007 (qty = -2) |
| `unit_price_not_positive` | 1 | O0091 (unit_price = -100.00) |
| `discount_pct_out_of_range` | 1 | O0021 (discount_pct = 150) |
| `invalid_order_date` | 1 | O0034 (`not-a-date`) |
| `unknown_customer_id` | 1 | O0049 (C999 ไม่มีใน master) |
| `unknown_product_id` | 1 | O0076 (P999 ไม่มีใน master) |
| **รวม** | **11** | |

เส้นทางของข้อมูล orders: 183 แถวดิบ − 3 ซ้ำ − 6 ผิดกฎ = 174 แถวที่ใช้ได้ − 74 แถวที่ไม่ใช่ paid/completed = **100 แถวเข้า fact_sales**

---

## 4. ETL Validation

จาก `output/validation.json`

| ตัวชี้วัด | ค่า |
|---|---|
| Valid transformed rows | 100 |
| Warehouse rows (`fact_sales`) | 100 |
| Duplicate `order_id` | 0 |
| Source total sales | 192,074.63 |
| Warehouse total sales | 192,074.63 |
| **Validation status** | **PASS** |

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

`status` จะเป็น `PASS` ก็ต่อเมื่อผ่านครบทั้ง 3 เงื่อนไข: จำนวนแถวตรงกัน, ไม่มี `order_id` ซ้ำ และผลรวมยอดขายสองฝั่งต่างกันน้อยกว่า 0.01 (เผื่อความคลาดเคลื่อนของ float)

ตารางใน `data/warehouse/warehouse.db`: `dim_customer` 60 แถว, `dim_product` 15 แถว, `fact_sales` 100 แถว — ตรวจแล้วไม่มี key ซ้ำและไม่มีแถวกำพร้าใน fact ทั้งสองด้าน

---

## 5. Idempotency Test

จำนวน fact_sales หลัง run ครั้งที่ 1: **100**

จำนวน fact_sales หลัง run ครั้งที่ 2: **100** (รันครั้งที่ 3 ก็ยังได้ 100)

อธิบายผล:

`fact_sales` **ไม่เพิ่ม** เพราะออกแบบให้เขียนแบบ *upsert* ไม่ใช่ append

1. ตาราง `fact_sales` ประกาศ `order_id TEXT PRIMARY KEY` — SQLite จึงบังคับ UNIQUE ให้ที่ระดับ schema เขียนซ้ำไม่ได้ตั้งแต่แรก
2. คำสั่งเขียนใน `src/load.py` ใช้
   ```sql
   INSERT INTO fact_sales (...) VALUES (...)
   ON CONFLICT(order_id) DO UPDATE SET customer_id=excluded.customer_id, ...
   ```
   เมื่อเจอ `order_id` เดิม จะ **อัปเดตทับ** แถวเดิมแทนการเพิ่มแถวใหม่ จำนวน record จึงคงที่ ส่วนค่าที่แก้ไขจากต้นทางก็ยังไหลตามมาถูกต้อง (ต่างจาก `INSERT OR IGNORE` ที่จะทิ้งค่าใหม่ทั้งหมด)
3. `dim_customer` (60) และ `dim_product` (15) ใช้หลักการเดียวกันบน `customer_id` / `product_id` จึงคงที่เช่นกัน

ถ้าใช้ `df.to_sql(..., if_exists="append")` ตรง ๆ รันครั้งที่ 2 จะได้ 200 แถวทันที และถ้าใช้ `if_exists="replace"` จำนวนแถวจะคงที่ก็จริง แต่ pandas จะ DROP แล้วสร้างตารางใหม่ ทำให้ PRIMARY KEY และ FOREIGN KEY หายไปหมด — ทั้งสองวิธีจึงไม่ตอบโจทย์ข้อนี้
