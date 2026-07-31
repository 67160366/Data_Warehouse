"""ETL pipeline: retail_logs.csv -> retail_warehouse.db (star schema)

แปลงล็อกการขายหน้าร้านที่ยังไม่ได้ทำความสะอาด ให้เป็น data warehouse แบบ star schema
ใน SQLite ไฟล์เดียว ทำครบทั้ง Extract, Transform, Load และตรวจสอบผลในตอนท้าย

    python etl_pipeline.py

รันซ้ำกี่รอบก็ได้ ข้อมูลไม่บาน (full refresh ครอบใน transaction เดียว)

ผลลัพธ์
    retail_warehouse.db     คลังข้อมูล
    output/*.csv            ตารางแต่ละตัวในรูป CSV เอาไว้เปิดดูด้วย Excel
    output/etl_report.txt   รายงานทุกขั้นตอน
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_FILE = BASE_DIR / "retail_logs.csv"
OUTPUT_DIR = BASE_DIR / "output"
DB_FILE = BASE_DIR / "retail_warehouse.db"

TEXT_COLUMNS = ["Store_Code", "Branch", "Province", "Region", "Product_Name", "Category"]
DIMENSION_TABLES = ["dim_location", "dim_product", "dim_date"]
FACT_TABLE = "fact_sales"


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

class Reporter:
    """print ออกจอ พร้อมเก็บข้อความไว้เขียนลงไฟล์รายงาน"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(str(text))

    def section(self, title: str) -> None:
        self.say()
        self.say("=" * 74)
        self.say(f"  {title}")
        self.say("=" * 74)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines), encoding="utf-8")
        print()
        print(f"บันทึกรายงาน: {path}")


def clean_text(series: pd.Series) -> pd.Series:
    """ตัดช่องว่างหัวท้าย และบีบช่องว่างกลางข้อความให้เหลือตัวเดียว

    ' Phuket Town ' -> 'Phuket Town'
    """
    return series.str.strip().str.replace(r"\s+", " ", regex=True)


def pick_display_spelling(values: pd.Series) -> str:
    """เลือกการสะกดที่จะใช้แสดงใน dimension

    อย่าใช้ .str.title() เพราะจะได้ 'Bkk-01' กับชื่อที่ผิดรูปแบบอื่น ๆ

    คัดสองชั้น:
      1. ตัดการสะกดที่เป็นพิมพ์ใหญ่ล้วน/เล็กล้วนออกก่อน ('TRAVEL MUG', 'travel mug')
         รูปแบบพวกนี้มักเป็นร่องรอยการกรอก ไม่ใช่ชื่อจริง
      2. ที่เหลือเอาอันที่พบบ่อยสุด เท่ากันก็เรียงตัวอักษร (ให้ผลคงที่ทุกรอบ)
    """
    counts = values.dropna().value_counts()
    natural = [v for v in counts.index if not v.isupper() and not v.islower()]
    pool = natural if natural else list(counts.index)
    return sorted(pool, key=lambda v: (-counts[v], v))[0]


def standardize(series: pd.Series) -> pd.Series:
    """รวมการสะกดที่ต่างกันแค่ตัวพิมพ์ให้เหลือแบบเดียว

    จับกลุ่มด้วย lowercase แล้วแทนที่ทั้งกลุ่มด้วยการสะกดที่เลือกไว้
    """
    key = series.str.lower()
    mapping = series.groupby(key).apply(pick_display_spelling)
    return key.map(mapping).where(series.notna())


def build_lookup(df: pd.DataFrame, key_col: str, value_col: str) -> dict:
    """สร้าง mapping key -> value พร้อมตรวจว่าเป็น 1:1 ก่อนคืนค่า

    การเติมค่าที่หายจากแถวอื่นจะปลอดภัยก็ต่อเมื่อ key หนึ่งผูกกับ value เดียว
    ถ้า Phuket ผูกกับสองภูมิภาค ต้องให้โปรแกรมหยุด ไม่ใช่เดาแล้วไปต่อ
    """
    pairs = df[[key_col, value_col]].dropna()
    conflicts = pairs.groupby(key_col)[value_col].nunique()
    conflicts = conflicts[conflicts > 1]

    if len(conflicts) > 0:
        raise ValueError(
            f"{key_col} -> {value_col} ไม่ใช่ 1:1 เติมค่าอัตโนมัติไม่ได้\n"
            f"  key ที่มีปัญหา: {list(conflicts.index)}"
        )

    return pairs.drop_duplicates().set_index(key_col)[value_col].to_dict()


# ไฟล์ต้นทางมีวันที่ 3 ฟอร์แมตปนกัน ประกาศไว้ตรงนี้ที่เดียว
DATE_FORMATS = [
    (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),             # 2026-03-15
    (r"^\d{2}/\d{2}/\d{4}$", "%d/%m/%Y"),             # 17/05/2026 วันขึ้นก่อน
    (r"^\d{1,2}-[A-Za-z]{3}-\d{4}$", "%d-%b-%Y"),     # 14-May-2026
]


def parse_dates_strict(series: pd.Series) -> pd.Series:
    """แปลงวันที่ทีละฟอร์แมตโดยระบุ format แล้วบังคับว่าห้ามเหลือ NaT

    ห้ามเรียก pd.to_datetime() เฉย ๆ เพราะค่าเริ่มต้นคือ dayfirst=False
    '06/05/2026' จะถูกอ่านเป็น 5 มิถุนายนแทน 6 พฤษภาคม และไม่มี error ฟ้อง
    ไฟล์นี้ยืนยันได้ว่าเป็นวันขึ้นก่อน เพราะมี 74 แถวที่เลขตัวหน้ามากกว่า 12

    เจอฟอร์แมตใหม่ที่ไม่รู้จักให้ error ไปเลย ดีกว่าปล่อยข้อมูลผิดเข้าคลัง
    """
    raw = series.str.strip()
    result = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")

    for pattern, fmt in DATE_FORMATS:
        match = raw.str.match(pattern, na=False)
        result[match] = pd.to_datetime(raw[match], format=fmt)

    if result.isna().any():
        bad = raw[result.isna()].unique()[:10]
        raise ValueError(f"แปลงวันที่ไม่ได้ ฟอร์แมตไม่รู้จัก: {list(bad)}")

    return result


def save_csv(df: pd.DataFrame, name: str) -> None:
    """เขียน CSV แบบ utf-8-sig ให้ Excel เปิดแล้วไม่เพี้ยน"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / name, index=False, encoding="utf-8-sig")


def show(df: pd.DataFrame, rp: Reporter, limit: int = 10) -> None:
    for line in df.head(limit).to_string(index=False).splitlines():
        rp.say(f"  {line}")


# ---------------------------------------------------------------------------
# 1) EXTRACT
# ---------------------------------------------------------------------------

def extract(rp: Reporter) -> pd.DataFrame:
    """อ่านไฟล์ดิบเป็น string ทั้งหมด แล้วสำรวจว่ามีอะไรพังบ้าง

    อ่านเป็น string ก่อนเพื่อไม่ให้ pandas เดาชนิดข้อมูลเอง เดี๋ยวขั้น transform
    จะแปลงเองทีละคอลัมน์โดยมีเงื่อนไขที่เราคุมได้
    """
    rp.section("1) EXTRACT - อ่านข้อมูลดิบ")

    # ไฟล์มี BOM อยู่หน้า Sale_ID ถ้าใช้ utf-8 เฉย ๆ ชื่อคอลัมน์แรกจะกลายเป็น '﻿Sale_ID'
    df = pd.read_csv(RAW_FILE, dtype=str, encoding="utf-8-sig")

    rp.say(f"ไฟล์  : {RAW_FILE.name}")
    rp.say(f"ขนาด  : {len(df)} แถว {len(df.columns)} คอลัมน์")
    rp.say()
    rp.say("ตัวอย่าง 5 แถวแรก:")
    show(df, rp, 5)

    rp.say()
    rp.say("ค่าที่หาย:")
    missing = df.isna().sum()
    for column, count in missing[missing > 0].items():
        rp.say(f"  {column:<18} {count} แถว")

    rp.say()
    rp.say(f"แถวซ้ำสนิท        : {df.duplicated().sum()}")
    rp.say(f"Sale_ID ซ้ำ       : {df['Sale_ID'].duplicated().sum()}")

    rp.say()
    rp.say("ค่าที่ต่างกันในแต่ละคอลัมน์ (ก่อนทำความสะอาด -> หลังตัดช่องว่างและตัวพิมพ์):")
    for column in TEXT_COLUMNS:
        before = df[column].nunique()
        after = clean_text(df[column]).str.lower().nunique()
        flag = "  <-- ต้องรวมให้เหลือชุดเดียว" if before != after else ""
        rp.say(f"  {column:<14} {before:>3} -> {after:>3}{flag}")

    rp.say()
    rp.say("ฟอร์แมตของ Sale_Date:")
    date_raw = df["Sale_Date"].str.strip()
    for pattern, fmt in DATE_FORMATS:
        rp.say(f"  {fmt:<10} {date_raw.str.match(pattern, na=False).sum():>4} แถว")
    slash = date_raw[date_raw.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)]
    day_first_proof = (slash.str[:2].astype(int) > 12).sum()
    rp.say(f"  แถวแบบ dd/mm/yyyy ที่เลขตัวหน้า > 12 : {day_first_proof}")
    rp.say("  -> ยืนยันว่าฟอร์แมตนี้เป็นวันขึ้นก่อน ไม่ใช่เดือนขึ้นก่อน")

    return df


# ---------------------------------------------------------------------------
# 2) TRANSFORM - ทำความสะอาด
# ---------------------------------------------------------------------------

def clean(df: pd.DataFrame, rp: Reporter) -> pd.DataFrame:
    """ทำความสะอาดให้ได้ตารางเดียวที่พร้อมแตกเป็น dimension กับ fact"""
    rp.section("2) TRANSFORM - ทำความสะอาด")

    before = len(df)

    # 2.1 ช่องว่าง -----------------------------------------------------------
    dirty_cells = sum(
        int(df[c].dropna().map(lambda s: s != s.strip()).sum()) for c in TEXT_COLUMNS
    )
    for column in TEXT_COLUMNS:
        df[column] = clean_text(df[column])
    df["Sale_ID"] = df["Sale_ID"].str.strip()
    rp.say(f"ตัดช่องว่างหัวท้าย          : {dirty_cells} ช่อง")

    # 2.2 แถวซ้ำ -------------------------------------------------------------
    # ต้องลบหลัง strip เพราะแถวซ้ำบางคู่ต่างกันแค่ช่องว่าง จะไม่ถูกจับถ้าลบก่อน
    df = df.drop_duplicates().reset_index(drop=True)
    rp.say(f"ลบแถวซ้ำสนิท              : {before - len(df)} แถว (เหลือ {len(df)})")

    if df["Sale_ID"].duplicated().any():
        repeated = df.loc[df["Sale_ID"].duplicated(), "Sale_ID"].tolist()
        raise ValueError(f"Sale_ID ยังซ้ำหลัง dedupe ใช้เป็น PK ไม่ได้: {repeated}")
    rp.say("Sale_ID ไม่ซ้ำแล้ว          : ใช้เป็น primary key ของ fact ได้")

    # 2.3 ตัวพิมพ์ -----------------------------------------------------------
    rp.say()
    rp.say("รวมการสะกดที่ต่างกันแค่ตัวพิมพ์:")
    for column in TEXT_COLUMNS:
        before_n = df[column].nunique()
        df[column] = standardize(df[column])
        rp.say(f"  {column:<14} {before_n:>3} -> {df[column].nunique():>3} แบบ")

    # 2.4 เติมค่าที่หาย -------------------------------------------------------
    rp.say()
    missing_region = int(df["Region"].isna().sum())
    if missing_region:
        # ตรวจก่อนว่า province -> region เป็น 1:1 จริง ไม่งั้น build_lookup จะ raise
        region_of = build_lookup(df, "Province", "Region")
        df["Region"] = df["Region"].fillna(df["Province"].map(region_of))
        rp.say(f"เติม Region ที่หาย {missing_region} แถว จาก Province (ตรวจแล้วเป็น 1:1)")
        rp.say(f"  mapping: {region_of}")

    missing_discount = int(df["Discount_Percent"].isna().sum())
    if missing_discount:
        # ส่วนลดไม่ผูกกับสินค้า สาขา หรือระดับราคา จึงกู้จากแถวอื่นไม่ได้
        # ตีความว่า 'ไม่ได้บันทึกส่วนลด = ไม่ได้ลด' ซึ่งเป็นค่าที่พบบ่อยที่สุดและ
        # ไม่ทำให้ยอดขายสูงเกินจริง
        blank = df.loc[df["Discount_Percent"].isna(), "Sale_ID"].tolist()
        df["Discount_Percent"] = df["Discount_Percent"].fillna("0")
        rp.say(f"เติม Discount_Percent ที่หาย {missing_discount} แถว ด้วย 0: {blank}")

    # 2.5 แปลงชนิดข้อมูล ------------------------------------------------------
    df["sale_date"] = parse_dates_strict(df["Sale_Date"])
    df["quantity"] = pd.to_numeric(df["Quantity"])
    df["unit_price"] = pd.to_numeric(df["Unit_Price"])
    df["discount_percent"] = pd.to_numeric(df["Discount_Percent"])

    rp.say()
    rp.say(f"แปลงวันที่ 3 ฟอร์แมตสำเร็จ  : {df['sale_date'].min():%Y-%m-%d} ถึง "
           f"{df['sale_date'].max():%Y-%m-%d}")
    rp.say(f"quantity          : {df['quantity'].min()} - {df['quantity'].max()}")
    rp.say(f"unit_price        : {df['unit_price'].min():.2f} - {df['unit_price'].max():.2f}")
    rp.say(f"discount_percent  : {sorted(int(v) for v in df['discount_percent'].unique())}")

    if df.isna().any().any():
        raise ValueError(f"ยังมีค่าว่างเหลือ:\n{df.isna().sum()[lambda s: s > 0]}")
    rp.say()
    rp.say("ไม่มีค่าว่างเหลือแล้วทุกคอลัมน์")

    # 2.6 ตรวจ functional dependency ก่อนแตกเป็น dimension --------------------
    # ถ้า store เดียวกันชี้ไปคนละจังหวัด แปลว่า dimension ที่กำลังจะสร้างมั่ว
    rp.say()
    rp.say("ตรวจความสอดคล้องก่อนแตกเป็น dimension:")
    for key, value in [
        ("Store_Code", "Branch"),
        ("Store_Code", "Province"),
        ("Store_Code", "Region"),
        ("Province", "Region"),
        ("Product_Name", "Category"),
    ]:
        build_lookup(df, key, value)
        rp.say(f"  {key + ' -> ' + value:<30} 1:1 ผ่าน")

    return df


# ---------------------------------------------------------------------------
# 3) TRANSFORM - สร้าง dimension
# ---------------------------------------------------------------------------

def build_dimensions(df: pd.DataFrame, rp: Reporter) -> dict[str, pd.DataFrame]:
    rp.section("3) TRANSFORM - สร้าง dimension")

    # dim_location ----------------------------------------------------------
    # grain = ร้านหนึ่งสาขา ใช้ Store_Code เป็น natural key
    # branch/province/region เป็น attribute ที่ roll-up ได้เป็นลำดับชั้น
    dim_location = (
        df[["Store_Code", "Branch", "Province", "Region"]]
        .drop_duplicates()
        .sort_values("Store_Code")
        .reset_index(drop=True)
        .rename(columns={
            "Store_Code": "store_code",
            "Branch": "branch",
            "Province": "province",
            "Region": "region",
        })
    )
    dim_location.insert(0, "location_id", range(1, len(dim_location) + 1))

    # dim_product -----------------------------------------------------------
    # ไม่มี unit_price เพราะสินค้าตัวเดียวกันขายหลายราคา (ราคาฐาน ±5%)
    # ราคาที่ขายจริง ณ ตอนนั้นเป็น measure ของธุรกรรม ไม่ใช่คุณสมบัติถาวรของสินค้า
    dim_product = (
        df[["Product_Name", "Category"]]
        .drop_duplicates()
        .sort_values("Product_Name")
        .reset_index(drop=True)
        .rename(columns={"Product_Name": "product_name", "Category": "category"})
    )
    dim_product.insert(0, "product_id", range(1, len(dim_product) + 1))

    # dim_date --------------------------------------------------------------
    # สร้างเป็นปฏิทินต่อเนื่องคลุมทั้งช่วง ไม่ใช่เอาเฉพาะวันที่มีการขาย
    # ถ้าเอาเฉพาะวันที่ขายได้ วันที่ขายไม่ออกจะหายไปจากคลัง ถามหา 'วันไหนยอด 0'
    # ไม่ได้ และกราฟรายวันจะกระโดดข้ามวันเงียบ ๆ
    calendar = pd.date_range(df["sale_date"].min(), df["sale_date"].max(), freq="D")
    dim_date = pd.DataFrame({"full_date": calendar})
    # date_key เป็น YYYYMMDD อ่าน fact แล้วเดาวันได้โดยไม่ต้อง join
    # และรัน pipeline ซ้ำค่าก็คงเดิม ต่างจากเลขรันนิ่งที่จะเลื่อนเมื่อมีวันใหม่เข้ามา
    dim_date.insert(0, "date_key", calendar.strftime("%Y%m%d").astype(int))
    dim_date["year"] = calendar.year
    dim_date["quarter"] = calendar.quarter
    dim_date["month"] = calendar.month
    dim_date["month_name"] = calendar.month_name()
    dim_date["day"] = calendar.day
    dim_date["weekday_name"] = calendar.day_name()
    dim_date["is_weekend"] = (calendar.dayofweek >= 5).astype(int)
    # SQLite ไม่มีชนิด DATE ต้องเก็บเป็น TEXT รูปแบบ ISO8601 เพราะเรียงตามตัวอักษร
    # แล้วได้ลำดับเวลาถูกต้องพอดี ใช้ WHERE เทียบช่วงเวลาได้
    dim_date["full_date"] = calendar.strftime("%Y-%m-%d")

    days_with_sales = df["sale_date"].nunique()
    rp.say(f"dim_location  {len(dim_location):>4} แถว   (จาก Store_Code ที่ไม่ซ้ำ)")
    rp.say(f"dim_product   {len(dim_product):>4} แถว   (จาก Product_Name ที่ไม่ซ้ำ)")
    rp.say(f"dim_date      {len(dim_date):>4} แถว   (ปฏิทินต่อเนื่อง มีการขายจริง "
           f"{days_with_sales} วัน ว่าง {len(dim_date) - days_with_sales} วัน)")

    rp.say()
    rp.say("dim_location:")
    show(dim_location, rp)
    rp.say()
    rp.say("dim_product:")
    show(dim_product, rp)
    rp.say()
    rp.say("dim_date (5 แถวแรก):")
    show(dim_date, rp, 5)

    return {
        "dim_location": dim_location,
        "dim_product": dim_product,
        "dim_date": dim_date,
    }


# ---------------------------------------------------------------------------
# 4) TRANSFORM - สร้าง fact
# ---------------------------------------------------------------------------

def build_fact(df: pd.DataFrame, dims: dict[str, pd.DataFrame], rp: Reporter) -> pd.DataFrame:
    """แทนที่ข้อความยาว ๆ ด้วย surrogate key แล้วคำนวณ measure"""
    rp.section("4) TRANSFORM - สร้าง fact_sales")

    fact = df.copy()
    fact["date_key"] = fact["sale_date"].dt.strftime("%Y%m%d").astype(int)

    before = len(fact)
    fact = fact.merge(
        dims["dim_location"][["location_id", "store_code"]],
        left_on="Store_Code", right_on="store_code", how="left", validate="many_to_one",
    )
    fact = fact.merge(
        dims["dim_product"][["product_id", "product_name"]],
        left_on="Product_Name", right_on="product_name", how="left", validate="many_to_one",
    )
    fact = fact.merge(
        dims["dim_date"][["date_key"]],
        on="date_key", how="left", validate="many_to_one",
    )

    # merge ที่ผิดพลาดทำให้แถวหายหรือบานได้เงียบ ๆ ต้องเช็คทั้งจำนวนแถวและ key ที่หลุด
    if len(fact) != before:
        raise ValueError(f"จำนวนแถวเปลี่ยนหลัง merge: {before} -> {len(fact)}")
    for key in ["location_id", "product_id", "date_key"]:
        if fact[key].isna().any():
            raise ValueError(f"{key} หาไม่เจอใน dimension {int(fact[key].isna().sum())} แถว")
    rp.say(f"merge หา surrogate key ครบทุกแถว ({len(fact)} แถว ไม่มี key หลุด)")

    # measure: ไฟล์ดิบไม่มีคอลัมน์ยอดเงินเลย ต้องคำนวณเองทั้งหมด
    # เก็บครบสามตัวเพื่อตอบได้ทั้งยอดก่อนลด มูลค่าส่วนลด และยอดสุทธิ
    # โดยไม่ต้องคำนวณซ้ำใน query ทุกครั้ง
    fact["gross_amount"] = (fact["quantity"] * fact["unit_price"]).round(2)
    fact["discount_amount"] = (fact["gross_amount"] * fact["discount_percent"] / 100).round(2)
    fact["net_amount"] = (fact["gross_amount"] - fact["discount_amount"]).round(2)

    fact = fact.rename(columns={"Sale_ID": "sale_id"})[[
        "sale_id", "location_id", "product_id", "date_key",
        "quantity", "unit_price", "discount_percent",
        "gross_amount", "discount_amount", "net_amount",
    ]].sort_values("sale_id").reset_index(drop=True)

    rp.say()
    rp.say(f"fact_sales    {len(fact)} แถว   grain = 1 แถวต่อ 1 รายการขาย (Sale_ID)")
    rp.say()
    rp.say(f"  ยอดก่อนลด (gross)  {fact['gross_amount'].sum():>12,.2f} บาท")
    rp.say(f"  ส่วนลดรวม          {fact['discount_amount'].sum():>12,.2f} บาท")
    rp.say(f"  ยอดสุทธิ (net)     {fact['net_amount'].sum():>12,.2f} บาท")
    rp.say()
    rp.say("fact_sales (10 แถวแรก):")
    show(fact, rp)

    return fact


# ---------------------------------------------------------------------------
# 5) LOAD
# ---------------------------------------------------------------------------

# schema ประกาศเองทุกตัว ไม่ปล่อยให้ pandas เดาจาก dtype
# constraint ตรงนี้เป็นกฎที่ฐานข้อมูลบังคับเอง ต่อให้โค้ด Python มีบั๊กวันหนึ่ง
# ฐานข้อมูลก็ยังปฏิเสธข้อมูลที่ผิดกฎ
SCHEMAS = {
    "dim_location": """
        CREATE TABLE IF NOT EXISTS dim_location (
            location_id INTEGER PRIMARY KEY,
            store_code  TEXT    NOT NULL UNIQUE,
            branch      TEXT    NOT NULL,
            province    TEXT    NOT NULL,
            region      TEXT    NOT NULL
        )
    """,
    "dim_product": """
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id   INTEGER PRIMARY KEY,
            product_name TEXT    NOT NULL UNIQUE,
            category     TEXT    NOT NULL
        )
    """,
    "dim_date": """
        CREATE TABLE IF NOT EXISTS dim_date (
            date_key     INTEGER PRIMARY KEY,
            full_date    TEXT    NOT NULL UNIQUE,
            year         INTEGER NOT NULL,
            quarter      INTEGER NOT NULL,
            month        INTEGER NOT NULL,
            month_name   TEXT    NOT NULL,
            day          INTEGER NOT NULL,
            weekday_name TEXT    NOT NULL,
            is_weekend   INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
        )
    """,
    "fact_sales": """
        CREATE TABLE IF NOT EXISTS fact_sales (
            sale_id          TEXT    PRIMARY KEY,
            location_id      INTEGER NOT NULL,
            product_id       INTEGER NOT NULL,
            date_key         INTEGER NOT NULL,
            quantity         INTEGER NOT NULL CHECK (quantity > 0),
            unit_price       REAL    NOT NULL CHECK (unit_price > 0),
            discount_percent REAL    NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
            gross_amount     REAL    NOT NULL CHECK (gross_amount >= 0),
            discount_amount  REAL    NOT NULL CHECK (discount_amount >= 0),
            net_amount       REAL    NOT NULL CHECK (net_amount >= 0),
            FOREIGN KEY (location_id) REFERENCES dim_location (location_id),
            FOREIGN KEY (product_id)  REFERENCES dim_product  (product_id),
            FOREIGN KEY (date_key)    REFERENCES dim_date     (date_key)
        )
    """,
}


def load(tables: dict[str, pd.DataFrame], rp: Reporter) -> sqlite3.Connection:
    rp.section("5) LOAD - เขียนลง SQLite")

    is_new = not DB_FILE.exists()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")   # ต้องสั่งใหม่ทุก connection

    rp.say(f"ไฟล์   : {DB_FILE.name} ({'สร้างใหม่' if is_new else 'เปิดไฟล์เดิม'})")
    rp.say(f"SQLite : {sqlite3.sqlite_version}")
    rp.say(f"foreign_keys = {conn.execute('PRAGMA foreign_keys').fetchone()[0]}")

    rp.say()
    rp.say("สร้างตาราง (IF NOT EXISTS เพื่อให้รันซ้ำได้):")
    for table, ddl in SCHEMAS.items():
        conn.execute(ddl)
        rp.say(f"  {table}")
    conn.commit()

    rp.say()
    rp.say("โหลดแบบ full refresh ครอบใน transaction เดียว")
    rp.say("  ลบ   fact ก่อน dimension  (ไม่งั้นแถวใน fact กลายเป็นเด็กกำพร้า)")
    rp.say("  โหลด dimension ก่อน fact  (ไม่งั้นไม่มี key ให้ชี้ไปหา)")
    rp.say()

    try:
        # with conn คือ transaction สำเร็จหมดถึงจะ commit เจอ exception จะ rollback ให้
        with conn:
            for table in [FACT_TABLE] + DIMENSION_TABLES:
                deleted = conn.execute(f"DELETE FROM {table}").rowcount
                rp.say(f"  DELETE FROM {table:<14} {deleted:>4} แถว")
            rp.say()
            for table in DIMENSION_TABLES + [FACT_TABLE]:
                # ต้องเป็น append ไม่ใช่ replace เพราะ replace ทำงานโดย DROP TABLE
                # แล้วสร้างใหม่จาก dtype ของ DataFrame ทำให้ PK/FK/NOT NULL/UNIQUE/CHECK
                # ที่ออกแบบไว้หายหมด
                tables[table].to_sql(table, conn, if_exists="append", index=False)
                rp.say(f"  INSERT INTO {table:<14} {len(tables[table]):>4} แถว")
    except sqlite3.IntegrityError as error:
        rp.say()
        rp.say(f"โหลดล้มเหลว: {error}")
        rp.say("rollback กลับหมดแล้ว คลังไม่ได้อยู่ในสภาพครึ่ง ๆ กลาง ๆ")
        raise

    rp.say()
    rp.say("commit สำเร็จ")
    return conn


# ---------------------------------------------------------------------------
# 6) VERIFY
# ---------------------------------------------------------------------------

def verify(conn: sqlite3.Connection, tables: dict[str, pd.DataFrame], rp: Reporter) -> None:
    rp.section("6) VERIFY - ตรวจสอบผลลัพธ์")

    checks: list[tuple[str, bool]] = []

    def check(label: str, passed: bool) -> None:
        checks.append((label, bool(passed)))
        rp.say(f"  [{'ผ่าน' if passed else 'ไม่ผ่าน'}] {label}")

    def scalar(sql: str):
        return conn.execute(sql).fetchone()[0]

    rp.say("จำนวนแถว:")
    for table, frame in tables.items():
        actual = scalar(f"SELECT COUNT(*) FROM {table}")
        check(f"{table:<14} {actual:>4} แถว (เท่ากับที่เตรียมไว้ {len(frame)})",
              actual == len(frame))

    rp.say()
    rp.say("ความสมบูรณ์ของการอ้างอิง:")
    for dim, key in [("dim_location", "location_id"),
                     ("dim_product", "product_id"),
                     ("dim_date", "date_key")]:
        orphan = scalar(f"""
            SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN {dim} d ON f.{key} = d.{key}
            WHERE d.{key} IS NULL
        """)
        check(f"fact_sales -> {dim:<14} ไม่มีแถวกำพร้า ({orphan} แถว)", orphan == 0)

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    check(f"PRAGMA foreign_key_check ไม่พบการละเมิด ({len(violations)} รายการ)",
          len(violations) == 0)

    rp.say()
    rp.say("ยอดเงิน (คำนวณใหม่จาก CSV ดิบด้วยโค้ดคนละชุด แล้วเทียบกับในคลัง):")
    # ตั้งใจไม่เรียกฟังก์ชัน transform ข้างบนซ้ำ ถ้าโค้ดตรงนั้นผิด การเทียบจะผิดตาม
    raw = pd.read_csv(RAW_FILE, dtype=str, encoding="utf-8-sig").drop_duplicates()
    gross_raw = (pd.to_numeric(raw["Quantity"]) * pd.to_numeric(raw["Unit_Price"])).round(2)
    discount_raw = (gross_raw * pd.to_numeric(raw["Discount_Percent"]).fillna(0) / 100).round(2)
    net_raw = (gross_raw - discount_raw).round(2)

    for label, expected, column in [
        ("gross_amount", gross_raw.sum(), "gross_amount"),
        ("discount_amount", discount_raw.sum(), "discount_amount"),
        ("net_amount", net_raw.sum(), "net_amount"),
    ]:
        actual = scalar(f"SELECT ROUND(SUM({column}), 2) FROM fact_sales")
        check(f"SUM({label:<15}) = {actual:>12,.2f}  (จาก CSV ดิบ {expected:>12,.2f})",
              abs(actual - expected) < 0.01)

    rp.say()
    rp.say("ฐานข้อมูลปฏิเสธข้อมูลเสียจริงหรือไม่ (ยิงของเสียเข้าไปแล้ว rollback):")
    bad_rows = [
        ("FK ปลอม (location_id = 999)",
         "INSERT INTO fact_sales VALUES ('TEST-1', 999, 1, 20260301, 1, 10, 0, 10, 0, 10)"),
        ("sale_id ซ้ำ",
         "INSERT INTO fact_sales SELECT sale_id, location_id, product_id, date_key,"
         " quantity, unit_price, discount_percent, gross_amount, discount_amount,"
         " net_amount FROM fact_sales LIMIT 1"),
        ("quantity = 0 (ผิด CHECK)",
         "INSERT INTO fact_sales VALUES ('TEST-2', 1, 1, 20260301, 0, 10, 0, 0, 0, 0)"),
    ]
    for label, sql in bad_rows:
        try:
            with conn:
                conn.execute(sql)
            rejected = False
            conn.execute("DELETE FROM fact_sales WHERE sale_id LIKE 'TEST-%'")
            conn.commit()
        except sqlite3.IntegrityError:
            rejected = True   # with conn จัดการ rollback ให้แล้ว
        check(f"ปฏิเสธ {label}", rejected)

    failed = [label for label, passed in checks if not passed]
    rp.say()
    rp.say(f"สรุป: ผ่าน {len(checks) - len(failed)}/{len(checks)} ข้อ")
    if failed:
        raise ValueError("การตรวจสอบไม่ผ่าน:\n  " + "\n  ".join(failed))


# ---------------------------------------------------------------------------
# 7) ตัวอย่างการใช้งานคลัง
# ---------------------------------------------------------------------------

BUSINESS_QUERIES = {
    "ยอดขายรายภูมิภาค": """
        SELECT l.region,
               COUNT(*)                  AS orders,
               SUM(f.quantity)           AS units,
               ROUND(SUM(f.net_amount),2) AS revenue
        FROM fact_sales f
        JOIN dim_location l ON f.location_id = l.location_id
        GROUP BY l.region
        ORDER BY revenue DESC
    """,
    "ยอดขายรายสาขา": """
        SELECT l.store_code, l.branch, l.province,
               COUNT(*)                   AS orders,
               ROUND(SUM(f.net_amount),2) AS revenue,
               ROUND(AVG(f.net_amount),2) AS avg_order
        FROM fact_sales f
        JOIN dim_location l ON f.location_id = l.location_id
        GROUP BY l.location_id
        ORDER BY revenue DESC
    """,
    "สินค้าขายดี": """
        SELECT p.product_name, p.category,
               SUM(f.quantity)            AS units,
               ROUND(SUM(f.net_amount),2) AS revenue
        FROM fact_sales f
        JOIN dim_product p ON f.product_id = p.product_id
        GROUP BY p.product_id
        ORDER BY revenue DESC
    """,
    "แนวโน้มรายเดือน (รวมวันที่ขายไม่ออก)": """
        SELECT d.month_name,
               COUNT(DISTINCT d.date_key)                              AS days_in_month,
               COUNT(DISTINCT CASE WHEN f.sale_id IS NOT NULL
                                   THEN d.date_key END)                AS days_with_sales,
               COUNT(f.sale_id)                                        AS orders,
               ROUND(COALESCE(SUM(f.net_amount), 0), 2)                AS revenue
        FROM dim_date d
        LEFT JOIN fact_sales f ON d.date_key = f.date_key
        GROUP BY d.year, d.month
        ORDER BY d.year, d.month
    """,
    "ผลกระทบของส่วนลดต่อหมวดสินค้า": """
        SELECT p.category,
               ROUND(SUM(f.gross_amount),2)    AS gross,
               ROUND(SUM(f.discount_amount),2) AS discount,
               ROUND(SUM(f.net_amount),2)      AS net,
               ROUND(100.0 * SUM(f.discount_amount) / SUM(f.gross_amount), 2) AS discount_pct
        FROM fact_sales f
        JOIN dim_product p ON f.product_id = p.product_id
        GROUP BY p.category
        ORDER BY gross DESC
    """,
}


def run_business_queries(conn: sqlite3.Connection, rp: Reporter) -> None:
    rp.section("7) ตัวอย่างคำถามธุรกิจที่คลังนี้ตอบได้")

    for title, sql in BUSINESS_QUERIES.items():
        rp.say()
        rp.say(f"--- {title} ---")
        show(pd.read_sql_query(sql, conn), rp, limit=12)


# ---------------------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)

    rp = Reporter()

    raw = extract(rp)
    clean_df = clean(raw, rp)
    tables = build_dimensions(clean_df, rp)
    tables["fact_sales"] = build_fact(clean_df, tables, rp)

    for name, frame in tables.items():
        save_csv(frame, f"{name}.csv")

    conn = load(tables, rp)
    try:
        verify(conn, tables, rp)
        run_business_queries(conn, rp)
    finally:
        conn.close()

    rp.section("เสร็จสิ้น")
    rp.say(f"คลังข้อมูล : {DB_FILE}")
    rp.say(f"ไฟล์กลาง   : {OUTPUT_DIR}")
    rp.save(OUTPUT_DIR / "etl_report.txt")


if __name__ == "__main__":
    main()
