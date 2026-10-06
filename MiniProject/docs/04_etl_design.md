# ETL และการตรวจสอบ

`CSV UTF-8-SIG → stg_* → 7 dimensions + 2 facts → fact_lot_summary / SQL views → read-only Dashboard`

1. `01_create_schema.py` สร้าง schema; `--reset` ล้างเฉพาะฐานข้อมูลที่กำหนด
2. `02_load_staging.py` ต้องพบ CSV ทั้ง 9 ตาราง แทนที่ staging; รักษาข้อความ `N/A` ไม่ตีความเป็น null
3. `03_load_dimensions.py` อ่านจาก staging แล้ว upsert dimensions (ไม่อ่าน CSV ซ้ำ)
4. `04_load_facts.py` อ่าน staging ตรวจชนิดข้อมูล null FK enum ช่วงตัวเลข grain และกฎ mode/scenario; ตรวจวันที่และกะตรง lot, จำนวนคืนไม่เกินของเสียหลุด แทนที่ facts ใน transaction เดียว ข้อมูลผิดทั้ง 2 facts ลง quarantine พร้อม JSON ต้นทางและเหตุผล
5. `05_build_marts.py` สร้าง mart ระดับ lot/scenario ใหม่ รวมเคลมก่อน join จึงไม่ทำให้ต้นทุนคูณจำนวนตรวจ แล้วสร้าง views
6. `06_validate.py` ตรวจ FK, SQLite integrity, จับได้+หลุด=ของเสียจริง, ความตรงของ unit_id ข้ามสถานการณ์, จำนวน lot, และ `staging = loaded + rejected` ของ fact load รอบล่าสุด แยก complete-lot/scenario checks เฉพาะ clean load

Run log เริ่ม `running` จบ `success`, `partial` หรือ `failed` พร้อมเวลา จำนวนอ่าน/โหลด/ปฏิเสธ และข้อความ Quarantine เก่าคงไว้เป็นหลักฐาน แต่ไม่นำมาบวกรอบปัจจุบัน `partial` หมายถึงมี rejected ที่ถูกแยกสำเร็จ ไม่ได้หมายถึง pipeline ล้มเหลว

รายงาน: `reports/data_quality_report.md`, `reports/etl_run_log.csv`, `reports/data_manifest.json` (hash ของ CSV และ SQLite) ทุกครั้งที่ ETL เปลี่ยน snapshot ต้องสร้างรายงานใหม่

การทดสอบใช้ temporary database ผ่าน `THREEEYES_DB`, `THREEEYES_RAW`, `THREEEYES_REPORTS`; ไม่แตะฐานส่งงาน และไม่เรียก `all` จาก test จึงไม่มี recursion ทดสอบข้อมูลเสีย 10 แถว (5 inspections + 5 claims) โดยเปลี่ยน staging โดยตรงเพื่อยืนยัน downstream อ่าน staging จริง จากนั้น clean rerun ต้องยังผ่านแม้มี quarantine เก่า

Dashboard เปิด SQLite `mode=ro` และ cache ตาม SHA-256 ที่เปลี่ยนเมื่อไฟล์เปลี่ยน ไม่รัน ETL ขณะผู้ชมเข้าใช้ ค่า assumptions โหลดจาก CSV ทุกครั้ง จึงเห็นการเปลี่ยนราคาและค่าแรง; ถ้าเปลี่ยน `confirmation_seconds` หรือพารามิเตอร์ generator ต้องสร้างข้อมูลและ ETL ใหม่
