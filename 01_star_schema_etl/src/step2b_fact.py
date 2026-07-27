"""Step 2B (Transform) - สร้าง fact table

fact เก็บของสองอย่างเท่านั้น: FK ที่ชี้ไป dimension กับ measure ที่เอาไปคำนวณได้

งานในขั้นนี้: แปลงตัวเลข -> เติม amount ที่หาย -> left join กับ dimension
แทนข้อความด้วย FK -> ตรวจว่าไม่มีแถวหายหรือเบิ้ล

ผลลัพธ์: output/fact_sales.csv
"""

import pandas as pd

from common import OUTPUT_DIR, Reporter, parse_money, save_csv, setup_console

setup_console()
rp = Reporter()


rp.section("1) อ่านผลลัพธ์จาก 2A")

orders = pd.read_csv(OUTPUT_DIR / "02a_clean_orders.csv", dtype=str)
dim_customer = pd.read_csv(OUTPUT_DIR / "dim_customer.csv")
dim_product = pd.read_csv(OUTPUT_DIR / "dim_product.csv")
dim_time = pd.read_csv(OUTPUT_DIR / "dim_time.csv")

# ตัวเลขนี้ห้ามเปลี่ยนตลอดทั้งไฟล์ ใช้เทียบทุกขั้นตอน
EXPECTED_ROWS = len(orders)

rp.say(f"clean_orders  : {len(orders):>4} แถว  <- ตัวตั้งต้น")
rp.say(f"dim_customer  : {len(dim_customer):>4} แถว")
rp.say(f"dim_product   : {len(dim_product):>4} แถว")
rp.say(f"dim_time      : {len(dim_time):>4} แถว")


rp.section("2) แปลงข้อความตัวเลขเป็น float")

rp.say("ก่อนแปลง:")
for _, row in orders[orders["amount_raw"].notna()].head(5).iterrows():
    rp.say(f"  unit_price = {row['unit_price_raw']:<12} amount = {row['amount_raw']}")

orders["quantity"] = orders["quantity"].astype(int)
orders["unit_price"] = parse_money(orders["unit_price_raw"])
orders["amount"] = parse_money(orders["amount_raw"])

rp.say()
rp.say("หลังแปลง:")
rp.say(orders[["order_id", "quantity", "unit_price", "amount"]].head(5).to_string(index=False))
rp.say()
rp.say(f"unit_price แปลงไม่ได้ : {orders['unit_price'].isna().sum()} แถว")
rp.say(f"amount ที่ยังว่าง      : {orders['amount'].isna().sum()} แถว")

if orders["unit_price"].isna().any():
    raise ValueError("unit_price แปลงเป็นตัวเลขไม่ได้บางแถว ตรวจ parse_money()")


rp.section("3) เติม amount ที่หาย")

rp.say("สมมติฐาน amount = quantity x unit_price")
rp.say("แต่ต้องพิสูจน์กับแถวที่มีค่าอยู่แล้วก่อน ไม่ใช่เชื่อเลย")
rp.say()

calculated = orders["quantity"] * orders["unit_price"]
has_amount = orders["amount"].notna()

# ยอมให้ต่างไม่เกิน 0.01 บาทจากการปัดทศนิยม
difference = (calculated[has_amount] - orders.loc[has_amount, "amount"]).abs()
mismatched = (difference > 0.01).sum()

rp.say(f"แถวที่มี amount อยู่แล้ว : {has_amount.sum()}")
rp.say(f"แถวที่สูตรไม่ตรง        : {mismatched}")
rp.say(f"ผลต่างสูงสุด            : {difference.max():.4f} บาท")

if mismatched > 0:
    bad = orders.loc[has_amount & (difference > 0.01)]
    raise ValueError(
        f"สูตรไม่ตรงกับ amount จริง {mismatched} แถว ห้ามเอาไปเติมค่าที่หาย\n"
        f"อาจมีส่วนลดหรือภาษีที่เราไม่รู้ ต้องกลับไปถามเจ้าของข้อมูลก่อน\n"
        f"{bad[['order_id', 'quantity', 'unit_price', 'amount']].to_string(index=False)}"
    )

rp.say()
rp.say("สูตรผ่าน เอาไปเติมค่าที่หายได้")
rp.say()

filled_count = orders["amount"].isna().sum()
filled_examples = orders.loc[orders["amount"].isna(), ["order_id", "quantity", "unit_price"]].head(5)
orders["amount"] = orders["amount"].fillna(calculated)

rp.say(f"เติมไป {filled_count} แถว ตัวอย่าง:")
for _, row in filled_examples.iterrows():
    rp.say(f"  {row['order_id']} : {int(row['quantity'])} x {row['unit_price']:,.2f} "
           f"= {row['quantity'] * row['unit_price']:,.2f}")

rp.say()
rp.say(f"amount ที่ยังว่าง : {orders['amount'].isna().sum()} แถว")


rp.section("4) เชื่อม FK ด้วย left join")

rp.say("ทำไมไม่ใช้ inner join:")
rp.say("  ข้อมูลสมบูรณ์ทั้งสองแบบให้ผลเหมือนกัน แต่ถ้ามีแถว join ไม่ติด")
rp.say("  inner join ทิ้งแถวนั้นหายไปเงียบ ๆ ไม่มี error ไม่มีใครรู้ว่ายอดขายหาย")
rp.say("  left join เก็บแถวไว้ FK เป็น null แล้วเรา assert จับได้")
rp.say()

amount_before_join = orders["amount"].sum()

# validate='many_to_one' บังคับให้ pandas เช็คว่าฝั่ง dimension ไม่มี key ซ้ำ
# ถ้าซ้ำจะเกิด fan-out ออเดอร์ถูกคูณสอง ยอดขายเบิ้ลโดยไม่มี error
fact = orders.merge(
    dim_customer[["customer_id", "email"]],
    how="left", left_on="customer_key", right_on="email",
    validate="many_to_one",
)

dim_product_key = dim_product.copy()
dim_product_key["product_key"] = dim_product_key["product_name"].str.lower()
fact = fact.merge(
    dim_product_key[["product_id", "product_key"]],
    how="left", on="product_key", validate="many_to_one",
)

fact["date_key"] = fact["date_key"].astype(int)
fact = fact.merge(dim_time[["date_key"]], how="left", on="date_key", validate="many_to_one")

rp.say("join ครบทั้ง 3 dimension")


rp.section("5) ตรวจผลการ join")

rp.say(f"[1] จำนวนแถว {EXPECTED_ROWS} -> {len(fact)}")
if len(fact) != EXPECTED_ROWS:
    raise ValueError(
        f"จำนวนแถวเปลี่ยนจาก {EXPECTED_ROWS} เป็น {len(fact)}\n"
        f"  เพิ่มขึ้น = dimension มี key ซ้ำ เกิด fan-out ยอดขายเบิ้ล\n"
        f"  ลดลง    = merge ทิ้งแถว ซึ่งไม่ควรเกิดกับ left join"
    )
rp.say("    ผ่าน")

rp.say()
rp.say("[2] FK ที่ join ไม่ติด:")
orphans = {}
for fk in ["customer_id", "product_id", "date_key"]:
    missing = fact[fk].isna().sum()
    orphans[fk] = missing
    rp.say(f"    {fk:<12} {missing}")

if any(orphans.values()):
    broken = fact[fact[list(orphans)].isna().any(axis=1)]
    raise ValueError(
        f"มีแถว join ไม่ติด {len(broken)} แถว dimension ขาดค่าที่ fact ต้องใช้\n"
        f"{broken[['order_id', 'customer_key', 'product_key', 'date_key']].to_string(index=False)}"
    )
rp.say("    ผ่าน")

amount_after_join = fact["amount"].sum()
rp.say()
rp.say(f"[3] ยอดรวม {amount_before_join:,.2f} -> {amount_after_join:,.2f}")
if abs(amount_before_join - amount_after_join) > 0.01:
    raise ValueError("ยอดรวมเปลี่ยนหลัง join ข้อมูลผิดพลาดระหว่างทาง")
rp.say("    ผ่าน")


rp.section("6) ทิ้งคอลัมน์ข้อความ")

text_columns = ["customer_key", "product_key", "email", "unit_price_raw", "amount_raw"]
rp.say(f"ทิ้ง: {text_columns}")

fact_sales = fact[[
    "order_id",      # degenerate dimension
    "customer_id",   # FK -> dim_customer
    "product_id",    # FK -> dim_product
    "date_key",      # FK -> dim_time
    "quantity",
    "unit_price",
    "amount",
]].copy()

fact_sales["customer_id"] = fact_sales["customer_id"].astype(int)
fact_sales["product_id"] = fact_sales["product_id"].astype(int)
fact_sales["amount"] = fact_sales["amount"].round(2)
fact_sales = fact_sales.sort_values("order_id").reset_index(drop=True)

rp.say()
rp.say(fact_sales.head(10).to_string(index=False))
rp.say()
rp.say("order_id เก็บไว้ในฐานะ degenerate dimension คือ key ที่ไม่มีตาราง")
rp.say("dimension ของตัวเอง เพราะไม่มี attribute อื่นให้เก็บ แต่ยังต้องใช้")
rp.say("สืบกลับไปหาข้อมูลต้นทาง และใช้เป็น PK ตอน load")


rp.section("7) ผลของการแทนข้อความด้วย FK")

text_size = orders["customer_key"].str.len().sum() + orders["product_key"].str.len().sum()
key_size = len(fact_sales) * 2 * 4

rp.say(f"เก็บเป็นข้อความ  : ~{text_size:,} bytes")
rp.say(f"เก็บเป็น integer : ~{key_size:,} bytes")
rp.say(f"ประหยัด          : {(1 - key_size / text_size) * 100:.0f}%")
rp.say()
rp.say(f"ข้อมูล {len(fact_sales)} แถวไม่รู้สึกอะไร แต่ fact จริงมีเป็นสิบล้านแถว")
rp.say("ส่วนต่างตรงนี้คือหลาย GB และ join ด้วย integer ก็เร็วกว่าเทียบข้อความ")


rp.section("8) บันทึกผลลัพธ์")

save_csv(fact_sales, OUTPUT_DIR / "fact_sales.csv")
rp.say(f"  fact_sales.csv  {len(fact_sales)} แถว")
rp.say()
rp.say(f"ยอดขายรวม : {fact_sales['amount'].sum():,.2f} บาท")
rp.say("Step 4 จะเอาตัวเลขนี้ไปเทียบกับที่ query ออกมาจาก SQLite")

rp.save(OUTPUT_DIR / "02b_fact_report.txt")
