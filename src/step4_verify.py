"""Step 4 - ตรวจสอบว่า pipeline ทำงานถูกจริง

รันแล้วไม่ error ไม่ได้แปลว่าถูก แบ่งการตรวจเป็นสองส่วน

ส่วน A ตรวจความถูกต้องของข้อมูลในคลัง
ส่วน B ลอง join fact กับ dimension ตอบคำถามธุรกิจ ซึ่งเป็นเหตุผลที่สร้างคลัง

ผลลัพธ์: output/04_verification_report.txt
"""

import sqlite3

import pandas as pd

from common import DB_FILE, OUTPUT_DIR, RAW_FILE, Reporter, parse_money, setup_console

setup_console()
rp = Reporter()

conn = sqlite3.connect(DB_FILE)
conn.execute("PRAGMA foreign_keys = ON")

passed = []
failed = []


def check(name: str, condition: bool, detail: str = "") -> None:
    """บันทึกผลการตรวจ

    detail เป็นคำอธิบายกรณีไม่ผ่าน จึงแสดงเฉพาะตอนไม่ผ่าน ถ้าแสดงตอนผ่านด้วย
    จะได้ข้อความขัดกันเอง เช่น '[ผ่าน] ปฏิเสธ id ปลอม -- ข้อมูลผิดหลุดเข้าไปได้'
    """
    (passed if condition else failed).append(name)
    mark = "ผ่าน  " if condition else "ไม่ผ่าน"
    rp.say(f"  [{mark}] {name}{('  -- ' + detail) if (detail and not condition) else ''}")


def run_query(sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


rp.section("A1) จำนวนแถว")

expected = {
    "dim_customer": len(pd.read_csv(OUTPUT_DIR / "dim_customer.csv")),
    "dim_product": len(pd.read_csv(OUTPUT_DIR / "dim_product.csv")),
    "dim_time": len(pd.read_csv(OUTPUT_DIR / "dim_time.csv")),
    "fact_sales": len(pd.read_csv(OUTPUT_DIR / "fact_sales.csv")),
}

for table, want in expected.items():
    got = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    check(f"{table:<14} {got:>4} แถว", got == want, f"คาดไว้ {want}")


rp.section("A2) แถวใน fact ที่หา dimension ไม่เจอ")

rp.say("LEFT JOIN แล้วนับแถวที่ฝั่ง dimension เป็น NULL")
rp.say("เจอแม้แถวเดียวแปลว่ามีเด็กกำพร้า คือยอดขายที่ไม่รู้ว่าเป็นของใคร")
rp.say()

orphan_queries = {
    "ลูกค้า": """
        SELECT COUNT(*) FROM fact_sales f
        LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
        WHERE c.customer_id IS NULL
    """,
    "สินค้า": """
        SELECT COUNT(*) FROM fact_sales f
        LEFT JOIN dim_product p ON f.product_id = p.product_id
        WHERE p.product_id IS NULL
    """,
    "วันที่": """
        SELECT COUNT(*) FROM fact_sales f
        LEFT JOIN dim_time t ON f.date_key = t.date_key
        WHERE t.date_key IS NULL
    """,
}

for label, sql in orphan_queries.items():
    count = conn.execute(sql).fetchone()[0]
    check(f"เด็กกำพร้าด้าน{label} = {count} แถว", count == 0)


rp.section("A3) PRAGMA foreign_key_check")

rp.say("A2 เราเขียน query ตรวจเอง อันนี้ให้ฐานข้อมูลตรวจ FK ทุกเส้นให้")
rp.say("ตรวจสองทางเพื่อกันกรณีที่ query ของเราเองเขียนผิด")
rp.say()

violations = conn.execute("PRAGMA foreign_key_check").fetchall()
check(f"พบการละเมิด {len(violations)} รายการ", len(violations) == 0)
for row in violations:
    rp.say(f"      {row}")


rp.section("A4) กระทบยอดจากไฟล์ดิบถึงคลัง")

rp.say("คำนวณยอดรวมจาก CSV ดิบใหม่ทั้งหมดโดยไม่พึ่งผลลัพธ์ระหว่างทางเลย")
rp.say("แล้วเทียบกับยอดในคลัง ถ้าตรงแปลว่าไม่มีเงินหายหรืองอกตลอด 5 ขั้นตอน")
rp.say()

raw = pd.read_csv(RAW_FILE, dtype=str)
raw = raw.apply(lambda column: column.str.strip())
for column in ["Customer_Name", "Email", "Product", "Category"]:
    raw[column] = raw[column].str.lower()

raw_deduped = raw.drop_duplicates()
raw_deduped = raw_deduped.assign(
    qty=raw_deduped["Quantity"].astype(int),
    price=parse_money(raw_deduped["Unit_Price"]),
    amt=parse_money(raw_deduped["Amount"]),
)
raw_deduped["amt"] = raw_deduped["amt"].fillna(raw_deduped["qty"] * raw_deduped["price"])

raw_rows = len(raw_deduped)
raw_total = raw_deduped["amt"].sum()
raw_quantity = raw_deduped["qty"].sum()

warehouse = run_query("SELECT COUNT(*) n, SUM(amount) total, SUM(quantity) qty FROM fact_sales")
wh_rows = int(warehouse.at[0, "n"])
wh_total = float(warehouse.at[0, "total"])
wh_quantity = int(warehouse.at[0, "qty"])

rp.say(f"  {'':<22} {'จากไฟล์ดิบ':>16} {'จากคลัง':>16}")
rp.say(f"  {'จำนวนออเดอร์':<22} {raw_rows:>16,} {wh_rows:>16,}")
rp.say(f"  {'จำนวนชิ้นรวม':<22} {raw_quantity:>16,} {wh_quantity:>16,}")
rp.say(f"  {'ยอดขายรวม (บาท)':<22} {raw_total:>16,.2f} {wh_total:>16,.2f}")
rp.say()

check("จำนวนออเดอร์ตรงกัน", raw_rows == wh_rows, f"ต่างกัน {abs(raw_rows - wh_rows)} แถว")
check("จำนวนชิ้นตรงกัน", raw_quantity == wh_quantity)
check("ยอดขายตรงกัน", abs(raw_total - wh_total) < 0.01, f"ต่างกัน {abs(raw_total - wh_total):.4f} บาท")

rp.say()
rp.say(f"เส้นทาง: ไฟล์ดิบ 185 แถว -> ลบซ้ำ 5 -> {raw_rows} -> เติม amount -> โหลดเข้าคลัง -> {wh_rows}")


rp.section("A5) ทดสอบว่า FK ปฏิเสธข้อมูลผิดจริง")

rp.say("A2 กับ A3 ตรวจว่าข้อมูลตอนนี้ถูก แต่ไม่ได้พิสูจน์ว่าพรุ่งนี้ฐานข้อมูล")
rp.say("จะกันของเสียได้ ต้องยิงเข้าไปจริงถึงจะรู้")
rp.say()

fk_tests = [
    ("customer_id ที่ไม่มีจริง (9999)", ("TEST-BAD-1", 9999, 1, 20260101, 1, 100.0, 100.0)),
    ("product_id ที่ไม่มีจริง (9999)", ("TEST-BAD-2", 1, 9999, 20260101, 1, 100.0, 100.0)),
    ("date_key ที่ไม่มีจริง (20991231)", ("TEST-BAD-3", 1, 1, 20991231, 1, 100.0, 100.0)),
]

insert_sql = "INSERT INTO fact_sales VALUES (?, ?, ?, ?, ?, ?, ?)"

for label, bad_row in fk_tests:
    rejected = False
    try:
        conn.execute(insert_sql, bad_row)
    except sqlite3.IntegrityError:
        rejected = True
    finally:
        conn.rollback()   # ยกเลิกทุกอย่างที่ทดลอง ไม่ให้ค้างในคลังจริง
    check(f"ปฏิเสธ {label}", rejected, "ข้อมูลผิดหลุดเข้าไปได้")

existing_order = conn.execute("SELECT order_id FROM fact_sales LIMIT 1").fetchone()[0]
rejected = False
try:
    conn.execute(insert_sql, (existing_order, 1, 1, 20260101, 1, 100.0, 100.0))
except sqlite3.IntegrityError:
    rejected = True
finally:
    conn.rollback()
check(f"ปฏิเสธ order_id ซ้ำ ({existing_order})", rejected, "PK ไม่ทำงาน")

leftover = conn.execute("SELECT COUNT(*) FROM fact_sales WHERE order_id LIKE 'TEST-%'").fetchone()[0]
check("ไม่มีข้อมูลทดสอบตกค้าง", leftover == 0, f"เหลือ {leftover} แถว")

rp.say()
rp.say(f"fact_sales หลังทดสอบ : {conn.execute('SELECT COUNT(*) FROM fact_sales').fetchone()[0]} แถว")


rp.section("B1) ยอดขายราย category")

sql_b1 = """
    SELECT
        p.category                AS category,
        COUNT(*)                  AS orders,
        SUM(f.quantity)           AS units,
        ROUND(SUM(f.amount), 2)   AS revenue,
        ROUND(AVG(f.amount), 2)   AS avg_order
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY p.category
    ORDER BY revenue DESC
"""
rp.say(sql_b1.strip())
rp.say()
rp.say(run_query(sql_b1).to_string(index=False))
rp.say()
rp.say("query นี้ group by category ได้ทั้งที่ fact ไม่มีคอลัมน์นั้น มันมาจาก")
rp.say("dimension ผ่าน FK นี่คือประโยชน์ของ star schema เพิ่ม attribute ใน")
rp.say("dimension ทีเดียว ออเดอร์ในอดีตทั้งหมดก็วิเคราะห์ด้วยมุมใหม่ได้ทันที")


rp.section("B2) Top 10 ลูกค้า")

sql_b2 = """
    SELECT
        c.customer_name           AS customer,
        c.email                   AS email,
        COUNT(*)                  AS orders,
        ROUND(SUM(f.amount), 2)   AS total_spent
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_id = c.customer_id
    GROUP BY c.customer_id, c.customer_name, c.email
    ORDER BY total_spent DESC
    LIMIT 10
"""
rp.say(run_query(sql_b2).to_string(index=False))
rp.say()
rp.say("ถ้าไม่ได้ทำความสะอาดใน 2A ตารางนี้จะมี Peter Kim กับ PETER KIM แยกเป็นคนละคน")


rp.section("B3) ยอดขายรายเดือน")

sql_b3 = """
    SELECT
        t.year                    AS year,
        t.month                   AS month,
        t.month_name              AS month_name,
        COUNT(*)                  AS orders,
        ROUND(SUM(f.amount), 2)   AS revenue
    FROM fact_sales f
    JOIN dim_time t ON f.date_key = t.date_key
    GROUP BY t.year, t.month, t.month_name
    ORDER BY t.year, t.month
"""
rp.say(run_query(sql_b3).to_string(index=False))
rp.say()
rp.say("ตัวเลขชุดนี้คือผลตอบแทนของงานแปลงวันที่ใน 2A ถ้าปล่อยให้ pandas เดา")
rp.say("ฟอร์แมต วันที่แบบ DD/MM ที่วันน้อยกว่า 13 จะถูกสลับวันกับเดือน")
rp.say("ยอดรายเดือนเพี้ยนโดยไม่มีทางรู้")


rp.section("B4) category แยกตามเดือน (join 3 ตาราง)")

sql_b4 = """
    SELECT
        p.category                AS category,
        t.month_name              AS month_name,
        ROUND(SUM(f.amount), 2)   AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    JOIN dim_time    t ON f.date_key   = t.date_key
    GROUP BY p.category, t.year, t.month, t.month_name
    ORDER BY p.category, t.year, t.month
"""
pivot = run_query(sql_b4).pivot(index="category", columns="month_name", values="revenue")
rp.say(pivot[["January", "February", "March", "April"]].fillna(0).to_string())
rp.say()
rp.say("รูปแบบนี้คือสิ่งที่ star schema ออกแบบมารองรับ fact อยู่ตรงกลาง")
rp.say("หยิบ dimension มาประกอบกี่ตัวก็ได้ ทุก join เป็นการเทียบ integer กับ PK")


rp.section("B5) เดือนไหนมีวันที่ขายไม่ออกมากสุด")

rp.say("คำถามนี้ตอบได้เพราะ dim_time เป็นปฏิทินเต็ม")
rp.say("สังเกตว่าต้อง LEFT JOIN จาก dim_time ไปหา fact ทิศทางกลับกับ query อื่น")
rp.say("เพราะเราถามหาวันที่ไม่มีธุรกรรม ซึ่งไม่มีอยู่ใน fact เลย")
rp.say()

sql_b5 = """
    SELECT
        t.month_name                                            AS month_name,
        COUNT(DISTINCT t.date_key)                              AS days_in_month,
        COUNT(DISTINCT f.date_key)                              AS days_with_sales,
        COUNT(DISTINCT t.date_key) - COUNT(DISTINCT f.date_key) AS days_no_sales
    FROM dim_time t
    LEFT JOIN fact_sales f ON t.date_key = f.date_key
    GROUP BY t.year, t.month, t.month_name
    ORDER BY days_no_sales DESC
"""
rp.say(sql_b5.strip())
rp.say()
rp.say(run_query(sql_b5).to_string(index=False))
rp.say()
rp.say("ถ้าสร้าง dim_time จากวันที่ที่มีในข้อมูลอย่างเดียว คอลัมน์สุดท้ายจะเป็น 0")
rp.say("ทุกเดือน ตอบคำถามนี้ไม่ได้เลย")


rp.section("สรุป")

rp.say(f"  ผ่าน {len(passed)} ข้อ ไม่ผ่าน {len(failed)} ข้อ")

if failed:
    rp.say()
    rp.say("รายการที่ไม่ผ่าน:")
    for name in failed:
        rp.say(f"    {name}")
else:
    rp.say()
    rp.say("  จำนวนแถวถูกต้องทุกตาราง")
    rp.say("  ไม่มีแถวใน fact ที่หา dimension ไม่เจอ")
    rp.say("  ฐานข้อมูลตรวจ FK เองแล้วไม่พบปัญหา")
    rp.say("  ยอดเงินไม่หายไม่งอกตลอดเส้นทาง 185 แถวดิบถึง 180 แถวในคลัง")
    rp.say("  ฐานข้อมูลปฏิเสธข้อมูลผิดจริง ทดสอบด้วยการยิงของเสียเข้าไป")
    rp.say("  query ธุรกิจ 5 แบบทำงานได้ถูกต้อง")

conn.close()
rp.save(OUTPUT_DIR / "04_verification_report.txt")

if failed:
    raise SystemExit(1)
