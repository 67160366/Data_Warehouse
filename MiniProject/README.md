# 3Eyes Narrative Dashboard (Data Warehouse)

โครงงาน Data Warehouse ที่จำลองการใช้ 3Eyes เป็นเครื่องมือช่วยคัดกรองตำหนิน็อตสำหรับงาน QC

> **ข้อมูลและผลลัพธ์ทั้งหมดเป็นข้อมูลจำลองเพื่อการศึกษา** ค่า recall, false alarm, ต้นทุน และ ROI เป็นสมมติฐานเชิงสถานการณ์ ไม่ใช่ผลทดสอบจริงของอุปกรณ์หรือโมเดล

## สมาชิกกลุ่ม

| ชื่อ-สกุล | รหัสนักศึกษา | หน้าที่ |
|---|---|---|
| กรอกโดยทีม | กรอกโดยทีม | กรอกโดยทีม |

## บริบทธุรกิจ

ศึกษาว่าการใช้เครื่องมือสวมใส่ช่วยคัดกรองร่วมกับพนักงาน QC อาจลดของเสียหลุดถึงลูกค้าได้อย่างไร พร้อมพิจารณา false alarm, uncertain, เวลาแรงงาน และต้นทุนอุปกรณ์ ดูรายละเอียดใน [บริบทธุรกิจ](docs/01_business_context.md) และ repository ต้นทาง `3eyes-anomaly-detection` (เติม URL จริงก่อนส่ง)

## สถาปัตยกรรมและข้อมูล

`CSV จำลอง → staging → dimensions/facts → marts และ KPI views → Streamlit Dashboard`

ข้อมูลสร้างจาก `src/generate_data.py` ด้วย seed 42 กำหนดพารามิเตอร์ใน `config/generator_params.yaml` และสมมติฐานต้นทุนใน `config/assumptions.csv` ทุกค่ามี source; `ASSUMPTION` หมายถึงค่าประมาณเพื่อการศึกษา คำอธิบายตารางและคอลัมน์อยู่ใน [data dictionary](data/data_dictionary.md)

## วิธีรัน

ต้องใช้ Python 3.11 ขึ้นไป จากโฟลเดอร์ repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python run.py setup
python run.py all
python run.py app
```

บน macOS/Linux ใช้ `source .venv/bin/activate` และ `python3 run.py ...` คำสั่ง `all` สร้าง CSV, reset และโหลด SQLite, สร้างรายงานตรวจคุณภาพ และรัน tests หากมีการแก้ source ให้รัน `python run.py data` ตามด้วย `python run.py etl` ได้

ไฟล์ผลลัพธ์หลักคือ `data/raw/*.csv`, `data/warehouse/threeeyes_dw.db` และ `reports/data_quality_report.md` ฐานข้อมูล SQLite ถูกสร้างตอนรันและไม่ commit ตาม `.gitignore`

## KPI และ Dashboard

KPI K1–K12 และนิยามอยู่ใน [เอกสาร KPI](docs/03_kpi_definitions.md) ภาพรวมแต่ละหน้าดูได้ใน [storyboard](docs/02_storyboard.md) Dashboard มีห้าตอน: ปัญหา, ประเภทตำหนิ, ความล้าของคน, ทางออก 3Eyes และความคุ้มค่า

## ข้อจำกัด

- ข้อมูลสร้างขึ้นเพื่อจำลองแนวโน้มและไม่ใช่หลักฐานสมรรถนะจริง
- ค่าใช้จ่ายและผลตอบแทนทั้งหมดต้องแทนด้วยข้อมูลอ้างอิงที่ทีมยืนยันก่อนนำเสนอ
- ความแตกต่าง manual/assisted ในชุดข้อมูลเป็นสถานการณ์จำลอง ไม่ใช่การทดลองควบคุมในโรงงาน
