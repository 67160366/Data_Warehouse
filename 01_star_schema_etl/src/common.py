"""ฟังก์ชันที่ใช้ร่วมกันหลาย step

รวม path, การทำความสะอาดข้อความ และการแปลงวันที่/ตัวเลขไว้ที่เดียว
ถ้าก๊อปโค้ดพวกนี้ไปวางทั้งใน 2A และ 2B แล้ววันหนึ่งแก้แค่ที่เดียว
dimension กับ fact จะใช้ค่าคนละแบบจน join ไม่ติด
"""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_FILE = BASE_DIR / "Workshop" / "raw_ecommerce_data.csv"
OUTPUT_DIR = BASE_DIR / "output"
WAREHOUSE_DIR = BASE_DIR / "warehouse"
DB_FILE = WAREHOUSE_DIR / "dw.sqlite"


def setup_console() -> None:
    """กัน UnicodeEncodeError ตอน print ภาษาไทย/฿ บน console ของ Windows"""
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)


class Reporter:
    """print ออกจอ พร้อมเก็บข้อความไว้เขียนลงไฟล์รายงาน"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(str(text))

    def section(self, title: str) -> None:
        self.say()
        self.say("=" * 70)
        self.say(f"  {title}")
        self.say("=" * 70)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines), encoding="utf-8")
        print()
        print(f"บันทึกรายงาน: {path}")


def clean_text(series: pd.Series) -> pd.Series:
    """ตัดช่องว่างหัวท้าย และบีบช่องว่างกลางข้อความให้เหลือตัวเดียว

    '  Emma   Brown  ' -> 'Emma Brown'
    """
    return series.str.strip().str.replace(r"\s+", " ", regex=True)


def norm_key(series: pd.Series) -> pd.Series:
    """แปลงเป็นตัวพิมพ์เล็กเพื่อใช้จับกลุ่ม ไม่ได้เอาไปแสดงผล"""
    return clean_text(series).str.lower()


def pick_display_spelling(values: pd.Series) -> str:
    """เลือกการสะกดที่จะใช้แสดงใน dimension

    อย่าใช้ .str.title() เพราะจะได้ 'Usb-C Hub' กับ 'Portable Ssd 1Tb'

    คัดสองชั้น:
      1. ตัดการสะกดที่เป็นพิมพ์ใหญ่ล้วน/เล็กล้วนออกก่อน รูปแบบพวกนี้มักเป็น
         ร่องรอยการกรอก ไม่ใช่ชื่อจริง
      2. ที่เหลือเอาอันที่พบบ่อยสุด เท่ากันก็เรียงตัวอักษร (ให้ผลคงที่ทุกรอบ)

    ที่ต้องมีชั้นแรกด้วยเพราะเสียงข้างมากเชื่อไม่ได้ตอน sample เล็ก เช่นลูกค้า
    suda chai มี 3 ออเดอร์ สะกด 'SUDA CHAI' 2 ครั้ง 'Suda Chai' 1 ครั้ง
    """
    counts = values.dropna().value_counts()
    natural = [v for v in counts.index if not v.isupper() and not v.islower()]
    pool = natural if natural else list(counts.index)
    return sorted(pool, key=lambda v: (-counts[v], v))[0]


# ไฟล์ต้นทางมีวันที่ 3 ฟอร์แมตปนกัน ประกาศไว้ตรงนี้ที่เดียว
DATE_FORMATS = [
    (r"^\d{2}/\d{2}/\d{4}$", "%d/%m/%Y"),              # 24/04/2026 วันขึ้นก่อน
    (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),              # 2026-02-28
    (r"^[A-Za-z]{3} \d{1,2}, \d{4}$", "%b %d, %Y"),    # Apr 03, 2026
]


def parse_dates_strict(series: pd.Series) -> pd.Series:
    """แปลงวันที่ทีละฟอร์แมตโดยระบุ format แล้วบังคับว่าห้ามเหลือ NaT

    ห้ามเรียก pd.to_datetime() เฉย ๆ เพราะค่าเริ่มต้นคือ dayfirst=False
    '03/04/2026' จะถูกอ่านเป็น 4 มีนาคมแทน 3 เมษายน และไม่มี error ฟ้อง

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


def parse_money(series: pd.Series) -> pd.Series:
    """ลอก ฿ กับ , ออกแล้วแปลงเป็น float, ค่าว่างได้ NaN

    '฿25,160.00' -> 25160.0
    """
    return pd.to_numeric(
        series.str.replace(r"[^0-9.\-]", "", regex=True).replace("", pd.NA),
        errors="coerce",
    )


def build_lookup(df: pd.DataFrame, key_col: str, value_col: str, label: str) -> dict:
    """สร้าง mapping key -> value พร้อมตรวจว่าเป็น 1:1 ก่อนคืนค่า

    การเติมค่าที่หายจากแถวอื่นจะปลอดภัยก็ต่อเมื่อ key หนึ่งผูกกับ value เดียว
    ถ้า john@email.com ผูกกับสองชื่อ ต้องให้โปรแกรมหยุด ไม่ใช่เดาแล้วไปต่อ
    """
    pairs = df[[key_col, value_col]].dropna()
    conflicts = pairs.groupby(key_col)[value_col].nunique()
    conflicts = conflicts[conflicts > 1]

    if len(conflicts) > 0:
        raise ValueError(
            f"[{label}] ไม่ใช่ 1:1 เติมค่าอัตโนมัติไม่ได้\n"
            f"  key ที่มีปัญหา: {list(conflicts.index)}"
        )

    return pairs.drop_duplicates().set_index(key_col)[value_col].to_dict()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """เขียน CSV แบบ utf-8-sig ให้ Excel เปิดแล้วไม่เพี้ยน"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
