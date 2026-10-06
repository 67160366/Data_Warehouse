"""Generate the column catalogue from schema with explicit meanings and units."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = {
    "date_key": ("YYYYMMDD", "คีย์วัน อ้างอิง dim_date"),
    "full_date": ("ISO date", "วันที่ปฏิทิน YYYY-MM-DD"),
    "year": ("year", "ปี ค.ศ."), "quarter": ("quarter", "ไตรมาส 1–4"),
    "month": ("month", "เดือน 1–12"), "month_name": ("—", "ชื่อเดือนภาษาอังกฤษ"),
    "week_of_year": ("ISO week", "สัปดาห์ตาม ISO 8601"), "day_of_week": ("day", "1 จันทร์ ถึง 7 อาทิตย์"),
    "is_weekend": ("0/1", "1 = เสาร์หรืออาทิตย์"),
    "period_phase": ("enum", "baseline_manual / assisted_3eyes"),
    "shift_key": ("key", "คีย์กะ อ้างอิง dim_shift"), "shift_name": ("—", "เช้า / บ่าย / ดึก"),
    "start_hour": ("hour", "ชั่วโมงเริ่มกะ 0–23"), "end_hour": ("hour", "ชั่วโมงจบกะ; กะดึกข้ามวัน แต่ลงวันที่เริ่มกะ"),
    "inspector_key": ("key", "คีย์พนักงาน อ้างอิง dim_inspector"), "inspector_code": ("—", "รหัส QC สมมติ ไม่ใช่ข้อมูลบุคคลจริง"),
    "tenure_years": ("years", "อายุงานสมมติ"), "experience_band": ("enum", "<1 ปี / 1-3 ปี / >3 ปี"),
    "device_key": ("key", "คีย์เครื่อง อ้างอิง dim_device; NULL เฉพาะ manual"),
    "device_code": ("—", "รหัสเครื่องสมมติ"), "model_version": ("—", "รุ่นจำลอง SIM-1.0"),
    "deployed_date": ("ISO date", "วันเริ่ม assisted ของเครื่องจำลอง"),
    "lot_key": ("key", "คีย์ lot อ้างอิง dim_lot"), "lot_code": ("—", "รหัส lot ไม่ซ้ำ"),
    "customer_name": ("—", "ชื่อลูกค้าสมมติ A/B/C กระจายข้ามไลน์"), "production_line": ("—", "LINE-1 ถึง LINE-3"),
    "lot_size": ("units", "จำนวนหน่วยจริงจำลองใน lot ห้ามคูณสามสถานการณ์"),
    "production_date": ("ISO date", "วันผลิตและตรวจ lot; รุ่นนี้ใช้เป็นวันเคลมด้วย"),
    "defect_key": ("key", "คีย์ประเภท: 0 งานดี; 1–7 ตำหนิหลัก"), "true_defect_key": ("key", "ความจริงของน็อต อ้างอิง dim_defect.defect_key"),
    "defect_name": ("—", "ชื่อตำหนิหลักหนึ่งประเภทต่อน็อต หรือ งานดี"), "defect_group": ("—", "กลุ่มพื้นที่ของตำหนิ"),
    "location": ("—", "ตำแหน่งตำหนิ"), "severity": ("enum", "none / minor / major / critical"),
    "is_defect": ("0/1", "1 = ของเสียจริง; 0 = งานดี"),
    "scenario_key": ("key", "0 manual, 1 Conservative, 2 Base, 3 Optimistic"),
    "scenario_name": ("enum", "N/A / Conservative / Base / Optimistic"), "description": ("—", "คำอธิบายสถานการณ์จำลอง"),
    "inspection_id": ("key", "รหัสแถวตรวจไม่ซ้ำ"), "unit_id": ("—", "รหัสน็อต LOT-xxxx-yyyy เดิมใน assisted ทั้งสามสถานการณ์"),
    "inspection_mode": ("enum", "manual / assisted"), "hour_in_shift": ("hour", "ชั่วโมงที่ 1–8 ภายในกะ"),
    "lighting_cond": ("enum", "good / dim / glare; สุ่มครั้งเดียวต่อน็อต"),
    "device_decision": ("enum", "PASS / FAIL / UNCERTAIN; NULL เฉพาะ manual"),
    "final_decision": ("enum", "PASS ส่งผ่าน QC / FAIL คัดออกหลังคนตัดสิน"),
    "override_flag": ("0/1", "1 เฉพาะเครื่อง FAIL แต่คนให้ final PASS"),
    "inspect_seconds": ("seconds/unit", "เวลาตรวจรวม; assisted FAIL/UNCERTAIN รวมเวลายืนยันเพิ่ม"),
    "claim_id": ("key", "รหัสแถวเคลมไม่ซ้ำ"), "qty_returned": ("units", "จำนวนคืน ไม่เกินของเสียที่หลุดใน lot/defect/scenario; อาจเป็น 0"),
    "claim_cost": ("THB", "ค่าเคลม; ใน mart รวมค่าแก้ไขงานคืนด้วย"), "rework_cost": ("THB", "ค่าแก้ไขงานที่คืน"),
    "units_inspected": ("units", "จำนวนตรวจใน lot/mode/scenario"), "true_defects": ("units", "จำนวนของเสียจริง"),
    "defects_caught": ("units", "จำนวนของเสียจริงที่ final FAIL"), "defects_escaped": ("units", "จำนวนของเสียจริงที่ final PASS"),
    "final_false_rejects": ("units", "งานดีที่ final FAIL (Final False Reject ไม่ใช่ Device False Alarm)"),
    "labor_cost": ("THB", "มูลค่าเวลา QC = วินาทีรวม × ค่าแรงต่อชั่วโมง / 3600"),
    "run_id": ("key", "รหัสรอบ ETL ของแต่ละขั้น"), "started_at": ("UTC timestamp", "เวลาเริ่มขั้น ETL"),
    "finished_at": ("UTC timestamp", "เวลาจบ; NULL ขณะ running"), "step_name": ("—", "ชื่อขั้น ETL"),
    "rows_read": ("rows/checks", "จำนวนอ่าน; ขั้น validate ใช้จำนวน checks"),
    "rows_loaded": ("rows/checks", "จำนวนโหลด; ขั้น validate ใช้จำนวน checks ที่ผ่าน"),
    "rows_rejected": ("rows", "จำนวนแถวที่แยกออกในรอบนี้"), "status": ("enum", "running / success / partial / failed"),
    "message": ("—", "ข้อความสรุปหรือข้อผิดพลาด"), "quarantine_id": ("key", "รหัส quarantine"),
    "source_table": ("—", "fact_inspection / fact_customer_claim"), "raw_row_json": ("JSON", "ค่าแถว staging เดิมที่ปฏิเสธ"),
    "reject_reason": ("—", "เหตุผลปฏิเสธแถว"), "created_at": ("UTC timestamp", "เวลาบันทึก quarantine"),
}


def main():
    con = sqlite3.connect(":memory:")
    con.executescript((ROOT / "src/schema.sql").read_text(encoding="utf-8"))
    lines = ["# Data Dictionary", "", "ข้อมูลจำลอง seed 42; CSV หลักเป็น UTF-8-SIG เปิดใน Excel ได้",
             "", "Inspection grain = unit_id × mode × scenario; assisted 3 สถานการณ์คือหน่วยเดิม ไม่ใช่ยอดผลิตสามเท่า",
             "Claim grain = lot × defect × scenario (วันที่เดียวกับ lot); หนึ่งตำหนิหลักต่อน็อต; lot อยู่วันและกะเดียว",
             "", "ชนิดด้านล่างคือชนิดใน SQLite; CSV ไม่มีชนิดข้อมูลในตัว ช่องว่างแทน NULL. PK รวมไม่อนุญาต NULL."]
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        lines += ["", f"## {table}", "", "| Column | Type | Unit | NULL | Meaning |", "|---|---|---|---|---|"]
        for _, name, dtype, required, default, pk in con.execute(f"PRAGMA table_info({table})"):
            unit, meaning = DESCRIPTIONS[name]
            lines.append(f"| `{name}`{' PK' if pk else ''} | {dtype} | {unit} | {'no' if required or pk else 'yes'} | {meaning} |")
    lines += ["", "## Staging และไฟล์สมมติฐาน", "", "`stg_*` มีชื่อคอลัมน์เหมือน CSV ต้นทางทั้ง 9 ตาราง; staging ยอมรับค่าว่างและชนิดผิดเพื่อให้ fact loader ตรวจและแยก quarantine ได้ ไม่มีการใช้ staging เป็นข้อมูล Dashboard โดยตรง", "",
              "| assumptions.csv column | Type | Unit | NULL | Meaning |", "|---|---|---|---|---|",
              "| param | TEXT | — | no | ชื่อสมมติฐานไม่ซ้ำ |", "| value | REAL | ตาม unit | no | ค่าที่ใช้ใน generator/ROI |",
              "| unit | TEXT | — | no | หน่วย |", "| source | TEXT | — | no | ASSUMPTION หรือแหล่งอ้างอิง |",
              "| note | TEXT | — | no | ความหมายของสมมติฐาน |", "", "ค่าตัวเลขและหน่วยจริงอยู่ใน [assumptions.csv](../config/assumptions.csv); schema และ CHECK constraints อยู่ใน [schema.sql](../src/schema.sql).",
              "SQL view columns เป็นผลรวมจาก facts ตาม [KPI definitions](../docs/03_kpi_definitions.md) ไม่ใช่ข้อมูลต้นทางเพิ่มเติม"]
    (ROOT / "data/data_dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    con.close()


if __name__ == "__main__":
    main()
