# Data Dictionary

ข้อมูลจำลอง seed 42; CSV หลักเป็น UTF-8-SIG เปิดใน Excel ได้

Inspection grain = unit_id × mode × scenario; assisted 3 สถานการณ์คือหน่วยเดิม ไม่ใช่ยอดผลิตสามเท่า
Claim grain = lot × defect × scenario (วันที่เดียวกับ lot); หนึ่งตำหนิหลักต่อน็อต; lot อยู่วันและกะเดียว

ชนิดด้านล่างคือชนิดใน SQLite; CSV ไม่มีชนิดข้อมูลในตัว ช่องว่างแทน NULL. PK รวมไม่อนุญาต NULL.

## dim_date

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `date_key` PK | INTEGER | YYYYMMDD | no | คีย์วัน อ้างอิง dim_date |
| `full_date` | TEXT | ISO date | no | วันที่ปฏิทิน YYYY-MM-DD |
| `year` | INTEGER | year | no | ปี ค.ศ. |
| `quarter` | INTEGER | quarter | no | ไตรมาส 1–4 |
| `month` | INTEGER | month | no | เดือน 1–12 |
| `month_name` | TEXT | — | no | ชื่อเดือนภาษาอังกฤษ |
| `week_of_year` | INTEGER | ISO week | no | สัปดาห์ตาม ISO 8601 |
| `day_of_week` | INTEGER | day | no | 1 จันทร์ ถึง 7 อาทิตย์ |
| `is_weekend` | INTEGER | 0/1 | no | 1 = เสาร์หรืออาทิตย์ |
| `period_phase` | TEXT | enum | no | baseline_manual / assisted_3eyes |

## dim_shift

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `shift_key` PK | INTEGER | key | no | คีย์กะ อ้างอิง dim_shift |
| `shift_name` | TEXT | — | no | เช้า / บ่าย / ดึก |
| `start_hour` | INTEGER | hour | no | ชั่วโมงเริ่มกะ 0–23 |
| `end_hour` | INTEGER | hour | no | ชั่วโมงจบกะ; กะดึกข้ามวัน แต่ลงวันที่เริ่มกะ |

## dim_inspector

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `inspector_key` PK | INTEGER | key | no | คีย์พนักงาน อ้างอิง dim_inspector |
| `inspector_code` | TEXT | — | no | รหัส QC สมมติ ไม่ใช่ข้อมูลบุคคลจริง |
| `tenure_years` | REAL | years | no | อายุงานสมมติ |
| `experience_band` | TEXT | enum | no | <1 ปี / 1-3 ปี / >3 ปี |

## dim_device

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `device_key` PK | INTEGER | key | no | คีย์เครื่อง อ้างอิง dim_device; NULL เฉพาะ manual |
| `device_code` | TEXT | — | no | รหัสเครื่องสมมติ |
| `model_version` | TEXT | — | no | รุ่นจำลอง SIM-1.0 |
| `deployed_date` | TEXT | ISO date | yes | วันเริ่ม assisted ของเครื่องจำลอง |

## dim_lot

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `lot_key` PK | INTEGER | key | no | คีย์ lot อ้างอิง dim_lot |
| `lot_code` | TEXT | — | no | รหัส lot ไม่ซ้ำ |
| `customer_name` | TEXT | — | no | ชื่อลูกค้าสมมติ A/B/C กระจายข้ามไลน์ |
| `production_line` | TEXT | — | no | LINE-1 ถึง LINE-3 |
| `lot_size` | INTEGER | units | no | จำนวนหน่วยจริงจำลองใน lot ห้ามคูณสามสถานการณ์ |
| `production_date` | TEXT | ISO date | no | วันผลิตและตรวจ lot; รุ่นนี้ใช้เป็นวันเคลมด้วย |
| `shift_key` | INTEGER | key | no | คีย์กะ อ้างอิง dim_shift |

## dim_defect

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `defect_key` PK | INTEGER | key | no | คีย์ประเภท: 0 งานดี; 1–7 ตำหนิหลัก |
| `defect_name` | TEXT | — | no | ชื่อตำหนิหลักหนึ่งประเภทต่อน็อต หรือ งานดี |
| `defect_group` | TEXT | — | no | กลุ่มพื้นที่ของตำหนิ |
| `location` | TEXT | — | no | ตำแหน่งตำหนิ |
| `severity` | TEXT | enum | no | none / minor / major / critical |
| `is_defect` | INTEGER | 0/1 | no | 1 = ของเสียจริง; 0 = งานดี |

## dim_scenario

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `scenario_key` PK | INTEGER | key | no | 0 manual, 1 Conservative, 2 Base, 3 Optimistic |
| `scenario_name` | TEXT | enum | no | N/A / Conservative / Base / Optimistic |
| `description` | TEXT | — | yes | คำอธิบายสถานการณ์จำลอง |

## fact_inspection

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `inspection_id` PK | INTEGER | key | no | รหัสแถวตรวจไม่ซ้ำ |
| `unit_id` | TEXT | — | no | รหัสน็อต LOT-xxxx-yyyy เดิมใน assisted ทั้งสามสถานการณ์ |
| `date_key` | INTEGER | YYYYMMDD | no | คีย์วัน อ้างอิง dim_date |
| `shift_key` | INTEGER | key | no | คีย์กะ อ้างอิง dim_shift |
| `inspector_key` | INTEGER | key | no | คีย์พนักงาน อ้างอิง dim_inspector |
| `device_key` | INTEGER | key | yes | คีย์เครื่อง อ้างอิง dim_device; NULL เฉพาะ manual |
| `lot_key` | INTEGER | key | no | คีย์ lot อ้างอิง dim_lot |
| `scenario_key` | INTEGER | key | no | 0 manual, 1 Conservative, 2 Base, 3 Optimistic |
| `true_defect_key` | INTEGER | key | no | ความจริงของน็อต อ้างอิง dim_defect.defect_key |
| `inspection_mode` | TEXT | enum | no | manual / assisted |
| `hour_in_shift` | INTEGER | hour | no | ชั่วโมงที่ 1–8 ภายในกะ |
| `lighting_cond` | TEXT | enum | no | good / dim / glare; สุ่มครั้งเดียวต่อน็อต |
| `device_decision` | TEXT | enum | yes | PASS / FAIL / UNCERTAIN; NULL เฉพาะ manual |
| `final_decision` | TEXT | enum | no | PASS ส่งผ่าน QC / FAIL คัดออกหลังคนตัดสิน |
| `override_flag` | INTEGER | 0/1 | no | 1 เฉพาะเครื่อง FAIL แต่คนให้ final PASS |
| `inspect_seconds` | REAL | seconds/unit | no | เวลาตรวจรวม; assisted FAIL/UNCERTAIN รวมเวลายืนยันเพิ่ม |

## fact_customer_claim

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `claim_id` PK | INTEGER | key | no | รหัสแถวเคลมไม่ซ้ำ |
| `date_key` | INTEGER | YYYYMMDD | no | คีย์วัน อ้างอิง dim_date |
| `lot_key` | INTEGER | key | no | คีย์ lot อ้างอิง dim_lot |
| `defect_key` | INTEGER | key | no | คีย์ประเภท: 0 งานดี; 1–7 ตำหนิหลัก |
| `scenario_key` | INTEGER | key | no | 0 manual, 1 Conservative, 2 Base, 3 Optimistic |
| `qty_returned` | INTEGER | units | no | จำนวนคืน ไม่เกินของเสียที่หลุดใน lot/defect/scenario; อาจเป็น 0 |
| `claim_cost` | REAL | THB | no | ค่าเคลม; ใน mart รวมค่าแก้ไขงานคืนด้วย |
| `rework_cost` | REAL | THB | no | ค่าแก้ไขงานที่คืน |

## fact_lot_summary

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `lot_key` PK | INTEGER | key | no | คีย์ lot อ้างอิง dim_lot |
| `scenario_key` PK | INTEGER | key | no | 0 manual, 1 Conservative, 2 Base, 3 Optimistic |
| `inspection_mode` PK | TEXT | enum | no | manual / assisted |
| `units_inspected` | INTEGER | units | no | จำนวนตรวจใน lot/mode/scenario |
| `true_defects` | INTEGER | units | no | จำนวนของเสียจริง |
| `defects_caught` | INTEGER | units | no | จำนวนของเสียจริงที่ final FAIL |
| `defects_escaped` | INTEGER | units | no | จำนวนของเสียจริงที่ final PASS |
| `final_false_rejects` | INTEGER | units | no | งานดีที่ final FAIL (Final False Reject ไม่ใช่ Device False Alarm) |
| `labor_cost` | REAL | THB | no | มูลค่าเวลา QC = วินาทีรวม × ค่าแรงต่อชั่วโมง / 3600 |
| `claim_cost` | REAL | THB | no | ค่าเคลม; ใน mart รวมค่าแก้ไขงานคืนด้วย |

## etl_run_log

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `run_id` PK | INTEGER | key | no | รหัสรอบ ETL ของแต่ละขั้น |
| `started_at` | TEXT | UTC timestamp | no | เวลาเริ่มขั้น ETL |
| `finished_at` | TEXT | UTC timestamp | yes | เวลาจบ; NULL ขณะ running |
| `step_name` | TEXT | — | no | ชื่อขั้น ETL |
| `rows_read` | INTEGER | rows/checks | yes | จำนวนอ่าน; ขั้น validate ใช้จำนวน checks |
| `rows_loaded` | INTEGER | rows/checks | yes | จำนวนโหลด; ขั้น validate ใช้จำนวน checks ที่ผ่าน |
| `rows_rejected` | INTEGER | rows | yes | จำนวนแถวที่แยกออกในรอบนี้ |
| `status` | TEXT | enum | no | running / success / partial / failed |
| `message` | TEXT | — | yes | ข้อความสรุปหรือข้อผิดพลาด |

## etl_quarantine

| Column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| `quarantine_id` PK | INTEGER | key | no | รหัส quarantine |
| `run_id` | INTEGER | key | no | รหัสรอบ ETL ของแต่ละขั้น |
| `source_table` | TEXT | — | no | fact_inspection / fact_customer_claim |
| `raw_row_json` | TEXT | JSON | no | ค่าแถว staging เดิมที่ปฏิเสธ |
| `reject_reason` | TEXT | — | no | เหตุผลปฏิเสธแถว |
| `created_at` | TEXT | UTC timestamp | no | เวลาบันทึก quarantine |

## Staging และไฟล์สมมติฐาน

`stg_*` มีชื่อคอลัมน์เหมือน CSV ต้นทางทั้ง 9 ตาราง; staging ยอมรับค่าว่างและชนิดผิดเพื่อให้ fact loader ตรวจและแยก quarantine ได้ ไม่มีการใช้ staging เป็นข้อมูล Dashboard โดยตรง

| assumptions.csv column | Type | Unit | NULL | Meaning |
|---|---|---|---|---|
| param | TEXT | — | no | ชื่อสมมติฐานไม่ซ้ำ |
| value | REAL | ตาม unit | no | ค่าที่ใช้ใน generator/ROI |
| unit | TEXT | — | no | หน่วย |
| source | TEXT | — | no | ASSUMPTION หรือแหล่งอ้างอิง |
| note | TEXT | — | no | ความหมายของสมมติฐาน |

ค่าตัวเลขและหน่วยจริงอยู่ใน [assumptions.csv](../config/assumptions.csv); schema และ CHECK constraints อยู่ใน [schema.sql](../src/schema.sql).
SQL view columns เป็นผลรวมจาก facts ตาม [KPI definitions](../docs/03_kpi_definitions.md) ไม่ใช่ข้อมูลต้นทางเพิ่มเติม
