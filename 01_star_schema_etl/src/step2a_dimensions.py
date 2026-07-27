"""Step 2A (Transform) - สร้างตาราง dimension

Dimension เก็บบริบทของธุรกรรม: ใคร (dim_customer) ซื้ออะไร (dim_product)
เมื่อไหร่ (dim_time)

งานในขั้นนี้: ทำความสะอาดข้อความ -> ลบแถวซ้ำ -> เติมค่าที่หาย ->
แยกบริบทออกเป็น dimension พร้อม surrogate key

surrogate key คือ PK เทียมที่เราสร้างเอง (1, 2, 3...) แทนการใช้ค่าจริงเป็นกุญแจ
เพราะค่าจริงเปลี่ยนได้ (ลูกค้าเปลี่ยนอีเมล) แต่ตัวตนไม่ได้เปลี่ยน และ integer
join เร็วกว่าข้อความมากเมื่อ fact มีเป็นล้านแถว

ผลลัพธ์: output/dim_*.csv และ output/02a_clean_orders.csv
"""

import pandas as pd

from common import (
    OUTPUT_DIR,
    RAW_FILE,
    Reporter,
    build_lookup,
    clean_text,
    norm_key,
    parse_dates_strict,
    pick_display_spelling,
    save_csv,
    setup_console,
)

setup_console()
rp = Reporter()

TEXT_COLUMNS = ["Order_ID", "Customer_Name", "Email", "Product", "Category", "Order_Date"]


rp.section("1) อ่านข้อมูลดิบ")

df = pd.read_csv(RAW_FILE, dtype=str)
rp.say(f"อ่านมา {len(df)} แถว")


rp.section("2) ทำความสะอาดข้อความ")

before_dirty = sum((df[c] != df[c].str.strip()).sum() for c in df.columns)

for col in TEXT_COLUMNS:
    df[col] = clean_text(df[col])
for col in ["Quantity", "Unit_Price", "Amount"]:
    df[col] = df[col].str.strip()

rp.say(f"ตัดช่องว่างหัวท้ายไป {before_dirty} ช่อง และบีบช่องว่างกลางข้อความ")


rp.section("3) สร้าง key สำหรับจับกลุ่ม")

# key พวกนี้เป็นตัวพิมพ์เล็กล้วน ใช้จับกลุ่มอย่างเดียว ไม่ได้เอาไปแสดงผล
df["customer_key"] = norm_key(df["Email"])
df["product_key"] = norm_key(df["Product"])
df["category_key"] = norm_key(df["Category"])
df["name_key"] = norm_key(df["Customer_Name"])

rp.say("จำนวนค่าไม่ซ้ำ ก่อน -> หลัง normalize:")
rp.say(f"  Customer_Name : {df['Customer_Name'].nunique():>3} -> {df['name_key'].nunique():>3}")
rp.say(f"  Email         : {df['Email'].nunique():>3} -> {df['customer_key'].nunique():>3}")
rp.say(f"  Product       : {df['Product'].nunique():>3} -> {df['product_key'].nunique():>3}")
rp.say(f"  Category      : {df['Category'].nunique():>3} -> {df['category_key'].nunique():>3}")
rp.say()
rp.say("ส่วนต่างคือลูกค้าและสินค้าปลอมที่เกิดจากสะกดไม่ตรงกัน")
rp.say("ไม่ทำขั้นนี้ ลูกค้าคนเดียวจะถูกนับเป็น 2-3 คนในคลัง")


rp.section("4) ลบแถวซ้ำ")

# ต้อง normalize มาก่อนถึงจะเห็นแถวที่ต่างกันแค่ช่องว่างหรือตัวพิมพ์
dedup_columns = [
    "Order_ID", "customer_key", "name_key", "product_key",
    "category_key", "Order_Date", "Quantity", "Unit_Price", "Amount",
]

before = len(df)
duplicated_mask = df.duplicated(subset=dedup_columns, keep="first")
removed_ids = sorted(df.loc[duplicated_mask, "Order_ID"].unique())
df = df[~duplicated_mask].copy()

rp.say(f"{before} -> {len(df)} แถว (ลบ {before - len(df)})")
rp.say(f"Order_ID ที่ลบ: {removed_ids}")
rp.say()

# ถ้ายังเหลือ Order_ID ซ้ำ แปลว่ามีแถวใช้เลขเดียวกันแต่ข้อมูลคนละอย่าง
# เป็นความขัดแย้งที่คนต้องตัดสิน ไม่ใช่โปรแกรมเลือกเองมั่ว ๆ
conflict = df["Order_ID"].duplicated().sum()
if conflict > 0:
    conflicting = df[df["Order_ID"].duplicated(keep=False)].sort_values("Order_ID")
    raise ValueError(
        f"Order_ID ซ้ำแต่ข้อมูลไม่ตรงกัน {conflict} แถว ต้องให้คนตัดสิน\n"
        f"{conflicting.to_string()}"
    )

rp.say(f"Order_ID ไม่ซ้ำแล้ว ({df['Order_ID'].nunique()} ค่า) ใช้เป็น PK ของ fact ได้")


rp.section("5) เติมค่าที่หายไป")

rp.say("เติมได้เฉพาะเมื่อมีหลักฐานในไฟล์เดียวกัน และต้องพิสูจน์ก่อนว่าเป็น 1:1 จริง")
rp.say("ถ้าไม่ใช่ 1:1 ให้โปรแกรมหยุด ไม่เดาต่อ")
rp.say()
rp.say(f"ก่อนเติม: Customer_Name {df['Customer_Name'].isna().sum()} | "
       f"Email {df['Email'].isna().sum()} | Category {df['Category'].isna().sum()}")
rp.say()

# เติม email ก่อนเติมชื่อ เพราะแถวที่ไม่มี email ยังมีชื่ออยู่
name_to_email = build_lookup(df, "name_key", "customer_key", "name -> email")
rp.say(f"lookup name -> email : {len(name_to_email)} รายการ เป็น 1:1 ทุกตัว")

missing_email = df["customer_key"].isna()
if missing_email.any():
    for idx in df.index[missing_email]:
        rp.say(f"    {df.at[idx, 'Order_ID']} ชื่อ '{df.at[idx, 'Customer_Name']}' "
               f"-> เติม '{name_to_email.get(df.at[idx, 'name_key'])}'")
    df.loc[missing_email, "customer_key"] = df.loc[missing_email, "name_key"].map(name_to_email)

email_to_name = build_lookup(df, "customer_key", "name_key", "email -> name")
rp.say(f"lookup email -> name : {len(email_to_name)} รายการ เป็น 1:1 ทุกตัว")

missing_name = df["name_key"].isna()
if missing_name.any():
    for idx in df.index[missing_name]:
        rp.say(f"    {df.at[idx, 'Order_ID']} email '{df.at[idx, 'customer_key']}' "
               f"-> จับเข้ากลุ่ม '{email_to_name.get(df.at[idx, 'customer_key'])}'")
    df.loc[missing_name, "name_key"] = df.loc[missing_name, "customer_key"].map(email_to_name)

product_to_category = build_lookup(df, "product_key", "category_key", "product -> category")
rp.say(f"lookup product -> category : {len(product_to_category)} รายการ เป็น 1:1 ทุกตัว")

missing_category = df["category_key"].isna()
if missing_category.any():
    for idx in df.index[missing_category]:
        rp.say(f"    {df.at[idx, 'Order_ID']} สินค้า '{df.at[idx, 'Product']}' "
               f"-> เติม '{product_to_category.get(df.at[idx, 'product_key'])}'")
    df.loc[missing_category, "category_key"] = (
        df.loc[missing_category, "product_key"].map(product_to_category)
    )

# ไฟล์รอบนี้เติมได้ครบ แต่ข้อมูลรอบหน้าอาจมีแถวที่ทั้งชื่อและ email หายพร้อมกัน
# ต้องมีทางรองรับไว้ ไม่งั้น join จะพังตอน 2B
UNKNOWN_CUSTOMER = "unknown@unknown"
UNKNOWN_TEXT = "unknown"

still_missing = df["customer_key"].isna().sum() + df["category_key"].isna().sum()
if still_missing > 0:
    rp.say(f"เหลือ {still_missing} ช่องที่เติมจากหลักฐานไม่ได้ ใส่ Unknown แทน")
    df["customer_key"] = df["customer_key"].fillna(UNKNOWN_CUSTOMER)
    df["name_key"] = df["name_key"].fillna(UNKNOWN_TEXT)
    df["category_key"] = df["category_key"].fillna(UNKNOWN_TEXT)
else:
    rp.say("เติมจากหลักฐานได้ครบทุกช่อง ไม่ต้องใช้ Unknown")

rp.say()
rp.say(f"หลังเติม: customer_key {df['customer_key'].isna().sum()} | "
       f"name_key {df['name_key'].isna().sum()} | "
       f"category_key {df['category_key'].isna().sum()}")


rp.section("6) แปลงวันที่")

df["order_date"] = parse_dates_strict(df["Order_Date"])

rp.say(f"แปลงครบทั้ง {len(df)} แถว ไม่เหลือค่าที่แปลงไม่ได้")
rp.say(f"ช่วงวันที่ : {df['order_date'].min().date()} ถึง {df['order_date'].max().date()}")
rp.say(f"วันที่ไม่ซ้ำ : {df['order_date'].nunique()} วัน")
rp.say()
rp.say("ตัวอย่าง (ฟอร์แมตต่างกันแต่ได้ผลถูก):")
for _, row in df.drop_duplicates(subset=["Order_Date"]).head(6).iterrows():
    rp.say(f"  {row['Order_Date']:<15} -> {row['order_date'].date()}")


rp.section("7) dim_customer")

# จับกลุ่มด้วย email แล้วเลือกการสะกดชื่อที่เหมาะสุด
customer_names = (
    df.groupby("customer_key")["Customer_Name"]
    .apply(pick_display_spelling)
    .rename("customer_name")
)

dim_customer = customer_names.reset_index().rename(columns={"customer_key": "email"})
dim_customer = dim_customer.sort_values("email").reset_index(drop=True)

# เรียงตาม email ก่อนแจก id เพื่อให้รันกี่รอบก็ได้เลขเดิม
dim_customer.insert(0, "customer_id", range(1, len(dim_customer) + 1))
dim_customer = dim_customer[["customer_id", "customer_name", "email"]]

rp.say(f"{len(dim_customer)} แถว (จากชื่อที่สะกดต่างกัน {df['Customer_Name'].nunique()} แบบ)")
rp.say()
rp.say(dim_customer.to_string(index=False))


rp.section("8) dim_product")

product_names = df.groupby("product_key")["Product"].apply(pick_display_spelling).rename("product_name")
product_categories = (
    df.dropna(subset=["Category"])
    .groupby("product_key")["Category"]
    .apply(pick_display_spelling)
    .rename("category")
)

dim_product = pd.concat([product_names, product_categories], axis=1).reset_index()
dim_product = dim_product.sort_values("product_key").reset_index(drop=True)
dim_product.insert(0, "product_id", range(1, len(dim_product) + 1))
dim_product = dim_product[["product_id", "product_name", "category"]]

rp.say(f"{len(dim_product)} แถว")
rp.say()
rp.say(dim_product.to_string(index=False))
rp.say()
rp.say("ไม่มีคอลัมน์ unit_price เพราะสินค้าชิ้นเดียวกันขายได้หลายราคา")
rp.say("ชื่อสินค้าออกมาถูกต้อง ไม่ใช่ 'Usb-C Hub' หรือ 'Portable Ssd 1Tb'")
rp.say("เพราะเลือกจากการสะกดที่มีอยู่จริง ไม่ได้ใช้ .str.title()")


rp.section("9) dim_time")

# สร้างเป็นปฏิทินต่อเนื่องครอบทุกเดือนที่มีข้อมูล ไม่ใช่เอาเฉพาะวันที่ปรากฏ
start = df["order_date"].min().to_period("M").to_timestamp()
end = df["order_date"].max().to_period("M").to_timestamp("M")
calendar = pd.date_range(start, end, freq="D")

dim_time = pd.DataFrame({"full_date": calendar})
# date_key แบบ YYYYMMDD อ่านแล้วเดาวันได้ทันที และรันซ้ำค่าก็คงเดิม
dim_time.insert(0, "date_key", dim_time["full_date"].dt.strftime("%Y%m%d").astype(int))
dim_time["year"] = dim_time["full_date"].dt.year
dim_time["quarter"] = dim_time["full_date"].dt.quarter
dim_time["month"] = dim_time["full_date"].dt.month
dim_time["month_name"] = dim_time["full_date"].dt.month_name()
dim_time["day"] = dim_time["full_date"].dt.day
dim_time["weekday_name"] = dim_time["full_date"].dt.day_name()
dim_time["is_weekend"] = (dim_time["full_date"].dt.dayofweek >= 5).astype(int)
dim_time["full_date"] = dim_time["full_date"].dt.strftime("%Y-%m-%d")

days_with_sales = df["order_date"].nunique()
rp.say(f"ปฏิทิน {start.date()} ถึง {end.date()} = {len(dim_time)} วัน")
rp.say(f"วันที่ขายได้จริง {days_with_sales} วัน ขายไม่ออก {len(dim_time) - days_with_sales} วัน")
rp.say()
rp.say("ที่ทำเป็นปฏิทินเต็มแทนการเอาเฉพาะวันที่มีข้อมูล เพราะ")
rp.say(f"  วันที่ขายไม่ออก {len(dim_time) - days_with_sales} วันจะหายไปจากคลัง ถามหาไม่ได้")
rp.say("  กราฟรายวันจะกระโดดข้ามวัน ดูเหมือนขายได้ทุกวันซึ่งไม่จริง")
rp.say("  dim_time เป็น dimension เดียวที่ไม่ควรขึ้นกับ fact สร้างครั้งเดียวจบ")
rp.say()
rp.say(dim_time.head(8).to_string(index=False))


rp.section("10) ตารางหลักส่งต่อให้ 2B")

clean_orders = pd.DataFrame({
    "order_id": df["Order_ID"],
    "customer_key": df["customer_key"],
    "product_key": df["product_key"],
    "date_key": df["order_date"].dt.strftime("%Y%m%d").astype(int),
    "quantity": df["Quantity"],
    "unit_price_raw": df["Unit_Price"],
    "amount_raw": df["Amount"],
}).reset_index(drop=True)

rp.say(f"{len(clean_orders)} แถว พร้อม key สำหรับ join ครบ 3 ตัว")
rp.say()
rp.say(clean_orders.head(8).to_string(index=False))
rp.say()
rp.say("unit_price กับ amount ยังเป็นข้อความ ตั้งใจปล่อยไว้ให้ 2B จัดการ")
rp.say("เพราะการแปลงตัวเลขและเติม amount เป็นเรื่องของ fact")


rp.section("11) บันทึกผลลัพธ์")

outputs = {
    "dim_customer.csv": dim_customer,
    "dim_product.csv": dim_product,
    "dim_time.csv": dim_time,
    "02a_clean_orders.csv": clean_orders,
}
for filename, table in outputs.items():
    save_csv(table, OUTPUT_DIR / filename)
    rp.say(f"  {filename:<24} {len(table):>4} แถว")

rp.save(OUTPUT_DIR / "02a_dimension_report.txt")
