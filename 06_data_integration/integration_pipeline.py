"""
Week08 Lab - Data Integration Pipeline
TechTrove E-Commerce: รวมข้อมูลจากหลายระบบให้พร้อมวิเคราะห์ยอดขาย

โครงสร้างตามหัวข้อในใบงาน
    5.1 Extract & Profile        -> extract, profile
    5.2 Combine Orders           -> align_january, align_february, combine_orders
    5.3 Transform                -> clean_orders, clean_customers, clean_products, clean_payments
    5.4 Integrate & Validate     -> integrate, apply_business_rules
    5.5 Load                     -> build_dimensions, build_fact, DataQualityLog.to_frame
    5.6 Analyze                  -> summarize_by_province, summarize_by_category, answer_questions
    Challenge (+2)               -> validate_data, plot_funnel, plot_before_after

การใช้งาน
    python integration_pipeline.py          รันทั้ง pipeline แล้วเขียนผลลัพธ์ลง output/ และ figures/
    python integration_pipeline.py --quiet  รันแบบไม่พิมพ์ profile ยาว ๆ (ใช้ตอน import จาก notebook)

กติกาสำคัญ: ห้ามแก้ไฟล์ใน data/ ทุกการแก้ไขเกิดในโค้ดเพื่อให้ตรวจย้อนกลับและรันซ้ำได้
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
FIGURES = ROOT / "figures"

# ---------------------------------------------------------------- คอนสแตนต์

# schema drift: ก.พ. ใช้ชื่อคอลัมน์คนละชุดกับ ม.ค. ต้อง rename ให้ตรงก่อน concat
FEB_RENAME = {"ordered_at": "order_date", "qty": "quantity", "discount_pct": "discount"}

# ระบุ format ตรง ๆ ห้ามให้ pandas เดา มิฉะนั้น 08/02/2026 จะถูกอ่านสลับวัน-เดือน
JAN_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FEB_DATETIME_FORMAT = "%d/%m/%Y %H:%M"
PAID_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"

# ชื่อจังหวัดมาตรฐาน (ภาษาไทย) key คือค่าที่ normalize แล้วและแปลงเป็นตัวพิมพ์เล็ก
PROVINCE_MAP = {
    "กรุงเทพมหานคร": "กรุงเทพมหานคร",
    "กทม.": "กรุงเทพมหานคร",
    "กทม": "กรุงเทพมหานคร",
    "bangkok": "กรุงเทพมหานคร",
    "ชลบุรี": "ชลบุรี",
    "chonburi": "ชลบุรี",
    "เชียงใหม่": "เชียงใหม่",
    "chiang mai": "เชียงใหม่",
    "chiangmai": "เชียงใหม่",
    "ขอนแก่น": "ขอนแก่น",
    "khon kaen": "ขอนแก่น",
    "khonkaen": "ขอนแก่น",
    "ภูเก็ต": "ภูเก็ต",
    "phuket": "ภูเก็ต",
    "ระยอง": "ระยอง",
    "rayong": "ระยอง",
}
PROVINCE_UNKNOWN = "ไม่ระบุ"

ONLY_PAID_STATUS = "PAID"


# ---------------------------------------------------------------- ตัวช่วยเก็บหลักฐาน


class DataQualityLog:
    """เก็บทุกการตรวจและทุกการแก้ไข เพื่อเขียนเป็น data_quality_report.csv"""

    COLUMNS = [
        "step",
        "check",
        "metric",
        "rows_before",
        "rows_after",
        "rows_affected",
        "action",
        "note",
    ]

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def add(
        self,
        step: str,
        check: str,
        metric: str,
        rows_before: int | str = "",
        rows_after: int | str = "",
        rows_affected: int | str = "",
        action: str = "",
        note: str = "",
    ) -> None:
        self._rows.append(
            {
                "step": step,
                "check": check,
                "metric": metric,
                "rows_before": rows_before,
                "rows_after": rows_after,
                "rows_affected": rows_affected,
                "action": action,
                "note": note,
            }
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self._rows, columns=self.COLUMNS)


class RejectStore:
    """เก็บแถวที่ถูกคัดออกพร้อม reason_code เพื่อไม่ให้ข้อมูลหายไปเงียบ ๆ"""

    def __init__(self) -> None:
        self._frames: list[pd.DataFrame] = []

    def add(self, df: pd.DataFrame, reason_code: str, stage: str) -> None:
        if df.empty:
            return
        out = df.copy()
        out.insert(0, "reason_code", reason_code)
        out.insert(1, "stage", stage)
        self._frames.append(out)

    def to_frame(self) -> pd.DataFrame:
        if not self._frames:
            return pd.DataFrame(columns=["reason_code", "stage"])
        return pd.concat(self._frames, ignore_index=True)


# ---------------------------------------------------------------- 5.1 Extract & Profile


def profile(df: pd.DataFrame, name: str, key: str | None = None, verbose: bool = True) -> dict:
    """สำรวจคุณภาพข้อมูลเบื้องต้น: shape, dtype, missing, duplicate และตัวอย่างค่า"""
    info = {
        "name": name,
        "rows": len(df),
        "columns": len(df.columns),
        "missing_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_key": int(df[key].duplicated().sum()) if key else 0,
    }
    if verbose:
        print(f"\n--- profile: {name} ---")
        print(f"shape: {df.shape[0]} แถว x {df.shape[1]} คอลัมน์")
        summary = pd.DataFrame(
            {
                "dtype": df.dtypes.astype(str),
                "missing": df.isna().sum(),
                "n_unique": df.nunique(dropna=True),
                "sample": [
                    ", ".join(map(str, df[c].dropna().unique()[:3])) for c in df.columns
                ],
            }
        )
        print(summary.to_string())
        line = f"แถวซ้ำทั้งแถว: {info['duplicate_rows']}"
        if key:
            line += f" | {key} ซ้ำ: {info['duplicate_key']}"
        print(f"{line} | ค่าว่างรวม: {info['missing_total']}")
    return info


def extract(verbose: bool = True) -> dict[str, pd.DataFrame]:
    """อ่านข้อมูลจาก CSV, Excel และ nested JSON"""
    jan = pd.read_csv(DATA / "orders_2026_01.csv", encoding="utf-8-sig")
    feb = pd.read_csv(DATA / "orders_2026_02.csv", encoding="utf-8-sig")
    customers = pd.read_csv(DATA / "customers_crm.csv", encoding="utf-8-sig")
    products = pd.read_excel(DATA / "product_master.xlsx")
    with open(DATA / "payments.json", encoding="utf-8") as fh:
        payments_raw = json.load(fh)
    # payments.json เป็น nested: payment.method / payment.status อยู่ลึกลงไปหนึ่งชั้น
    payments = pd.json_normalize(payments_raw)

    if verbose:
        print("=" * 78)
        print("5.1 EXTRACT & PROFILE — คุณภาพข้อมูลก่อนทำ Data Integration")
        print("=" * 78)
    return {
        "orders_jan": jan,
        "orders_feb": feb,
        "customers": customers,
        "products": products,
        "payments": payments,
    }


# ---------------------------------------------------------------- 5.2 Combine Orders


def align_january(jan: pd.DataFrame) -> pd.DataFrame:
    out = jan.copy()
    out["order_date"] = pd.to_datetime(
        out["order_date"], format=JAN_DATETIME_FORMAT, errors="coerce"
    )
    out["discount"] = pd.to_numeric(out["discount"], errors="coerce")
    out["source_file"] = "orders_2026_01.csv"
    return out


def align_february(feb: pd.DataFrame) -> pd.DataFrame:
    """ปรับ schema ของ ก.พ. ให้เหมือน ม.ค.: ชื่อคอลัมน์ รูปแบบวันที่ และหน่วยของ discount"""
    out = feb.rename(columns=FEB_RENAME).copy()
    out["order_date"] = pd.to_datetime(
        out["order_date"], format=FEB_DATETIME_FORMAT, errors="coerce"
    )
    # "5%" -> 0.05 ให้อยู่ในหน่วยเดียวกับเดือน ม.ค.
    discount = out["discount"].astype("string").str.strip().str.rstrip("%")
    out["discount"] = pd.to_numeric(discount, errors="coerce") / 100
    out["source_file"] = "orders_2026_02.csv"
    return out


def combine_orders(jan: pd.DataFrame, feb: pd.DataFrame, dq: DataQualityLog) -> pd.DataFrame:
    columns = [
        "order_id",
        "order_date",
        "customer_id",
        "product_id",
        "quantity",
        "unit_price",
        "discount",
        "channel",
        "source_file",
    ]
    aligned_jan = align_january(jan)[columns]
    aligned_feb = align_february(feb)[columns]
    combined = pd.concat([aligned_jan, aligned_feb], ignore_index=True)

    dq.add(
        "5.2 combine",
        "schema_alignment",
        "คอลัมน์ที่ rename ของเดือน ก.พ.",
        rows_before=len(feb.columns),
        rows_after=len(aligned_feb.columns),
        rows_affected=len(FEB_RENAME),
        action="rename + แปลง discount จาก % เป็นสัดส่วน + parse วันที่ dd/mm/yyyy",
        note=", ".join(f"{k}->{v}" for k, v in FEB_RENAME.items()),
    )
    dq.add(
        "5.2 combine",
        "concat_orders",
        "จำนวนแถวหลังรวมสองเดือน",
        rows_before=len(jan) + len(feb),
        rows_after=len(combined),
        rows_affected=0,
        action="pd.concat(ignore_index=True)",
        note=f"ม.ค. {len(jan)} แถว + ก.พ. {len(feb)} แถว",
    )
    return combined


# ---------------------------------------------------------------- 5.3 Transform


def normalize_text(series: pd.Series) -> pd.Series:
    """ตัดช่องว่างหัวท้าย ยุบช่องว่างซ้ำ และแก้สระ เเ (เ+เ) ให้เป็น แ ตัวเดียว"""
    out = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    out = out.map(lambda v: unicodedata.normalize("NFC", v) if pd.notna(v) else v)
    return out.str.replace("เเ", "แ", regex=False)


def standardize_province(series: pd.Series) -> pd.Series:
    cleaned = normalize_text(series)
    return cleaned.str.lower().map(PROVINCE_MAP).fillna(PROVINCE_UNKNOWN)


def clean_orders(orders: pd.DataFrame, dq: DataQualityLog, rejects: RejectStore) -> pd.DataFrame:
    """แปลงชนิดข้อมูล ทำ channel ให้เป็นมาตรฐาน แล้วลบ order_id ซ้ำ (เก็บแถวหลังสุด)"""
    out = orders.copy()
    for col in ["order_id", "customer_id", "product_id", "channel"]:
        out[col] = normalize_text(out[col])
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").astype("Int64")
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce")
    out["discount"] = pd.to_numeric(out["discount"], errors="coerce")

    dq.add(
        "5.3 transform",
        "dtype_cast_orders",
        "แปลงชนิดข้อมูล quantity/unit_price/discount/order_date",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=0,
        action="astype Int64 / float / datetime64",
        note="ค่าที่แปลงไม่ได้กลายเป็น NA แล้วถูกคัดออกในขั้น 5.5",
    )

    before = len(out)
    duplicated_mask = out.duplicated(subset=["order_id"], keep="last")
    rejects.add(out[duplicated_mask], "DUPLICATE_ORDER_ID", "5.3 dedup orders")
    out = out[~duplicated_mask].reset_index(drop=True)
    dq.add(
        "5.3 transform",
        "duplicate_order_id",
        "order_id ซ้ำ",
        rows_before=before,
        rows_after=len(out),
        rows_affected=before - len(out),
        action="drop_duplicates(subset='order_id', keep='last')",
        note="กติกาข้อ 4.1 เก็บข้อมูลล่าสุดตามลำดับที่ปรากฏ",
    )
    return out


def clean_customers(customers: pd.DataFrame, dq: DataQualityLog) -> pd.DataFrame:
    """ทำ email เป็นตัวพิมพ์เล็ก ปรับชื่อจังหวัดให้เป็นมาตรฐาน แล้วลบลูกค้าซ้ำ"""
    out = customers.copy()
    out["customer_id"] = normalize_text(out["customer_id"])
    out["full_name"] = normalize_text(out["full_name"])

    raw_email = out["email"].astype("string")
    out["email"] = raw_email.str.strip().str.lower()
    email_fixed = int((raw_email.notna() & (raw_email != out["email"])).sum())
    dq.add(
        "5.3 transform",
        "email_standardization",
        "email ที่มีช่องว่าง/ตัวพิมพ์ใหญ่",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=email_fixed,
        action="str.strip().str.lower()",
        note="ตัวอย่างก่อนแก้: ' CUSTOMER017@EXAMPLE.COM '",
    )
    dq.add(
        "5.3 transform",
        "email_missing",
        "email ว่าง",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=int(out["email"].isna().sum()),
        action="คงไว้",
        note="email ไม่ใช่คีย์ทางธุรกิจ จึงไม่ตัดแถวทิ้ง แต่บันทึกไว้",
    )

    # นับรูปแบบที่เขียนต่างกันจริงในไฟล์ต้นทาง (ยังไม่ normalize) เพื่อให้เทียบกับสิ่งที่เห็นในไฟล์ได้ตรง
    raw_province_variants = int(customers["province"].nunique())
    normalized_variants = int(normalize_text(customers["province"]).nunique())
    out["province"] = standardize_province(out["province"])
    province_fixed = int(
        (normalize_text(customers["province"]).fillna("") != out["province"].fillna("")).sum()
    )
    dq.add(
        "5.3 transform",
        "province_standardization",
        "จังหวัดที่เขียนไม่ตรงมาตรฐาน",
        rows_before=raw_province_variants,
        rows_after=int(out["province"].nunique()),
        rows_affected=province_fixed,
        action="normalize + map ตาม PROVINCE_MAP",
        note=(
            f"{raw_province_variants} รูปแบบในไฟล์ต้นทาง -> {normalized_variants} รูปแบบหลัง normalize "
            f"(ตัดช่องว่างและแก้ เ+เ) -> {int(out['province'].nunique())} จังหวัดมาตรฐาน "
            "รวมชื่ออังกฤษ, 'กทม.', ช่องว่างท้ายชื่อ และ 'ขอนเเก่น' ที่สะกดด้วย เ+เ"
        ),
    )
    dq.add(
        "5.3 transform",
        "province_unmapped",
        f"จังหวัดที่ map ไม่ได้ (= '{PROVINCE_UNKNOWN}')",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=int((out["province"] == PROVINCE_UNKNOWN).sum()),
        action="ตั้งเป็น 'ไม่ระบุ'",
        note="ไม่เดาชื่อจังหวัดเอง",
    )

    out["signup_date"] = pd.to_datetime(out["signup_date"], errors="coerce").dt.date

    before = len(out)
    out = out.drop_duplicates(subset=["customer_id"], keep="last").reset_index(drop=True)
    dq.add(
        "5.3 transform",
        "duplicate_customer_id",
        "customer_id ซ้ำใน CRM",
        rows_before=before,
        rows_after=len(out),
        rows_affected=before - len(out),
        action="drop_duplicates(subset='customer_id', keep='last')",
        note="ต้องทำก่อน merge มิฉะนั้น validate='m:1' จะโยน MergeError",
    )
    return out.sort_values("customer_id").reset_index(drop=True)


def clean_products(products: pd.DataFrame, dq: DataQualityLog) -> pd.DataFrame:
    out = products.copy()
    for col in ["product_id", "product_name", "category", "active_flag"]:
        out[col] = normalize_text(out[col])
    out["active_flag"] = out["active_flag"].str.upper()
    out["standard_price"] = pd.to_numeric(out["standard_price"], errors="coerce")

    before = len(out)
    out = out.drop_duplicates(subset=["product_id"], keep="last").reset_index(drop=True)
    dq.add(
        "5.3 transform",
        "duplicate_product_id",
        "product_id ซ้ำใน master",
        rows_before=before,
        rows_after=len(out),
        rows_affected=before - len(out),
        action="drop_duplicates(subset='product_id', keep='last')",
        note="ชุดนี้ไม่พบซ้ำ แต่คงขั้นตอนไว้เพื่อกันข้อมูลรอบหน้า",
    )
    dq.add(
        "5.3 transform",
        "inactive_product",
        "สินค้าที่ active_flag = 'N'",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=int((out["active_flag"] == "N").sum()),
        action="คงไว้ใน dim_product",
        note="สินค้าเลิกขายแล้วแต่ยังมีคำสั่งซื้อย้อนหลัง จึงไม่ตัดออกจาก dimension",
    )
    return out.sort_values("product_id").reset_index(drop=True)


def clean_payments(payments: pd.DataFrame, dq: DataQualityLog) -> pd.DataFrame:
    """คลี่ nested payment แล้วลบเหตุการณ์ซ้ำ ให้เหลือหนึ่งแถวต่อหนึ่ง order"""
    out = payments.rename(
        columns={"payment.method": "payment_method", "payment.status": "payment_status"}
    ).copy()
    for col in ["payment_id", "order_id", "payment_method", "payment_status"]:
        out[col] = normalize_text(out[col])
    out["payment_status"] = out["payment_status"].str.upper()
    out["paid_at"] = pd.to_datetime(out["paid_at"], format=PAID_AT_FORMAT, errors="coerce")

    before = len(out)
    out = out.drop_duplicates(subset=["payment_id"], keep="last")
    after_payment_id = len(out)
    dq.add(
        "5.3 transform",
        "duplicate_payment_id",
        "payment_id ซ้ำ",
        rows_before=before,
        rows_after=after_payment_id,
        rows_affected=before - after_payment_id,
        action="drop_duplicates(subset='payment_id', keep='last')",
    )

    out = out.drop_duplicates(subset=["order_id"], keep="last").reset_index(drop=True)
    dq.add(
        "5.3 transform",
        "multiple_payment_per_order",
        "order_id ที่มีเหตุการณ์ชำระเงินมากกว่าหนึ่งครั้ง",
        rows_before=after_payment_id,
        rows_after=len(out),
        rows_affected=after_payment_id - len(out),
        action="drop_duplicates(subset='order_id', keep='last')",
        note="เก็บสถานะล่าสุดตามลำดับที่ปรากฏ เพื่อให้ merge เป็น 1:1",
    )
    status_counts = out["payment_status"].value_counts().to_dict()
    dq.add(
        "5.3 transform",
        "payment_status_mix",
        "สัดส่วนสถานะการชำระเงิน",
        rows_before=len(out),
        rows_after=len(out),
        rows_affected=int(len(out) - status_counts.get(ONLY_PAID_STATUS, 0)),
        action="ยังไม่ตัดออก รอกรองในขั้น 5.5",
        note=" | ".join(f"{k}={v}" for k, v in sorted(status_counts.items())),
    )
    return out


# ---------------------------------------------------------------- 5.4 Integrate & Validate


def integrate(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    payments: pd.DataFrame,
    dq: DataQualityLog,
    verbose: bool = True,
) -> pd.DataFrame:
    """merge ลูกค้า สินค้า และการชำระเงิน พร้อมตรวจ cardinality ด้วย validate= และ indicator="""
    merged = orders.merge(
        customers[["customer_id", "full_name", "email", "province", "signup_date"]],
        on="customer_id",
        how="left",
        validate="m:1",
        indicator="_merge_customer",
    )
    merged = merged.merge(
        products[["product_id", "product_name", "category", "standard_price", "active_flag"]],
        on="product_id",
        how="left",
        validate="m:1",
        indicator="_merge_product",
    )
    merged = merged.merge(
        payments[["order_id", "payment_method", "payment_status", "paid_at"]],
        on="order_id",
        how="left",
        validate="1:1",
        indicator="_merge_payment",
    )

    for label, column, key in [
        ("customer", "_merge_customer", "customer_id"),
        ("product", "_merge_product", "product_id"),
        ("payment", "_merge_payment", "order_id"),
    ]:
        matched = int((merged[column] == "both").sum())
        unmatched = len(merged) - matched
        distinct_unmatched = int(merged.loc[merged[column] != "both", key].nunique())
        dq.add(
            "5.4 integrate",
            f"merge_{label}",
            f"จับคู่ {key} กับ master ได้/ไม่ได้",
            rows_before=len(merged),
            rows_after=matched,
            rows_affected=unmatched,
            action=f"pd.merge(how='left', validate=..., indicator='{column}')",
            note=f"matched={matched}, unmatched={unmatched}, คีย์ที่ไม่พบ {distinct_unmatched} ค่า",
        )
        if verbose:
            print(
                f"merge {label:8s}: matched={matched:4d}  unmatched={unmatched:3d}"
                f"  (คีย์ไม่พบ {distinct_unmatched} ค่า)"
            )

    price_gap = int(
        (
            merged["standard_price"].notna()
            & merged["unit_price"].notna()
            & (merged["standard_price"] != merged["unit_price"])
        ).sum()
    )
    dq.add(
        "5.4 integrate",
        "price_vs_standard_price",
        "คำสั่งซื้อที่ unit_price ไม่เท่ากับราคาอ้างอิงใน master",
        rows_before=len(merged),
        rows_after=len(merged),
        rows_affected=price_gap,
        action="บันทึกอย่างเดียว ไม่แก้ไข",
        note="ยอดขายใช้ unit_price ที่ขายจริงตามกติกาข้อ 4.5",
    )
    return merged


def apply_business_rules(
    merged: pd.DataFrame, dq: DataQualityLog, rejects: RejectStore, verbose: bool = True
) -> tuple[pd.DataFrame, dict[str, int]]:
    """ตรวจกติกาทางธุรกิจทีละข้อ ทุกแถวที่ถูกคัดออกต้องมี reason_code"""
    df = merged.copy()
    stage_counts: dict[str, int] = {}

    value_rules = [
        ("INVALID_ORDER_DATE", "order_date แปลงเป็นวันที่ไม่ได้", "order_date ต้องเป็นวันที่ที่ถูกต้อง"),
        ("MISSING_QUANTITY", "quantity ว่าง", "กติกาข้อ 4.2 quantity > 0"),
        ("MISSING_UNIT_PRICE", "unit_price ว่าง", "กติกาข้อ 4.2 unit_price > 0"),
        ("QTY_NOT_POSITIVE", "quantity <= 0", "กติกาข้อ 4.2 quantity > 0"),
        ("PRICE_NOT_POSITIVE", "unit_price <= 0", "กติกาข้อ 4.2 unit_price > 0"),
        ("DISCOUNT_OUT_OF_RANGE", "discount อยู่นอกช่วง 0-1 หรือว่าง", "กติกาข้อ 4.2 0 <= discount <= 1"),
    ]
    for reason, metric, note in value_rules:
        if reason == "INVALID_ORDER_DATE":
            mask = df["order_date"].isna()
        elif reason == "MISSING_QUANTITY":
            mask = df["quantity"].isna()
        elif reason == "MISSING_UNIT_PRICE":
            mask = df["unit_price"].isna()
        elif reason == "QTY_NOT_POSITIVE":
            mask = df["quantity"].astype("float") <= 0
        elif reason == "PRICE_NOT_POSITIVE":
            mask = df["unit_price"] <= 0
        else:
            mask = df["discount"].isna() | (df["discount"] < 0) | (df["discount"] > 1)
        mask = mask.fillna(False).astype(bool)

        before = len(df)
        rejects.add(df[mask], reason, "5.5 business rules")
        df = df[~mask].copy()
        dq.add(
            "5.5 validate",
            reason.lower(),
            metric,
            rows_before=before,
            rows_after=len(df),
            rows_affected=before - len(df),
            action="คัดออกจาก fact และบันทึกใน rejected_rows.csv",
            note=note,
        )
    stage_counts["ค่าถูกต้องตามกติกา"] = len(df)

    for reason, metric, column, note in [
        (
            "CUSTOMER_NOT_IN_MASTER",
            "customer_id ไม่พบใน CRM",
            "_merge_customer",
            "กติกาข้อ 4.3 ลูกค้าต้องพบใน Master Data",
        ),
        (
            "PRODUCT_NOT_IN_MASTER",
            "product_id ไม่พบใน product master",
            "_merge_product",
            "กติกาข้อ 4.3 สินค้าต้องพบใน Master Data",
        ),
    ]:
        mask = (df[column] != "both").astype(bool)
        before = len(df)
        rejects.add(df[mask], reason, "5.5 referential integrity")
        df = df[~mask].copy()
        dq.add(
            "5.5 validate",
            reason.lower(),
            metric,
            rows_before=before,
            rows_after=len(df),
            rows_affected=before - len(df),
            action="คัดออกจาก fact และบันทึกใน rejected_rows.csv",
            note=note,
        )
    stage_counts["จับคู่ master ได้"] = len(df)

    mask = (df["_merge_payment"] != "both").astype(bool)
    before = len(df)
    rejects.add(df[mask], "PAYMENT_MISSING", "5.5 payment")
    df = df[~mask].copy()
    dq.add(
        "5.5 validate",
        "payment_missing",
        "ไม่มีเหตุการณ์ชำระเงินของ order นี้",
        rows_before=before,
        rows_after=len(df),
        rows_affected=before - len(df),
        action="คัดออกจาก fact",
        note="กติกาข้อ 4.4 นับเป็นยอดขายเมื่อ payment.status = PAID",
    )

    mask = (df["payment_status"] != ONLY_PAID_STATUS).astype(bool)
    before = len(df)
    rejects.add(df[mask], "PAYMENT_NOT_PAID", "5.5 payment")
    not_paid_mix = df.loc[mask, "payment_status"].value_counts().to_dict()
    df = df[~mask].copy()
    dq.add(
        "5.5 validate",
        "payment_not_paid",
        "สถานะการชำระเงินไม่ใช่ PAID",
        rows_before=before,
        rows_after=len(df),
        rows_affected=before - len(df),
        action="คัดออกจาก fact",
        note=" | ".join(f"{k}={v}" for k, v in sorted(not_paid_mix.items())) or "ไม่มี",
    )
    stage_counts["ชำระเงินสำเร็จ (fact)"] = len(df)

    if verbose:
        print(f"\nแถวที่ผ่านกติกาทั้งหมด: {len(df)} จาก {len(merged)} แถวที่เข้ามา")
    return df.reset_index(drop=True), stage_counts


# ---------------------------------------------------------------- 5.5 Load


def build_dimensions(
    customers: pd.DataFrame, products: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dim_customer = customers.copy().reset_index(drop=True)
    dim_customer.insert(0, "customer_key", range(1, len(dim_customer) + 1))
    dim_customer = dim_customer[
        ["customer_key", "customer_id", "full_name", "email", "province", "signup_date"]
    ]

    dim_product = products.copy().reset_index(drop=True)
    dim_product.insert(0, "product_key", range(1, len(dim_product) + 1))
    dim_product = dim_product[
        ["product_key", "product_id", "product_name", "category", "standard_price", "active_flag"]
    ]
    return dim_customer, dim_product


def build_fact(
    valid: pd.DataFrame, dim_customer: pd.DataFrame, dim_product: pd.DataFrame
) -> pd.DataFrame:
    """คำนวณ net_sales = quantity x unit_price x (1 - discount) แล้วต่อ surrogate key"""
    fact = valid.merge(
        dim_customer[["customer_key", "customer_id"]],
        on="customer_id",
        how="left",
        validate="m:1",
    ).merge(
        dim_product[["product_key", "product_id"]],
        on="product_id",
        how="left",
        validate="m:1",
    )
    quantity = fact["quantity"].astype("float")
    fact["gross_sales"] = (quantity * fact["unit_price"]).round(2)
    fact["net_sales"] = (quantity * fact["unit_price"] * (1 - fact["discount"])).round(2)
    columns = [
        "order_id",
        "order_date",
        "customer_key",
        "product_key",
        "quantity",
        "unit_price",
        "discount",
        "gross_sales",
        "net_sales",
        "payment_method",
        "payment_status",
        "paid_at",
        "channel",
        "source_file",
    ]
    return fact[columns].sort_values("order_id").reset_index(drop=True)


# ---------------------------------------------------------------- 5.6 Analyze


def _summarize(joined: pd.DataFrame, group_column: str) -> pd.DataFrame:
    summary = (
        joined.groupby(group_column, as_index=False)
        .agg(
            orders=("order_id", "count"),
            units=("quantity", "sum"),
            net_sales=("net_sales", "sum"),
        )
        .sort_values("net_sales", ascending=False)
        .reset_index(drop=True)
    )
    summary["units"] = summary["units"].astype("int64")
    summary["net_sales"] = summary["net_sales"].round(2)
    summary["avg_order_value"] = (summary["net_sales"] / summary["orders"]).round(2)
    total = summary["net_sales"].sum()
    summary["share_pct"] = (summary["net_sales"] / total * 100).round(2)
    return summary


def summarize_by_province(fact: pd.DataFrame, dim_customer: pd.DataFrame) -> pd.DataFrame:
    joined = fact.merge(dim_customer[["customer_key", "province"]], on="customer_key", how="left")
    return _summarize(joined, "province")


def summarize_by_category(fact: pd.DataFrame, dim_product: pd.DataFrame) -> pd.DataFrame:
    joined = fact.merge(dim_product[["product_key", "category"]], on="product_key", how="left")
    return _summarize(joined, "category")


# ---------------------------------------------------------------- Challenge: validate_data


class DataValidationError(ValueError):
    """ยกขึ้นเมื่อ fact table ไม่ผ่านกฎคุณภาพข้อมูลข้อใดข้อหนึ่ง"""


def validate_data(
    df: pd.DataFrame,
    dim_customer: pd.DataFrame | None = None,
    dim_product: pd.DataFrame | None = None,
) -> bool:
    """ตรวจ uniqueness, referential integrity และค่าที่อยู่นอกช่วง

    เก็บทุกข้อที่ไม่ผ่านแล้วค่อย raise ทีเดียว เพื่อให้เห็นปัญหาครบในรอบเดียว
    """
    failures: list[str] = []

    duplicate_orders = int(df["order_id"].duplicated().sum())
    if duplicate_orders:
        failures.append(f"order_id ซ้ำ {duplicate_orders} แถว (ต้องไม่ซ้ำเลย)")
    if int(df["order_id"].isna().sum()):
        failures.append("order_id มีค่าว่าง")

    if dim_customer is not None:
        orphan = int((~df["customer_key"].isin(dim_customer["customer_key"])).sum())
        if orphan:
            failures.append(f"customer_key ไม่พบใน dim_customer {orphan} แถว")
    if dim_product is not None:
        orphan = int((~df["product_key"].isin(dim_product["product_key"])).sum())
        if orphan:
            failures.append(f"product_key ไม่พบใน dim_product {orphan} แถว")

    range_checks = [
        ("quantity > 0", df["quantity"].astype("float") <= 0),
        ("unit_price > 0", df["unit_price"] <= 0),
        ("0 <= discount <= 1", (df["discount"] < 0) | (df["discount"] > 1)),
        ("net_sales >= 0", df["net_sales"] < 0),
        ("net_sales <= gross_sales", df["net_sales"] > df["gross_sales"] + 0.01),
    ]
    for rule, mask in range_checks:
        bad = int(mask.fillna(True).sum())
        if bad:
            failures.append(f"ผิดกฎ {rule} จำนวน {bad} แถว")

    if bool((df["payment_status"] != ONLY_PAID_STATUS).any()):
        failures.append("มีแถวที่ payment_status ไม่ใช่ PAID อยู่ใน fact")

    recomputed = (
        df["quantity"].astype("float") * df["unit_price"] * (1 - df["discount"])
    ).round(2)
    mismatch = int((recomputed - df["net_sales"]).abs().gt(0.01).sum())
    if mismatch:
        failures.append(f"net_sales ไม่ตรงกับสูตร {mismatch} แถว")

    if failures:
        raise DataValidationError(
            f"fact_sales ไม่ผ่านการตรวจสอบ {len(failures)} ข้อ:\n  - " + "\n  - ".join(failures)
        )
    return True


# ---------------------------------------------------------------- Challenge: กราฟ (ขาว-ดำ)


def _setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["Leelawadee UI", "Tahoma", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"
    plt.rcParams["text.color"] = "black"
    plt.rcParams["axes.labelcolor"] = "black"
    plt.rcParams["xtick.color"] = "black"
    plt.rcParams["ytick.color"] = "black"
    return plt


def plot_funnel(stages: dict[str, int], path: Path) -> Path:
    """กราฟ funnel ขาว-ดำ: raw -> deduplicated -> valid -> matched -> paid"""
    plt = _setup_matplotlib()
    labels = list(stages.keys())
    values = list(stages.values())
    base = values[0] if values else 1

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    positions = list(range(len(labels)))
    ax.barh(positions, values, color="#d0d0d0", edgecolor="black", height=0.62)
    for i, value in enumerate(values):
        ax.text(
            value + base * 0.012,
            i,
            f"{value:,} แถว ({value / base * 100:.1f}%)",
            va="center",
            fontsize=10,
            color="black",
        )
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, base * 1.32)
    ax.set_xlabel("จำนวนแถว")
    ax.set_title("Data Quality Funnel — จากข้อมูลดิบสู่ยอดขายที่ใช้ได้จริง", fontsize=12)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path


def plot_before_after(metrics: list[tuple[str, int, int]], path: Path) -> Path:
    """กราฟแท่งขาว-ดำเทียบปัญหาคุณภาพข้อมูลก่อนและหลัง Data Integration"""
    plt = _setup_matplotlib()
    labels = [m[0] for m in metrics]
    before = [m[1] for m in metrics]
    after = [m[2] for m in metrics]
    positions = list(range(len(labels)))
    width = 0.38
    headroom = max(before + [1]) * 0.02

    fig, ax = plt.subplots(figsize=(10, 5.4))
    bars_before = ax.bar(
        [p - width / 2 for p in positions], before, width,
        label="ก่อน Integration", color="#bfbfbf", edgecolor="black",
    )
    bars_after = ax.bar(
        [p + width / 2 for p in positions], after, width,
        label="หลัง Integration", color="#3d3d3d", edgecolor="black",
    )
    for bars in (bars_before, bars_after):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + headroom,
                f"{int(bar.get_height())}",
                ha="center",
                fontsize=9,
                color="black",
            )
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=9, rotation=18, ha="right")
    ax.set_ylabel("จำนวนแถวที่มีปัญหา")
    ax.set_title("คุณภาพข้อมูลก่อนและหลัง Data Integration", fontsize=12)
    ax.legend(frameon=False)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- คำตอบคำถามวิเคราะห์


def answer_questions(
    raw_rows: int,
    orders: pd.DataFrame,
    merged: pd.DataFrame,
    fact: pd.DataFrame,
    by_province: pd.DataFrame,
    by_category: pd.DataFrame,
    verbose: bool = True,
) -> dict[str, str]:
    unmatched_customer = int((merged["_merge_customer"] != "both").sum())
    unmatched_product = int((merged["_merge_product"] != "both").sum())
    top_province = by_province.iloc[0]
    top_category = by_category.iloc[0]

    answers = {
        "q1": (
            f"หลัง concat ได้ {raw_rows} แถว และเหลือ {len(orders)} แถวหลังลบ order_id ซ้ำ "
            f"(ลบไป {raw_rows - len(orders)} แถว ตามกติกา keep='last')"
        ),
        "q2": (
            f"customer_id ที่ไม่พบใน CRM มี {unmatched_customer} แถว และ product_id ที่ไม่พบใน "
            f"product master มี {unmatched_product} แถว (นับจาก indicator ของ merge "
            "บนข้อมูลที่ลบซ้ำแล้ว)"
        ),
        "q3": (
            f"ยอดขายที่ใช้ได้จริง {len(fact)} ธุรกรรม ยอดขายสุทธิรวม "
            f"{fact['net_sales'].sum():,.2f} บาท"
        ),
        "q4": (
            f"{top_province['province']} มียอดขายสุทธิสูงสุด {top_province['net_sales']:,.2f} บาท "
            f"({top_province['share_pct']}% ของทั้งหมด จาก {int(top_province['orders'])} ธุรกรรม)"
        ),
        "q5": (
            f"หมวด {top_category['category']} มียอดขายสุทธิสูงสุด "
            f"{top_category['net_sales']:,.2f} บาท ({top_category['share_pct']}% จาก "
            f"{int(top_category['orders'])} ธุรกรรม)"
        ),
        "q6": (
            "ถ้า merge ก่อน cleaning ผลจะเพี้ยนและเชื่อถือไม่ได้ — CRM มี customer_id ซ้ำ 3 รายการ "
            "ทำให้ pd.merge(validate='m:1') โยน MergeError ทันที และถ้าไม่ใส่ validate= แถวคำสั่งซื้อ "
            "จะถูกคูณซ้ำจนยอดขายเกินจริง; order_id ที่ยังซ้ำอยู่จะถูกนับยอดสองครั้ง; discount ของเดือน "
            "ก.พ. ที่ยังเป็นสตริง '5%' จะคำนวณ net_sales ไม่ได้เลย; และชื่อจังหวัดที่ยังไม่ทำมาตรฐาน "
            "จะกระจายเป็นหลายกลุ่ม (Bangkok / กทม. / กรุงเทพมหานคร แยกกัน) ทำให้สรุปยอดรายจังหวัดผิด "
            "สรุปคือ cleaning ต้องมาก่อน merge เสมอ"
        ),
    }
    if verbose:
        print("\n" + "=" * 78)
        print("5.6 ANALYZE — คำตอบคำถามวิเคราะห์ 6 ข้อ")
        print("=" * 78)
        print("\nยอดขายสุทธิแยกตามจังหวัด")
        print(by_province.to_string(index=False))
        print("\nยอดขายสุทธิแยกตามหมวดสินค้า")
        print(by_category.to_string(index=False))
        print()
        for key in sorted(answers):
            print(f"{key.upper()}: {answers[key]}\n")
    return answers


# ---------------------------------------------------------------- orchestration


def run(verbose: bool = True) -> dict:
    OUTPUT.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)

    dq = DataQualityLog()
    rejects = RejectStore()

    # ---- 5.1 Extract & profile
    raw = extract(verbose=verbose)
    profiles = {
        "orders_2026_01.csv": profile(raw["orders_jan"], "orders_2026_01.csv", "order_id", verbose),
        "orders_2026_02.csv": profile(raw["orders_feb"], "orders_2026_02.csv", "order_id", verbose),
        "customers_crm.csv": profile(raw["customers"], "customers_crm.csv", "customer_id", verbose),
        "product_master.xlsx": profile(
            raw["products"], "product_master.xlsx", "product_id", verbose
        ),
        "payments.json": profile(raw["payments"], "payments.json", "payment_id", verbose),
    }
    for name, info in profiles.items():
        dq.add(
            "5.1 profile",
            "raw_profile",
            f"สำรวจไฟล์ {name}",
            rows_before=info["rows"],
            rows_after=info["rows"],
            rows_affected=info["duplicate_key"],
            action="อ่านอย่างเดียว ยังไม่แก้ไข",
            note=(
                f"{info['columns']} คอลัมน์ | ค่าว่างรวม {info['missing_total']} | "
                f"แถวซ้ำทั้งแถว {info['duplicate_rows']} | คีย์ซ้ำ {info['duplicate_key']}"
            ),
        )

    # ---- 5.2 Combine
    if verbose:
        print("\n" + "=" * 78)
        print("5.2 COMBINE ORDERS — schema alignment + concat")
        print("=" * 78)
        print(f"คอลัมน์ ม.ค.: {list(raw['orders_jan'].columns)}")
        print(f"คอลัมน์ ก.พ.: {list(raw['orders_feb'].columns)}")
        print(f"rename ที่ใช้: {FEB_RENAME}")
    combined = combine_orders(raw["orders_jan"], raw["orders_feb"], dq)
    raw_rows = len(combined)
    if verbose:
        print(f"รวมแล้วได้ {raw_rows} แถว")

    # ---- 5.3 Transform
    if verbose:
        print("\n" + "=" * 78)
        print("5.3 TRANSFORM — แปลงชนิดข้อมูล ทำมาตรฐาน และลบข้อมูลซ้ำ")
        print("=" * 78)
    orders = clean_orders(combined, dq, rejects)
    customers = clean_customers(raw["customers"], dq)
    products = clean_products(raw["products"], dq)
    payments = clean_payments(raw["payments"], dq)
    if verbose:
        print(f"orders   : {raw_rows} -> {len(orders)} แถว (ลบ order_id ซ้ำ)")
        print(f"customers: {len(raw['customers'])} -> {len(customers)} แถว")
        print(f"products : {len(raw['products'])} -> {len(products)} แถว")
        print(f"payments : {len(raw['payments'])} -> {len(payments)} แถว")
        print(f"จังหวัดหลังทำมาตรฐาน: {sorted(customers['province'].unique())}")

    # ---- 5.4 Integrate & validate
    if verbose:
        print("\n" + "=" * 78)
        print("5.4 INTEGRATE & VALIDATE — merge พร้อม validate= และ indicator=")
        print("=" * 78)
    merged = integrate(orders, customers, products, payments, dq, verbose=verbose)
    valid, stage_counts = apply_business_rules(merged, dq, rejects, verbose=verbose)

    # ---- 5.5 Load
    dim_customer, dim_product = build_dimensions(customers, products)
    fact = build_fact(valid, dim_customer, dim_product)
    validate_data(fact, dim_customer, dim_product)

    # ---- 5.6 Analyze
    by_province = summarize_by_province(fact, dim_customer)
    by_category = summarize_by_category(fact, dim_product)

    dq.add(
        "5.5 load",
        "fact_sales",
        "แถวใน fact_sales",
        rows_before=raw_rows,
        rows_after=len(fact),
        rows_affected=raw_rows - len(fact),
        action="net_sales = quantity x unit_price x (1 - discount)",
        note=f"ยอดขายสุทธิรวม {fact['net_sales'].sum():,.2f} บาท",
    )
    dq.add(
        "5.5 load",
        "dim_customer",
        "แถวใน dim_customer",
        rows_before=len(raw["customers"]),
        rows_after=len(dim_customer),
        rows_affected=len(raw["customers"]) - len(dim_customer),
        action="surrogate key customer_key",
    )
    dq.add(
        "5.5 load",
        "dim_product",
        "แถวใน dim_product",
        rows_before=len(raw["products"]),
        rows_after=len(dim_product),
        rows_affected=len(raw["products"]) - len(dim_product),
        action="surrogate key product_key",
    )
    dq.add(
        "Challenge",
        "validate_data",
        "ตรวจ uniqueness / referential integrity / ค่านอกช่วง",
        rows_before=len(fact),
        rows_after=len(fact),
        rows_affected=0,
        action="ผ่านทุกข้อ",
        note="ถ้าไม่ผ่าน ฟังก์ชันจะ raise DataValidationError และ pipeline หยุดทันที",
    )

    dq_report = dq.to_frame()
    rejected = rejects.to_frame()

    # ---- เขียนผลลัพธ์
    dim_customer.to_csv(OUTPUT / "dim_customer.csv", index=False, encoding="utf-8-sig")
    dim_product.to_csv(OUTPUT / "dim_product.csv", index=False, encoding="utf-8-sig")
    fact.to_csv(OUTPUT / "fact_sales.csv", index=False, encoding="utf-8-sig")
    dq_report.to_csv(OUTPUT / "data_quality_report.csv", index=False, encoding="utf-8-sig")
    by_province.to_csv(OUTPUT / "summary_by_province.csv", index=False, encoding="utf-8-sig")
    by_category.to_csv(OUTPUT / "summary_by_category.csv", index=False, encoding="utf-8-sig")
    rejected.to_csv(OUTPUT / "rejected_rows.csv", index=False, encoding="utf-8-sig")

    # ---- กราฟ (ขาว-ดำ)
    funnel_stages = {
        "ข้อมูลดิบ 2 เดือน (raw)": raw_rows,
        "หลังลบ order_id ซ้ำ": len(orders),
        **stage_counts,
    }
    plot_funnel(funnel_stages, FIGURES / "dq_funnel.png")

    raw_customers = raw["customers"]
    raw_email = raw_customers["email"].astype("string")
    email_bad = int((raw_email.notna() & (raw_email != raw_email.str.strip().str.lower())).sum())
    province_bad = int(
        (
            normalize_text(raw_customers["province"]).fillna("")
            != standardize_province(raw_customers["province"]).fillna("")
        ).sum()
    )
    reject_counts = rejected["reason_code"].value_counts().to_dict() if not rejected.empty else {}
    before_after = [
        ("order_id ซ้ำ", reject_counts.get("DUPLICATE_ORDER_ID", 0), 0),
        ("unit_price ว่าง", reject_counts.get("MISSING_UNIT_PRICE", 0), 0),
        ("quantity <= 0", reject_counts.get("QTY_NOT_POSITIVE", 0), 0),
        ("customer_id ซ้ำใน CRM", len(raw_customers) - len(customers), 0),
        ("email ไม่เป็นมาตรฐาน", email_bad, 0),
        ("จังหวัดไม่เป็นมาตรฐาน", province_bad, 0),
        (
            "อ้าง master ไม่ได้",
            reject_counts.get("CUSTOMER_NOT_IN_MASTER", 0)
            + reject_counts.get("PRODUCT_NOT_IN_MASTER", 0),
            0,
        ),
        (
            "ชำระเงินไม่สำเร็จ/ไม่มี",
            reject_counts.get("PAYMENT_NOT_PAID", 0) + reject_counts.get("PAYMENT_MISSING", 0),
            0,
        ),
    ]
    plot_before_after(before_after, FIGURES / "dq_before_after.png")

    answers = answer_questions(
        raw_rows=raw_rows,
        orders=orders,
        merged=merged,
        fact=fact,
        by_province=by_province,
        by_category=by_category,
        verbose=verbose,
    )

    summary = {
        "raw_rows": raw_rows,
        "rows_after_dedup": len(orders),
        "funnel": funnel_stages,
        "before_after": [{"metric": m, "before": b, "after": a} for m, b, a in before_after],
        "reject_counts": reject_counts,
        "fact_rows": len(fact),
        "net_sales_total": round(float(fact["net_sales"].sum()), 2),
        "gross_sales_total": round(float(fact["gross_sales"].sum()), 2),
        "unmatched_customer_rows": int((merged["_merge_customer"] != "both").sum()),
        "unmatched_product_rows": int((merged["_merge_product"] != "both").sum()),
        "province_before_variants": int(raw_customers["province"].nunique()),
        "province_normalized_variants": int(normalize_text(raw_customers["province"]).nunique()),
        "province_after": sorted(customers["province"].unique().tolist()),
        "dim_customer_rows": len(dim_customer),
        "dim_product_rows": len(dim_product),
        "raw_profiles": profiles,
        "answers": answers,
    }
    with open(OUTPUT / "kpi_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2, default=str)

    if verbose:
        print("\n" + "=" * 78)
        print("เขียนไฟล์ผลลัพธ์เรียบร้อย")
        print("=" * 78)
        for name in [
            "dim_customer.csv",
            "dim_product.csv",
            "fact_sales.csv",
            "data_quality_report.csv",
            "summary_by_province.csv",
            "summary_by_category.csv",
            "rejected_rows.csv",
            "kpi_summary.json",
        ]:
            print(f"  output/{name}")
        print("  figures/dq_funnel.png")
        print("  figures/dq_before_after.png")

    return {
        "raw": raw,
        "orders": orders,
        "customers": customers,
        "products": products,
        "payments": payments,
        "merged": merged,
        "valid": valid,
        "dim_customer": dim_customer,
        "dim_product": dim_product,
        "fact": fact,
        "dq_report": dq_report,
        "rejected": rejected,
        "by_province": by_province,
        "by_category": by_category,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Week08 Data Integration Pipeline")
    parser.add_argument("--quiet", action="store_true", help="ไม่พิมพ์ profile และผลลัพธ์ยาว ๆ")
    args = parser.parse_args(argv)
    run(verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
