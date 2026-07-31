# Retail Store Logs -> Star Schema Data Warehouse

Week 04 Assignment — แปลงล็อกการขายหน้าร้าน `retail_logs.csv` ที่ยังไม่ได้ทำความสะอาด
ให้เป็น data warehouse แบบ star schema ใน SQLite ผ่าน ETL pipeline ไฟล์เดียว

ข้อมูลต้นทาง `retail_logs.csv` — 325 แถว 11 คอลัมน์ ช่วง 2026-03-01 ถึง 2026-06-30

## โครงสร้าง star schema

```
              dim_location
              (8 แถว)
                   |
                   | location_id
                   v
dim_date <----- fact_sales -----> dim_product
(122 แถว) date_key (320 แถว) product_id (10 แถว)
```

| ตาราง | PK | คอลัมน์ |
|---|---|---|
| `dim_location` | `location_id` | `store_code` (UNIQUE), `branch`, `province`, `region` |
| `dim_product` | `product_id` | `product_name` (UNIQUE), `category` |
| `dim_date` | `date_key` (YYYYMMDD) | `full_date`, `year`, `quarter`, `month`, `month_name`, `day`, `weekday_name`, `is_weekend` |
| `fact_sales` | `sale_id` | `location_id`, `product_id`, `date_key` (FK) + `quantity`, `unit_price`, `discount_percent`, `gross_amount`, `discount_amount`, `net_amount` |

grain ของ fact คือ 1 แถวต่อ 1 รายการขาย (`Sale_ID`)

## วิธีรัน

ต้องมี Python 3.9 ขึ้นไป กับ pandas (`sqlite3` มากับ Python อยู่แล้ว)

```bash
pip install pandas
python etl_pipeline.py
```

รันซ้ำกี่รอบก็ได้ ข้อมูลไม่บาน — ทดสอบแล้วว่ารัน 3 รอบได้ทุกตารางเหมือนเดิมเป๊ะ

## โครงสร้างไฟล์

```
.
├── retail_logs.csv        ข้อมูลต้นทาง (ไม่แก้ไข)
├── etl_pipeline.py        E -> T -> L -> verify ในไฟล์เดียว
├── retail_warehouse.db    คลังข้อมูล
└── output/
    ├── dim_location.csv   ตารางแต่ละตัวในรูป CSV เอาไว้เปิดดูด้วย Excel
    ├── dim_product.csv
    ├── dim_date.csv
    ├── fact_sales.csv
    └── etl_report.txt     รายงานทุกขั้นตอน
```

## ปัญหาที่เจอในข้อมูลดิบ และวิธีจัดการ

| ปัญหา | จำนวน | วิธีจัดการ |
|---|---|---|
| แถวซ้ำสนิท (`Sale_ID` ซ้ำด้วย) | 5 | ลบหลัง `strip` เหลือ 320 แถว |
| ช่องว่างหัวท้าย | 153 ช่อง | `strip` + บีบช่องว่างกลาง |
| ตัวพิมพ์ใหญ่เล็กไม่ตรงกัน | Branch 31→8, Product 39→10, Province 18→6, Region 14→5, Category 12→4 | จับกลุ่มด้วย lowercase แล้วเลือกการสะกดที่เหมาะสุด |
| `Sale_Date` มี 3 ฟอร์แมต | 100 / 111 / 114 แถว | parse แยกทีละ pattern |
| `Region` หาย | 2 | เติมจาก `Province -> Region` |
| `Discount_Percent` หาย | 1 | เติม `0` |

ตัวเลขในไฟล์นี้สะอาดอยู่แล้ว ไม่มี `฿` หรือ `,` ปน — `Quantity` 1–8,
`Unit_Price` 23.75–336.00, `Discount_Percent` ∈ {0, 5, 10, 15}

## การตัดสินใจที่สำคัญ

**`unit_price` อยู่ใน fact ไม่ใช่ `dim_product`**
สินค้าทุกตัวมีราคาขาย 3 ระดับ (ราคาฐาน ±5% เช่น Mineral Water ขายที่ 23.75 / 25.00 / 26.25)
ถ้าเอาราคาเข้า dimension จะได้ 30 แถวแทน 10 ราคาที่ขายจริง ณ ตอนนั้นเป็น measure
ของธุรกรรม ไม่ใช่คุณสมบัติถาวรของสินค้า

**`dim_location` ใช้ grain ระดับสาขา**
`Store_Code` เป็น natural key ส่วน `branch` `province` `region` เป็น attribute ที่
roll-up ได้ตามลำดับชั้น สาขา -> จังหวัด -> ภูมิภาค เก็บทั้งสามระดับไว้ในตารางเดียว
ตามหลัก denormalize ของ star schema ถามยอดรายภูมิภาคได้โดย join แค่ครั้งเดียว

**คำนวณ `gross_amount` / `discount_amount` / `net_amount` เก็บไว้ทั้งสามตัว**
ไฟล์ดิบไม่มีคอลัมน์ยอดเงินเลย มีแค่จำนวน ราคาต่อชิ้น และ % ส่วนลด
เก็บครบสามตัวเพื่อตอบได้ทั้งยอดก่อนลด มูลค่าส่วนลดที่ให้ไป และยอดสุทธิ
โดยไม่ต้องคำนวณซ้ำใน query ทุกครั้ง

```
gross_amount    = quantity x unit_price
discount_amount = gross_amount x discount_percent / 100
net_amount      = gross_amount - discount_amount
```

**แถวที่ `Discount_Percent` หาย เติม 0**
ส่วนลดไม่ผูกกับสินค้า สาขา หรือระดับราคา (ตรวจ crosstab แล้วกระจายทั่ว) จึงกู้จากแถวอื่น
ไม่ได้เหมือน `Region` เลือกตีความว่า "ไม่ได้บันทึกส่วนลด = ไม่ได้ลด" ซึ่งเป็นค่าที่พบบ่อยที่สุด
(163 จาก 320 แถว) และเป็นการเดาที่ไม่ทำให้ยอดขายสูงเกินจริง

**แปลงวันที่ทีละฟอร์แมตแทนการปล่อยให้ pandas เดา**
`pd.to_datetime` ตั้ง `dayfirst=False` เป็นค่าเริ่มต้น ถ้าปล่อยให้เดา `06/05/2026`
จะถูกอ่านเป็น 5 มิถุนายนแทน 6 พฤษภาคม ยอดขายรายเดือนเพี้ยนโดยไม่มี error ฟ้อง
ข้อมูลชุดนี้ยืนยันได้ว่าเป็นวันขึ้นก่อน เพราะมี 74 แถวที่เลขตัวหน้ามากกว่า 12
เจอฟอร์แมตที่ไม่รู้จักโปรแกรมจะ `raise` ไม่ปล่อยผ่าน

**`dim_date` เป็นปฏิทินต่อเนื่อง ไม่ใช่วันที่ที่มีในข้อมูล**
ข้อมูลครอบคลุม 122 วัน แต่มีการขายจริงแค่ 113 วัน ถ้าสร้าง dimension จากวันที่ที่ปรากฏจริง
9 วันที่ขายไม่ออกจะหายไปจากคลัง ถามว่า "วันไหนยอดเป็นศูนย์" ไม่ได้ และกราฟรายวันจะ
กระโดดข้ามวันเงียบ ๆ

**`date_key` ใช้รูปแบบ `YYYYMMDD`**
อ่าน fact แล้วเดาวันได้ทันทีโดยไม่ต้อง join และรัน pipeline ซ้ำค่าก็คงเดิม
ต่างจากเลขรันนิ่ง 1, 2, 3 ที่จะเลื่อนเมื่อมีข้อมูลวันใหม่เข้ามา

**เติมค่าที่หายเฉพาะที่พิสูจน์ได้ว่าเป็น 1:1**
ก่อนเติม `Region` จาก `Province` โค้ดจะตรวจก่อนว่า mapping เป็น 1:1 จริง ถ้าไม่ใช่จะหยุด
ทำงาน ไม่ใช่เดาแล้วไปต่อ และก่อนแตกเป็น dimension ยังตรวจซ้ำอีก 5 คู่
(`Store_Code -> Branch/Province/Region`, `Province -> Region`, `Product_Name -> Category`)

**Idempotency ใช้ full refresh**
`DELETE FROM` ทุกตาราง (fact ก่อน dimension) แล้ว `to_sql(if_exists='append')`
ครอบใน transaction เดียว

ไม่ใช้ `if_exists='replace'` เพราะมันทำงานโดย `DROP TABLE` แล้วสร้างใหม่จาก dtype
ของ DataFrame ทำให้ PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE และ CHECK
ที่ออกแบบไว้หายหมด

**ใส่ CHECK constraint ไว้เป็นตาข่ายชั้นสุดท้าย**
`quantity > 0`, `unit_price > 0`, `discount_percent BETWEEN 0 AND 100`,
`is_weekend IN (0,1)` — โค้ด Python ตรวจไปแล้วรอบหนึ่ง แต่ถ้าวันหนึ่งโค้ดมีบั๊ก
ฐานข้อมูลจะยังปฏิเสธเอง

## ผลการตรวจสอบ

section VERIFY ใน `etl_pipeline.py` ตรวจ 14 ข้อ ผ่านทั้งหมด

- จำนวนแถวในทุกตารางตรงกับที่เตรียมไว้ (8 / 10 / 122 / 320)
- ไม่มีแถวใน fact ที่หา dimension ไม่เจอ ทั้งสาม dimension
- `PRAGMA foreign_key_check` ไม่พบการละเมิด
- ยอดเงินที่คำนวณใหม่จาก CSV ดิบด้วยโค้ดคนละชุด เท่ากับยอดในคลังพอดี
  — gross **159,092.00** ส่วนลด **7,251.43** สุทธิ **151,840.57** บาท
- ฐานข้อมูลปฏิเสธ FK ปลอม, `sale_id` ซ้ำ และ `quantity = 0` จริง
  (ทดสอบด้วยการยิงของเสียเข้าไปแล้ว rollback)

ตัวอย่างผล:

```
     region  orders  units  revenue
       East     125    479 54072.43
    Central      79    367 41542.44
      South      47    224 25556.22
      North      35    168 18784.45
  Northeast      34    113 11885.03
```

```
     category    gross  discount      net  discount_pct
  Merchandise 56720.00   2168.15 54551.85          3.82
       Bakery 42420.75   2204.05 40216.70          5.20
         Food 38323.50   1843.78 36479.72          4.81
     Beverage 21627.75   1035.45 20592.30          4.79
```

รายงานเต็มของทุกขั้นตอนอยู่ใน `output/etl_report.txt`

## หมายเหตุ

- `dim_location` ใช้ `store_code` เป็น natural key เพราะไฟล์ต้นทางไม่มีรหัสสาขาจาก
  ระบบหลังบ้าน ถ้าร้านเปลี่ยนรหัสระบบจะมองเป็นสาขาใหม่
- ยังไม่รองรับ Slowly Changing Dimension — ถ้าสาขาย้ายจังหวัด ประวัติเดิมจะหายไปเลย
- ไม่มีข้อมูลลูกค้าในไฟล์ต้นทาง จึงตอบคำถามเชิงพฤติกรรมลูกค้าไม่ได้
