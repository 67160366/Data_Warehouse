"""Step 3C (Load) - ย้ายข้อมูลจาก pandas เข้า SQLite

เรื่องสำคัญของขั้นนี้คือ idempotency คือรันกี่ครั้งก็ได้ผลเหมือนเดิม
ถ้าไม่มี รันสองรอบข้อมูล 180 แถวจะกลายเป็น 360 ยอดขายเบิ้ลโดยไม่มี error ฟ้อง
และ pipeline จริงถูกรันซ้ำบ่อยมาก ทั้ง rerun ตอน network หลุด backfill ย้อนหลัง
หรือแค่ทดสอบ

วิธีที่ใช้: full refresh ล้างของเดิมทิ้งแล้วโหลดใหม่ทั้งหมด
"""

import sqlite3
from contextlib import closing

import pandas as pd

from common import DB_FILE, OUTPUT_DIR, Reporter, setup_console

setup_console()
rp = Reporter()

DIMENSION_TABLES = ["dim_customer", "dim_product", "dim_time"]
FACT_TABLE = "fact_sales"


rp.section("1) อ่านข้อมูลที่เตรียมไว้")

tables = {
    "dim_customer": pd.read_csv(OUTPUT_DIR / "dim_customer.csv"),
    "dim_product": pd.read_csv(OUTPUT_DIR / "dim_product.csv"),
    "dim_time": pd.read_csv(OUTPUT_DIR / "dim_time.csv"),
    "fact_sales": pd.read_csv(OUTPUT_DIR / "fact_sales.csv"),
}

for name, table in tables.items():
    rp.say(f"  {name:<14} {len(table):>4} แถว")

expected_counts = {name: len(table) for name, table in tables.items()}


rp.section("2) ลำดับการลบและการโหลด")

rp.say("กฎเดียวที่ต้องรักษาไว้คือ ห้ามมีแถวใน fact ที่ชี้ไปหา dimension ที่ไม่มีตัวตน")
rp.say("จากกฎนี้ได้ลำดับที่สลับกันพอดี:")
rp.say()
rp.say("  ลบ   fact ก่อน dimension")
rp.say("       ถ้าลบ dim_customer ก่อน แถวใน fact จะกลายเป็นเด็กกำพร้าทันที")
rp.say()
rp.say("  โหลด dimension ก่อน fact")
rp.say("       ถ้าโหลด fact ก่อน จะไม่มี customer_id ให้ชี้ไปหา")
rp.say()
rp.say("ทำผิดลำดับทั้งสองกรณีจะเจอ FOREIGN KEY constraint failed เหมือนกัน")


rp.section("3) โหลดข้อมูล")

conn = sqlite3.connect(DB_FILE)
conn.execute("PRAGMA foreign_keys = ON")   # ต้องสั่งใหม่ทุก connection

rp.say(f"foreign_keys = {conn.execute('PRAGMA foreign_keys').fetchone()[0]}")
before_counts = {
    name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in tables
}
rp.say(f"จำนวนแถวก่อนโหลด : {before_counts}")
rp.say()

try:
    # with conn คือ transaction สำเร็จหมดถึงจะ commit เจอ exception จะ rollback ให้
    with conn:
        rp.say("ล้างของเดิม:")
        for table in [FACT_TABLE] + DIMENSION_TABLES:
            deleted = conn.execute(f"DELETE FROM {table}").rowcount
            rp.say(f"  DELETE FROM {table:<14} {deleted} แถว")

        rp.say()
        rp.say("โหลดใหม่:")
        for table in DIMENSION_TABLES + [FACT_TABLE]:
            # ต้องเป็น append ไม่ใช่ replace เพราะ replace จะ DROP TABLE
            # แล้วสร้างใหม่จาก dtype ของ DataFrame ทำให้ PK/FK/NOT NULL หายหมด
            tables[table].to_sql(table, conn, if_exists="append", index=False)
            rp.say(f"  to_sql {table:<14} {len(tables[table])} แถว")

except sqlite3.IntegrityError as error:
    rp.say()
    rp.say(f"โหลดล้มเหลว: {error}")
    rp.say("transaction rollback กลับหมดแล้ว คลังไม่ได้อยู่ในสภาพครึ่ง ๆ กลาง ๆ")
    raise

rp.say()
rp.say("commit สำเร็จ")


rp.section("4) เทียบจำนวนแถว")

rp.say(f"  {'ตาราง':<16} {'จาก CSV':>8} {'ใน SQLite':>10}")
all_match = True
for name, expected in expected_counts.items():
    actual = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    all_match &= actual == expected
    mark = "" if actual == expected else "  <-- ไม่ตรง"
    rp.say(f"  {name:<16} {expected:>8} {actual:>10}{mark}")

if not all_match:
    raise ValueError("จำนวนแถวใน SQLite ไม่ตรงกับ CSV การโหลดผิดพลาด")


rp.section("5) ทำไมไม่ใช้ if_exists='replace'")

rp.say("ทดลองในฐานข้อมูลชั่วคราวในหน่วยความจำ ไม่แตะคลังจริง")
rp.say()

demo = sqlite3.connect(":memory:")
demo.execute("""
    CREATE TABLE dim_customer (
        customer_id   INTEGER PRIMARY KEY,
        customer_name TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE
    )
""")


def describe(connection, label):
    rp.say(f"  {label}")
    rp.say(f"    {'name':<14} {'type':<9} {'notnull':<8} {'pk'}")
    for _cid, name, col_type, notnull, _default, pk in connection.execute(
        "PRAGMA table_info(dim_customer)"
    ):
        rp.say(f"    {name:<14} {col_type:<9} {notnull:<8} {pk}")


describe(demo, "schema ที่เราออกแบบไว้:")
tables["dim_customer"].to_sql("dim_customer", demo, if_exists="replace", index=False)
rp.say()
describe(demo, "หลังใช้ replace:")

rp.say()
rp.say("pk หายหมด notnull หายหมด UNIQUE บน email ก็หาย")
rp.say("เพราะ replace ทำงานสามขั้น: DROP TABLE -> CREATE จาก dtype ของ DataFrame -> INSERT")
rp.say("แปลว่างานใน 3A กับ 3B สูญเปล่า และ step 4 ที่จะทดสอบ FK ก็ไม่มีความหมาย")
rp.say()

rp.say("ยังมีปัญหาที่สอง ลองใช้กับตารางที่มี fact อ้างอิงอยู่จริง:")
# ใช้ closing ด้วยเพราะ with บน connection ปิดแค่ transaction ไม่ได้ปิด connection
with closing(sqlite3.connect(DB_FILE)) as test_conn:
    try:
        with test_conn:
            test_conn.execute("PRAGMA foreign_keys = ON")
            test_conn.execute("DROP TABLE dim_customer")   # ขั้นแรกที่ replace ทำ
        rp.say("  ไม่เกิด error ซึ่งไม่ควรมาถึงบรรทัดนี้")
    except sqlite3.IntegrityError as error:
        rp.say(f"  sqlite3.IntegrityError: {error}")
        rp.say("  SQLite ปฏิเสธเพราะ fact_sales ยังอ้างอิง dim_customer อยู่")
        rp.say("  แปลว่า replace ไม่ใช่แค่ทำ schema หาย แต่รันไม่ผ่านเลย")
        rp.say("  (ข้อนี้จะเกิดก็ต่อเมื่อเปิด PRAGMA foreign_keys ไว้ ลืมเปิดเมื่อไหร่")
        rp.say("   DROP จะผ่านฉลุยและ schema พังเงียบ ๆ)")

demo.close()

rp.say()
rp.say("คู่ที่ถูกคือ DELETE FROM (ล้างข้อมูลแต่เก็บ schema) + to_sql(if_exists='append')")


rp.section("6) ตัวอย่างข้อมูลในคลัง")

for table in DIMENSION_TABLES + [FACT_TABLE]:
    rp.say(f"--- {table} ---")
    columns = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    rp.say(f"  {columns}")
    for row in conn.execute(f"SELECT * FROM {table} LIMIT 3"):
        rp.say(f"  {row}")
    rp.say()

total = conn.execute("SELECT ROUND(SUM(amount), 2) FROM fact_sales").fetchone()[0]
rp.say(f"ยอดขายรวมในคลัง : {total:,.2f} บาท (ต้องตรงกับที่ 2B รายงานไว้)")


rp.section("7) idempotency")

rp.say("ลองรันสคริปต์นี้อีกรอบ จำนวนแถวต้องเท่าเดิม:")
for name, expected in expected_counts.items():
    rp.say(f"  {name:<16} {expected} แถว ไม่ใช่ {expected * 2}")
rp.say()
rp.say("ถ้าไม่มี DELETE FROM ข้างบน รอบสองจะได้สองเท่า รอบสามสามเท่า และไม่มี error ฟ้อง")

conn.close()
rp.save(OUTPUT_DIR / "03c_load_report.txt")
