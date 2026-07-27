# Data Warehouse (Star Schema) ด้วย pandas + sqlite3

แปลงไฟล์ยอดขาย e-commerce ที่ยังไม่ได้ทำความสะอาด ให้กลายเป็น data warehouse
แบบ star schema ใน SQLite ผ่าน ETL pipeline 3 เฟส

ข้อมูลต้นทาง `Workshop/raw_ecommerce_data.csv` — 185 แถว 9 คอลัมน์

## โครงสร้าง star schema

```
                dim_customer
                (18 แถว)
                     |
                     | customer_id
                     v
dim_time  <----- fact_sales ----->  dim_product
(120 แถว)   date_key   (180 แถว)  product_id  (12 แถว)
```

| ตาราง | PK | คอลัมน์ |
|---|---|---|
| `dim_customer` | `customer_id` | `customer_name`, `email` |
| `dim_product` | `product_id` | `product_name`, `category` |
| `dim_time` | `date_key` (YYYYMMDD) | `full_date`, `year`, `quarter`, `month`, `month_name`, `day`, `weekday_name`, `is_weekend` |
| `fact_sales` | `order_id` | `customer_id`, `product_id`, `date_key` (FK) + `quantity`, `unit_price`, `amount` |

## วิธีรัน

ต้องมี Python 3.9 ขึ้นไป กับ pandas (`sqlite3` มากับ Python อยู่แล้ว)

```bash
pip install pandas

python src/step1_extract.py        # E   สำรวจข้อมูลดิบ
python src/step2a_dimensions.py    # T   สร้าง dimension
python src/step2b_fact.py          # T   สร้าง fact
python src/step3a_schema_dim.py    # L   schema ของ dimension
python src/step3b_schema_fact.py   # L   schema ของ fact + FK
python src/step3c_load.py          # L   โหลดข้อมูลเข้า SQLite
python src/step4_verify.py         #     ตรวจสอบผลลัพธ์
```

ต้องรันตามลำดับเพราะแต่ละขั้นอ่านผลลัพธ์ของขั้นก่อนหน้า
รันซ้ำกี่รอบก็ได้ ข้อมูลไม่บาน

## โครงสร้างไฟล์

```
.
├── Workshop/raw_ecommerce_data.csv   ข้อมูลต้นทาง (ไม่แก้ไข)
├── src/
│   ├── common.py                     ฟังก์ชันที่ใช้ร่วมกัน
│   ├── step1_extract.py
│   ├── step2a_dimensions.py
│   ├── step2b_fact.py
│   ├── step3a_schema_dim.py
│   ├── step3b_schema_fact.py
│   ├── step3c_load.py
│   └── step4_verify.py
├── output/                           ไฟล์กลางระหว่าง step + รายงานแต่ละขั้น
└── warehouse/dw.sqlite               ตัวคลังข้อมูล
```

แต่ละขั้นเขียนผลลัพธ์เป็น CSV ทิ้งไว้ใน `output/` แล้วขั้นถัดไปอ่านจากไฟล์นั้น
ทำให้รันทีละขั้นแยกกันได้ และเปิดดูผลกลางทางด้วย Excel ได้

## ปัญหาที่เจอในข้อมูลดิบ และวิธีจัดการ

| ปัญหา | จำนวน | วิธีจัดการ | ขั้น |
|---|---|---|---|
| แถวซ้ำสนิท | 5 | ลบหลัง normalize | 2A |
| ช่องว่างหัวท้าย | 121 ช่อง | `strip` + บีบช่องว่างกลาง | 2A |
| ตัวพิมพ์ใหญ่เล็กไม่ตรงกัน | 43 ค่า | จับกลุ่มด้วย lowercase แล้วเลือกการสะกดที่เหมาะสุด | 2A |
| `Customer_Name` หาย | 2 | เติมจาก `email -> name` | 2A |
| `Email` หาย | 1 | เติมจาก `name -> email` | 2A |
| `Category` หาย | 1 | เติมจาก `product -> category` | 2A |
| `Order_Date` มี 3 ฟอร์แมต | 185 | parse แยกทีละ pattern | 2A |
| `Unit_Price`/`Amount` มี `฿` และ `,` | 102 ช่อง | ลอกอักขระออกแล้วแปลงเป็น float | 2B |
| `Amount` หาย | 42 | คำนวณจาก `quantity x unit_price` | 2B |

## การตัดสินใจที่สำคัญ

**`Unit_Price` อยู่ใน fact ไม่ใช่ `dim_product`**
สินค้าชิ้นเดียวกันขายได้หลายราคา (Mechanical Keyboard มี 8 ราคา, Webcam HD มี 8)
เพราะราคาเปลี่ยนตามเวลาและโปรโมชั่น ถ้าเอาราคาเข้า dimension จะได้ 63 แถวแทน 12
ราคาที่ขายจริง ณ ตอนนั้นเป็น measure ของธุรกรรม ไม่ใช่คุณสมบัติถาวรของสินค้า

**เติมค่าที่หายแทนการทิ้งแถว**
ค่าที่หายทุกตัวกู้คืนได้จากแถวอื่นในไฟล์เดียวกัน — email กับชื่อเป็น 1:1 ทั้ง 18 ราย
สินค้ากับ category เป็น 1:1 ทั้ง 12 รายการ และ `amount` เท่ากับ
`quantity x unit_price` ตรงทุกแถวที่มีค่า จึงเติมได้โดยไม่ต้องเดา
ก่อนเติมทุกครั้งโค้ดจะตรวจว่า mapping เป็น 1:1 จริง ถ้าไม่ใช่จะหยุดทำงาน

**แปลงวันที่ทีละฟอร์แมตแทนการปล่อยให้ pandas เดา**
`pd.to_datetime` ตั้ง `dayfirst=False` เป็นค่าเริ่มต้น ถ้าปล่อยให้เดา `03/04/2026`
จะถูกอ่านเป็น 4 มีนาคมแทน 3 เมษายน ยอดขายรายเดือนเพี้ยนโดยไม่มี error ฟ้อง
ข้อมูลชุดนี้ยืนยันได้ว่าเป็นวันขึ้นก่อน เพราะมี 40 แถวที่เลขตัวหน้ามากกว่า 12

**`dim_time` เป็นปฏิทินต่อเนื่อง ไม่ใช่วันที่ที่มีในข้อมูล**
ข้อมูลครอบคลุม 120 วัน แต่มีการขายจริงแค่ 92 วัน ถ้าสร้าง dimension จากวันที่ที่
ปรากฏจริง 28 วันที่ขายไม่ออกจะหายไปจากคลัง ถามหาไม่ได้ และกราฟรายวันจะกระโดดข้ามวัน

**`date_key` ใช้รูปแบบ `YYYYMMDD`**
อ่าน fact แล้วเดาวันได้ทันทีโดยไม่ต้อง join และรัน pipeline ซ้ำค่าก็คงเดิม
ต่างจากเลขรันนิ่ง 1, 2, 3 ที่จะเลื่อนเมื่อมีข้อมูลวันใหม่เข้ามา

**Idempotency ใช้ full refresh**
`DELETE FROM` ทุกตาราง (fact ก่อน dimension) แล้ว `to_sql(if_exists='append')`
ครอบใน transaction เดียว

ไม่ใช้ `if_exists='replace'` เพราะมันทำงานโดย `DROP TABLE` แล้วสร้างใหม่จาก dtype
ของ DataFrame ทำให้ PRIMARY KEY, FOREIGN KEY, NOT NULL และ UNIQUE ที่กำหนดใน
step 3A/3B หายหมด นอกจากนี้เมื่อเปิด `PRAGMA foreign_keys = ON` การ `DROP TABLE`
บน dimension ที่ยังมี fact อ้างอิงอยู่จะโดน `FOREIGN KEY constraint failed`
ตั้งแต่แรก (มีโค้ดสาธิตทั้งสองกรณีอยู่ใน `step3c_load.py`)

## ผลการตรวจสอบ

`step4_verify.py` ตรวจ 16 ข้อ ผ่านทั้งหมด

- จำนวนแถวตรงกับไฟล์ต้นทางทุกตาราง
- ไม่มีแถวใน fact ที่หา dimension ไม่เจอ
- `PRAGMA foreign_key_check` ไม่พบการละเมิด
- ยอดขายรวมที่คำนวณจาก CSV ดิบใหม่ตั้งแต่ต้น เท่ากับยอดในคลังพอดี — **918,184.75 บาท**
- ฐานข้อมูลปฏิเสธ FK ปลอมและ `order_id` ซ้ำจริง (ทดสอบด้วยการยิงของเสียเข้าไปแล้ว rollback)
- query ธุรกิจ 5 แบบทำงานถูกต้อง

ตัวอย่างผล:

```
   category  orders  units   revenue  avg_order
Electronics      83    258 487932.50    5878.70
  Furniture      16     37 222666.00   13916.63
    Storage      16     42 118056.50    7378.53
     Office      41    128  82496.50    2012.11
 Stationery      24     71   7033.25     293.05
```

```
month_name  days_in_month  days_with_sales  days_no_sales
   January             31               20             11
  February             28               20              8
     March             31               25              6
     April             30               27              3
```

รายงานเต็มของแต่ละขั้นอยู่ใน `output/*.txt`

## หมายเหตุ

- `dim_customer` ใช้ email เป็น natural key เพราะไฟล์ต้นทางไม่มีรหัสลูกค้าจากระบบ CRM
  ถ้าลูกค้าเปลี่ยนอีเมลระบบจะมองเป็นคนใหม่ ในระบบจริงควรใช้รหัสจากต้นทางแทน
- ยังไม่รองรับ Slowly Changing Dimension — แก้ค่าใน dimension แล้วประวัติเดิมหายไปเลย
- `sqlite3.connect()` ใช้ `with` ครอบได้แค่ transaction ไม่ได้ปิด connection
  ต้องใช้ `contextlib.closing()` อีกชั้นถ้าต้องการให้ปิดจริง
