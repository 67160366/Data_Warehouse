"""Step 1 (Extract) - อ่านข้อมูลดิบและสำรวจปัญหา

ขั้นนี้ไม่แก้ข้อมูลเลยแม้แต่ตัวเดียว หน้าที่คือดูให้เห็นปัญหาทั้งหมดก่อน
ถ้ารีบ clean ตั้งแต่ตอนนี้จะไม่มีทางรู้ว่าต้นทางส่งอะไรมาให้บ้าง

ผลลัพธ์: output/01_profile_report.txt
"""

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_FILE = BASE_DIR / "Workshop" / "raw_ecommerce_data.csv"
OUTPUT_DIR = BASE_DIR / "output"
REPORT_FILE = OUTPUT_DIR / "01_profile_report.txt"

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

_lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    _lines.append(str(text))


def section(title: str) -> None:
    say()
    say("=" * 70)
    say(f"  {title}")
    say("=" * 70)


section("1) อ่านไฟล์ดิบ")

# dtype=str บังคับไว้เพื่อให้ได้ข้อความตามที่เขียนในไฟล์เป๊ะ ๆ
# ถ้าปล่อยให้ pandas เดา Amount จะกลายเป็น object ปนกันมั่ว บางแถว str บางแถว float
df = pd.read_csv(RAW_FILE, dtype=str)

say(f"ไฟล์ : {RAW_FILE}")
say(f"ขนาด : {df.shape[0]} แถว x {df.shape[1]} คอลัมน์")
say()
say("--- 10 แถวแรก ---")
say(df.head(10).to_string())


section("2) ชนิดข้อมูล")

say(df.dtypes.to_string())
say()
say("ทุกคอลัมน์เป็น object เพราะบังคับ dtype=str ไว้")
say()
say("--- describe ---")
say(df.describe(include="all").to_string())


section("3) ค่าที่หายไป")

missing = pd.DataFrame({
    "missing": df.isna().sum(),
    "percent": (df.isna().sum() / len(df) * 100).round(2),
})
say(missing.to_string())
say()
say("Amount หายเยอะสุด ต้องหาว่ามีสูตรคำนวณกลับได้ไหม")
say("ที่เหลือหายไม่กี่แถว ดูว่ากู้จากแถวอื่นได้หรือเปล่า")


section("4) Cardinality")

card = pd.DataFrame({
    "nunique": df.nunique(dropna=True),
    "ratio_to_rows": (df.nunique(dropna=True) / len(df)).round(3),
})
say(card.to_string())
say()
say("ใช้ตัดสินว่าคอลัมน์ไหนควรเป็นอะไรใน star schema:")
say("  ค่าซ้ำเยอะ nunique ต่ำ   -> เป็นบริบท ควรแยกไป dimension")
say("  nunique เท่าจำนวนแถว     -> เป็นตัวระบุรายการ")
say("  ตัวเลขที่วัดค่าได้        -> เป็น measure อยู่ใน fact")


section("5) ข้อมูลซ้ำ")

say(f"ซ้ำสนิทแบบดิบ (ไม่ normalize) : {df.duplicated().sum()}")

# normalize ชั่วคราวเพื่อ "ดู" เท่านั้น ไม่เขียนกลับลง df
peek = df.apply(lambda c: c.str.strip())
for col in ["Customer_Name", "Email", "Product", "Category"]:
    peek[col] = peek[col].str.lower()

say(f"ซ้ำสนิทหลัง strip + lower      : {peek.duplicated().sum()}")
say(f"Order_ID ที่ซ้ำ                : {peek['Order_ID'].duplicated().sum()}")
say()
say("--- แถวที่ Order_ID ซ้ำ ---")
say(peek[peek["Order_ID"].duplicated(keep=False)].sort_values("Order_ID").to_string())
say()
say("ตัวเลขสองอันแรกไม่เท่ากัน แปลว่ามีแถวที่ซ้ำจริงแต่มองด้วยตาไม่เห็น")
say("เพราะต่างกันแค่ช่องว่างหรือตัวพิมพ์ ต้อง normalize ก่อนถึงจะ dedup ได้ครบ")


section("6) ฟอร์แมตของ Order_Date")

date_col = df["Order_Date"].str.strip()

patterns = {
    "DD/MM/YYYY   (24/04/2026)": r"^\d{2}/\d{2}/\d{4}$",
    "YYYY-MM-DD   (2026-02-28)": r"^\d{4}-\d{2}-\d{2}$",
    "Mon DD, YYYY (Apr 03, 2026)": r"^[A-Za-z]{3} \d{1,2}, \d{4}$",
}

matched_any = pd.Series(False, index=date_col.index)
for label, pattern in patterns.items():
    hit = date_col.str.match(pattern)
    matched_any |= hit
    say(f"  {label:<32} : {hit.sum():>3} แถว")
say(f"  {'ไม่ตรง pattern ใดเลย':<32} : {(~matched_any).sum():>3} แถว")

slash = date_col[date_col.str.match(patterns["DD/MM/YYYY   (24/04/2026)"])]
first_over_12 = (slash.str[:2].astype(int) > 12).sum()
second_over_12 = (slash.str[3:5].astype(int) > 12).sum()

say()
say("เช็คว่า DD/MM/YYYY เป็นวันขึ้นก่อนจริงไหม:")
say(f"  เลขตัวหน้า > 12 : {first_over_12} แถว  (ถ้ามี แปลว่าตัวหน้าคือวัน)")
say(f"  เลขตัวหลัง > 12 : {second_over_12} แถว  (ถ้าไม่มี แปลว่าตัวหลังคือเดือน)")
say()
say("อันตรายตรงนี้: pd.to_datetime() ตั้ง dayfirst=False ไว้เป็นค่าเริ่มต้น")
say("ปล่อยให้เดาเอง '03/04/2026' จะกลายเป็น 4 มีนาคมแทน 3 เมษายน")
say("ยอดขายรายเดือนเพี้ยนทันทีโดยไม่มี error ฟ้อง")
say("ต้องแยก parse ทีละ pattern แล้วเช็คว่าไม่เหลือ NaT")


section("7) whitespace และตัวพิมพ์")

say("--- แถวที่มีช่องว่างหัวหรือท้าย ---")
for col in df.columns:
    has_space = (df[col] != df[col].str.strip()) & df[col].notna()
    if has_space.any():
        say(f"  {col:<15} : {has_space.sum():>3} แถว")

say()
say("--- ค่าที่สะกดตัวพิมพ์ไม่ตรงกัน ---")
for col in ["Customer_Name", "Email", "Product", "Category"]:
    norm = df[col].str.strip().str.lower()
    variants = df[col].str.strip().groupby(norm).nunique()
    problem = variants[variants > 1]
    say(f"  {col} : {len(problem)} ค่า")
    for value, count in problem.items():
        spellings = sorted(set(df[col].str.strip()[norm == value].dropna()))
        say(f"      {value!r:<28} ({count} แบบ) {spellings}")


section("8) ตัวเลขที่ยังเป็นข้อความ")

for col in ["Unit_Price", "Amount"]:
    values = df[col].dropna()
    say(f"--- {col} ---")
    say(f"  มี ฿  : {values.str.contains('฿').sum():>3} แถว")
    say(f"  มี ,  : {values.str.contains(',').sum():>3} แถว")
    dirty = values[values.str.contains(r"[฿,]", regex=True)]
    say(f"  ตัวอย่าง : {list(dirty.head(5))}")
    say()

say("ทั้งสองคอลัมน์ยังคำนวณไม่ได้ ต้องลอก ฿ กับ , ออกก่อนใน Step 2B")


section("9) Unit_Price ควรอยู่ที่ไหน")

product_norm = df["Product"].str.strip().str.lower()
price_variety = (
    df.groupby(product_norm)["Unit_Price"]
    .agg(distinct_price="nunique", n_orders="size")
    .sort_values("distinct_price", ascending=False)
)
say(price_variety.to_string())
say()
say("สินค้าชิ้นเดียวกันขายได้หลายราคา (ราคาเปลี่ยนตามเวลาหรือโปรโมชั่น)")
say()
say(f"  เอาเข้า dim_product     -> dimension บวมเป็น {price_variety['distinct_price'].sum()} แถว")
say(f"  ไม่เอาเข้า              -> เหลือ {len(price_variety)} แถวตามจำนวนสินค้าจริง")
say()
say("ราคาที่ขายจริง ณ ตอนนั้นเป็น measure ของธุรกรรม ไม่ใช่คุณสมบัติถาวรของสินค้า")
say("จึงต้องอยู่ใน fact_sales")


section("10) สรุปปัญหาและขั้นที่จะแก้")

say(f"  แถวซ้ำ {peek.duplicated().sum()} แถว (ซ่อนอยู่ใต้ whitespace/case)   -> 2A")
say(f"  ช่องว่างหัวท้ายกระจายหลายคอลัมน์                -> 2A")
say(f"  ตัวพิมพ์ใหญ่เล็กไม่ตรงกัน                        -> 2A")
say(f"  Customer_Name หาย {df['Customer_Name'].isna().sum()} แถว                          -> 2A")
say(f"  Email หาย {df['Email'].isna().sum()} แถว                                 -> 2A")
say(f"  Category หาย {df['Category'].isna().sum()} แถว                              -> 2A")
say(f"  Order_Date มี {len(patterns)} ฟอร์แมตปนกัน                      -> 2A")
say(f"  Unit_Price / Amount เป็นข้อความมี ฿ และ ,        -> 2B")
say(f"  Amount หาย {df['Amount'].isna().sum()} แถว                                -> 2B")
say()
say("ไฟล์ต้นฉบับยังไม่ถูกแก้ไขใด ๆ")

OUTPUT_DIR.mkdir(exist_ok=True)
REPORT_FILE.write_text("\n".join(_lines), encoding="utf-8")
print()
print(f"บันทึกรายงาน: {REPORT_FILE}")
