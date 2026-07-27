"""Step 3B (Load) - สร้าง fact table พร้อม foreign key

FK คือเส้นที่ลากจาก fact ไปหา dimension ทั้ง 3 ตัว พอลากครบ star schema
ก็เป็นรูปเป็นร่าง fact อยู่ตรงกลาง dimension อยู่รอบ ๆ

ผลลัพธ์: ตาราง fact_sales (ว่าง) พร้อม FK และ index
"""

import sqlite3

from common import DB_FILE, OUTPUT_DIR, Reporter, setup_console

setup_console()
rp = Reporter()


FACT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS fact_sales (
        -- ต้องเขียน NOT NULL กำกับด้วย เพราะ SQLite ยอมให้ TEXT PRIMARY KEY
        -- เป็น NULL ได้ (พฤติกรรมเก่าที่เก็บไว้เพื่อความเข้ากันได้ย้อนหลัง)
        order_id    TEXT    PRIMARY KEY NOT NULL,

        customer_id INTEGER NOT NULL,
        product_id  INTEGER NOT NULL,
        date_key    INTEGER NOT NULL,

        quantity    INTEGER NOT NULL,
        unit_price  REAL    NOT NULL,
        amount      REAL    NOT NULL,

        FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
        FOREIGN KEY (product_id)  REFERENCES dim_product(product_id),
        FOREIGN KEY (date_key)    REFERENCES dim_time(date_key)
    )
"""

# SQLite ไม่สร้าง index ให้คอลัมน์ FK อัตโนมัติ ต้องสร้างเอง
FACT_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fact_customer ON fact_sales(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_product  ON fact_sales(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_date     ON fact_sales(date_key)",
]


rp.section("1) เปิดการตรวจสอบ foreign key")

conn = sqlite3.connect(DB_FILE)

before = conn.execute("PRAGMA foreign_keys").fetchone()[0]
conn.execute("PRAGMA foreign_keys = ON")
after = conn.execute("PRAGMA foreign_keys").fetchone()[0]

rp.say(f"ค่าเริ่มต้นตอนเปิด connection : foreign_keys = {before}")
rp.say(f"หลังสั่ง PRAGMA               : foreign_keys = {after}")
rp.say()
rp.say("ถ้าไม่สั่งเปิด คำสั่ง FOREIGN KEY ที่เขียนไว้ใน CREATE TABLE จะเป็นแค่")
rp.say("ข้อความประกอบ ไม่บังคับอะไรเลย ใส่ customer_id = 9999 ที่ไม่มีจริงก็เข้าได้")
rp.say()
rp.say("และค่านี้ไม่ถูกจำไว้ในไฟล์ ต้องสั่งใหม่ทุกครั้งที่เปิด connection")
rp.say("แปลว่า step3c กับ step4 ต้องสั่งเองด้วย")


rp.section("2) เช็คว่า dimension พร้อมแล้ว")

required = ["dim_customer", "dim_product", "dim_time"]
existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

for table in required:
    rp.say(f"  {table:<14} {'พบ' if table in existing else 'ไม่พบ'}")

missing_tables = [t for t in required if t not in existing]
if missing_tables:
    raise RuntimeError(
        f"ยังไม่มีตาราง {missing_tables} ต้องรัน step3a_schema_dim.py ก่อน\n"
        f"เพราะ FOREIGN KEY ต้องอ้างอิงตารางที่มีอยู่จริงแล้ว"
    )

rp.say()
rp.say("ต้องสร้าง dimension ก่อน fact เสมอ")


rp.section("3) สร้าง fact_sales")

conn.execute(FACT_SCHEMA)
conn.commit()

rp.say(f"  {'cid':<4} {'name':<13} {'type':<9} {'notnull':<8} {'pk'}")
for cid, name, col_type, notnull, _default, pk in conn.execute("PRAGMA table_info(fact_sales)"):
    rp.say(f"  {cid:<4} {name:<13} {col_type:<9} {notnull:<8} {pk}")

rp.say()
rp.say("order_id ได้ notnull = 1 เพราะเขียน NOT NULL กำกับไว้")
rp.say("ถ้าเขียนแค่ TEXT PRIMARY KEY เฉย ๆ SQLite จะยอมให้ NULL เข้ามาจริง ๆ")
rp.say("(PostgreSQL กับ MySQL ตั้ง PK เป็น NOT NULL ให้อัตโนมัติ SQLite ไม่ทำ)")


rp.section("4) foreign key ที่สร้างไว้")

rp.say(f"  {'id':<4} {'คอลัมน์ใน fact':<14} {'ตารางปลายทาง':<16} {'คอลัมน์ปลายทาง'}")
for row in conn.execute("PRAGMA foreign_key_list(fact_sales)"):
    fk_id, _seq, ref_table, from_col, to_col, *_rest = row
    rp.say(f"  {fk_id:<4} {from_col:<14} {ref_table:<16} {to_col}")

rp.say()
rp.say("                dim_customer")
rp.say("                     |")
rp.say("                     | customer_id")
rp.say("                     v")
rp.say("dim_time  <----- fact_sales ----->  dim_product")
rp.say("        date_key            product_id")


rp.section("5) index บนคอลัมน์ FK")

for statement in FACT_INDEXES:
    conn.execute(statement)
conn.commit()

for row in conn.execute("PRAGMA index_list(fact_sales)"):
    _seq, index_name, unique, origin, _partial = row
    kind = "อัตโนมัติจาก PK" if origin == "pk" else "สร้างเอง"
    rp.say(f"  {index_name:<32} unique={unique}  {kind}")

rp.say()
rp.say("SQLite ไม่สร้าง index ให้ FK เองแบบ MySQL ถ้าไม่สร้างจะเจอสองปัญหา")
rp.say("  join กับ dimension ทีไรต้องสแกน fact ทั้งตาราง")
rp.say("  ลบหรือแก้แถวใน dimension ต้องสแกน fact ทั้งตารางเพื่อเช็คว่ามีใครอ้างอิงอยู่")


rp.section("6) สถานะตอนนี้")

for table in ["dim_customer", "dim_product", "dim_time", "fact_sales"]:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    rp.say(f"  {table:<16} {count} แถว")

rp.say()
rp.say("โครงสร้างครบแล้วแต่ยังไม่มีข้อมูล ขั้นต่อไปคือ 3C")

conn.close()
rp.save(OUTPUT_DIR / "03b_fact_schema_report.txt")
