"""Step 3A (Load) - สร้างโครงสร้างตาราง dimension ใน SQLite

ขั้นนี้สร้างแต่โครง ยังไม่ใส่ข้อมูล เพราะ schema เปลี่ยนไม่บ่อยแต่ข้อมูล
โหลดทุกวัน แยกกันไว้จะได้ไม่ต้องเสี่ยงไปยุ่งกับ schema ทุกครั้งที่โหลด

constraint ที่กำหนดตรงนี้เป็นกฎที่ฐานข้อมูลบังคับเอง ต่อให้โค้ด Python
มีบั๊กวันหนึ่ง ฐานข้อมูลก็ยังปฏิเสธข้อมูลที่ผิดกฎ

ผลลัพธ์: warehouse/dw.sqlite (ตาราง dimension ว่าง 3 ตาราง)
"""

import sqlite3

from common import DB_FILE, OUTPUT_DIR, WAREHOUSE_DIR, Reporter, setup_console

setup_console()
rp = Reporter()


DIMENSION_SCHEMAS = {
    "dim_customer": """
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_id   INTEGER PRIMARY KEY,
            customer_name TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE
        )
    """,
    # ไม่มี unit_price เพราะราคาที่ขายจริงเป็น measure ไม่ใช่คุณสมบัติของสินค้า
    "dim_product": """
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id   INTEGER PRIMARY KEY,
            product_name TEXT    NOT NULL UNIQUE,
            category     TEXT    NOT NULL
        )
    """,
    # full_date เก็บเป็น TEXT รูปแบบ ISO8601 เพราะ SQLite ไม่มีชนิด DATE
    "dim_time": """
        CREATE TABLE IF NOT EXISTS dim_time (
            date_key     INTEGER PRIMARY KEY,
            full_date    TEXT    NOT NULL UNIQUE,
            year         INTEGER NOT NULL,
            quarter      INTEGER NOT NULL,
            month        INTEGER NOT NULL,
            month_name   TEXT    NOT NULL,
            day          INTEGER NOT NULL,
            weekday_name TEXT    NOT NULL,
            is_weekend   INTEGER NOT NULL
        )
    """,
}


rp.section("1) เชื่อมต่อฐานข้อมูล")

WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)

is_new = not DB_FILE.exists()
conn = sqlite3.connect(DB_FILE)   # สร้างไฟล์ให้เองถ้ายังไม่มี

rp.say(f"ไฟล์   : {DB_FILE}")
rp.say(f"สถานะ  : {'สร้างใหม่' if is_new else 'เปิดไฟล์เดิม'}")
rp.say(f"SQLite : {sqlite3.sqlite_version}")
rp.say()
rp.say("SQLite เก็บทั้งฐานข้อมูลไว้ในไฟล์เดียว ไม่ต้องติดตั้ง server เหมาะกับงาน local")
rp.say("แต่หลักการ star schema ที่ใช้ตรงนี้เหมือนกันหมด ย้ายไป PostgreSQL")
rp.say("หรือ BigQuery ก็คิดแบบเดียวกัน")


rp.section("2) สร้างตาราง")

for table_name, ddl in DIMENSION_SCHEMAS.items():
    conn.execute(ddl)
    rp.say(f"  {table_name}")
conn.commit()

rp.say()
rp.say("ใช้ IF NOT EXISTS เพื่อให้รันซ้ำได้โดยไม่ error")
rp.say("ถ้าเขียน CREATE TABLE เฉย ๆ รอบสองจะพังว่า table already exists")


rp.section("3) schema ที่ลงจริง")

rp.say("PRAGMA table_info ใช้ดูโครงสร้างตาราง คอลัมน์ pk = 1 คือ Primary Key")
rp.say()

for table_name in DIMENSION_SCHEMAS:
    rp.say(f"--- {table_name} ---")
    rp.say(f"  {'cid':<4} {'name':<14} {'type':<9} {'notnull':<8} {'pk'}")
    for cid, name, col_type, notnull, _default, pk in conn.execute(
        f"PRAGMA table_info({table_name})"
    ):
        rp.say(f"  {cid:<4} {name:<14} {col_type:<9} {notnull:<8} {pk}")
    rp.say()


rp.section("4) เกร็ดของ SQLite ที่ต้องรู้")

rp.say("INTEGER PRIMARY KEY มีความหมายพิเศษ")
rp.say("  เขียนแบบนี้เป๊ะ ๆ คอลัมน์จะกลายเป็น alias ของ rowid ซึ่งเป็นตัวชี้")
rp.say("  ตำแหน่งจริงในไฟล์ ค้นหาเร็วสุดโดยไม่ต้องสร้าง index เพิ่ม")
rp.say("  แต่ถ้าเขียน INT PRIMARY KEY จะไม่ได้ผลนี้ กลายเป็น index ธรรมดา")
rp.say()

rp.say("SQLite ไม่มีชนิดข้อมูล DATE")
rp.say("  ต้องเก็บวันที่เป็น TEXT รูปแบบ ISO8601 เท่านั้น เพราะเรียงตามตัวอักษร")
rp.say("  แล้วได้ลำดับเวลาถูกต้องพอดี")

iso_sorted = sorted(["2026-04-24", "2026-01-15", "2026-12-01", "2026-02-03"])
slash_sorted = sorted(["24/04/2026", "15/01/2026", "01/12/2026", "03/02/2026"])
rp.say()
rp.say(f"  ISO8601    : {iso_sorted}")
rp.say(f"  DD/MM/YYYY : {slash_sorted}")
rp.say("  อันหลังเรียงตามวันที่ ไม่ใช่ตามปี ใช้ WHERE เทียบช่วงเวลาไม่ได้")
rp.say()

rp.say("UNIQUE บน email กับ product_name เป็นตาข่ายชั้นสุดท้าย")
rp.say("  เรา dedup ไว้แล้วใน 2A แต่ถ้าโค้ดตรงนั้นพังวันหนึ่ง ฐานข้อมูลจะปฏิเสธเอง")
rp.say()

rp.say("ยังไม่มีข้อมูลในตาราง:")
for table_name in DIMENSION_SCHEMAS:
    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    rp.say(f"  {table_name:<14} {count} แถว")

conn.close()
rp.save(OUTPUT_DIR / "03a_schema_report.txt")
