# Week05 — Data Quality & Data Cleaning

การเตรียมข้อมูลร้านค้าออนไลน์ก่อนโหลดเข้า Data Warehouse ด้วย Python (Pandas)

## โครงสร้างไฟล์

```
03_data_quality_cleaning/
├── dq_lab.ipynb          งานส่ง — 1 ส่วนต่อ Task พร้อม output, boxplot และคำตอบวิเคราะห์
├── dq_lab.py             pipeline ตัวจริง รันซ้ำได้ มี assertion 15 ข้อ
├── data/
│   ├── e_commerce_raw.csv          ข้อมูลดิบ 630 แถว 16 คอลัมน์
│   ├── customer_reference.csv      ตารางอ้างอิงลูกค้า 167 ราย
│   ├── e_commerce_clean.csv        ผลลัพธ์ 612 แถว 36 คอลัมน์ (UTF-8-SIG)
│   └── data_quality_report.csv     รายงานคุณภาพข้อมูล 19 ตัวชี้วัด (UTF-8-SIG)
├── figures/
│   ├── boxplot_before.png
│   └── boxplot_after.png
└── docs/
    ├── Lab-assigment.pdf
    └── answers.html            เอกสารคำตอบคำถาม 5 ข้อ + Reflection + Checklist (เปิดในเบราว์เซอร์/สั่งพิมพ์เป็น PDF ได้)
```

## วิธีรัน

```powershell
cd 03_data_quality_cleaning
python dq_lab.py                                                    # รัน pipeline + assertion ทั้งหมด
python -m nbconvert --to notebook --execute --inplace dq_lab.ipynb   # รัน notebook ทุก cell
```

`dq_lab.ipynb` import ฟังก์ชันและ path constant จาก `dq_lab.py` จึงต้องอยู่โฟลเดอร์เดียวกัน
และผลลัพธ์ของทั้งสองทางจะตรงกันเสมอ

## หลักการที่ใช้

1. **สร้าง flag ก่อนแก้ค่าทุกครั้ง** เพื่อให้ตรวจย้อนหลังได้ — คอลัมน์ flag 11 ตัวถูกเก็บไว้ในไฟล์ผลลัพธ์
2. **ห้าม drop แถว** เพราะข้อมูลบางคอลัมน์หาย — Fact row และยอดขายต้องไม่สูญหาย
3. **ไม่แก้ค่าที่ต้องใช้ business context ตัดสิน** (ยอดโปรโมชัน ยอดไม่ตรงสูตร ยอดติดลบ) ติด flag ไว้ให้ตรวจ
4. **ทุก mapping มี coverage check** ถ้าเจอค่าที่ยังไม่รู้จักจะ error ทันที ไม่เงียบกลายเป็น `Unknown`

## ผลลัพธ์สรุป

| มิติ | ก่อน | หลัง |
|---|---|---|
| จำนวนแถว | 630 | 612 (ลบแถวซ้ำ 18 แถว) |
| `Customer_Email` ว่าง | 50 | 0 (เติมจาก reference 47, unknown 3) |
| `Province` ว่าง | 12 | 0 (เติมจาก reference 8, Unknown 4) |
| รูปแบบ `Gender` | 10 | 2 |
| รูปแบบ `Payment_Method` | 14 | 4 |
| `Order_Date` ที่ไม่เป็น `YYYY-MM-DD` | 281 | 0 |
| `Quantity` นอกช่วง 1–20 | 3 | 0 |
| ค่า sentinel ในยอดเงิน | 4 | 0 |
| Outlier ตาม IQR | 25 | 6 (เป็นรายการโปรโมชันที่คงค่าเดิมไว้) |

## ข้อค้นพบที่น่าสนใจ

- **`Load_Timestamp` เป็นหลักฐานตัดสินวันที่กำกวมได้** — 409 แถวที่รูปแบบไม่กำกวมมี delay 1–116 ชม.
  ไม่ติดลบเลยแม้แถวเดียว จึงใช้กฎ "delay ต้องไม่ติดลบและน้อยที่สุด" ตัดสินได้ 78 แถว
  (ถ้า parse เหมารวมด้วย `dayfirst=True` จะได้ delay ติดลบ 28 แถว ซึ่งเป็นไปไม่ได้ทางธุรกิจ)
- **regex ตรวจรูปแบบวันที่อย่างเดียวไม่พอ** ต้อง validate ด้วยปฏิทินด้วย เพราะมีค่าอย่าง `2026-13-05`
  (เดือน 13) และ `31/02/2026` ที่รูปแบบถูกแต่ไม่ใช่วันที่จริง — รวม 7 แถวที่ต้อง impute
- **IQR จับยอดติดลบไม่ได้** เพราะ lower bound ของข้อมูลชุดนี้คือ −758.22 ซึ่งติดลบอยู่แล้ว
  ยอดติดลบจึงต้องตรวจด้วย business rule แยกจาก outlier detection
- **ยอดขายรวมที่ลดลง 87% มาจากค่า sentinel 4 แถว** (666666 + 777777 + 888888 + 999999 = 3,333,330 บาท)
  ไม่ใช่ข้อมูลจริงที่หายไป — เมื่อตัด sentinel ออก ยอดเปลี่ยนจาก 504,814 เป็น 489,798 บาท
- **near duplicate ในชุดข้อมูลนี้เกิดจากช่องว่างซ้ำ** (`Ploy  Saelim` vs `Ploy Saelim`) ไม่ใช่ชื่อเล่น
  จึงต้อง normalize whitespace ถึงจะจับได้ และรายงานไว้เท่านั้นโดยไม่ลบ เพราะสองแถวนั้นเป็นธุรกรรมต่างรายการกัน
