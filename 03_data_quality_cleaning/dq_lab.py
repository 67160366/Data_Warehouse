"""Data Quality & Data Cleaning Lab (Week 5)
=============================================
Data Refinery: ทำความสะอาด e_commerce_raw.csv ก่อนโหลดเข้า Data Warehouse

หลักการสำคัญ
------------
1. สร้าง flag "ก่อน" แก้ค่าทุกครั้ง เพื่อให้ตรวจย้อนหลังได้ (auditability)
2. ห้าม drop แถวเพราะข้อมูลบางคอลัมน์หาย -> Fact row และยอดขายจะสูญหาย
3. ห้ามแก้ Outlier โดยอัตโนมัติ ต้องพิจารณา Is_Promotion และ business context
4. ทุก mapping มี coverage assert ถ้าเจอค่าที่ไม่รู้จักจะ error ทันที ไม่เงียบกลายเป็น Unknown

รัน: python dq_lab.py
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

# ไม่ตั้ง backend ตอน import เพราะ notebook ที่ import ไฟล์นี้ต้องใช้ backend inline ของตัวเอง
# script จะสลับไปใช้ Agg ใน main() ก่อนวาดกราฟลงไฟล์

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FIG_DIR = BASE_DIR / "figures"

RAW_PATH = DATA_DIR / "e_commerce_raw.csv"
REF_PATH = DATA_DIR / "customer_reference.csv"
CLEAN_PATH = DATA_DIR / "e_commerce_clean.csv"
REPORT_PATH = DATA_DIR / "data_quality_report.csv"
BOXPLOT_BEFORE = FIG_DIR / "boxplot_before.png"
BOXPLOT_AFTER = FIG_DIR / "boxplot_after.png"

ENCODING = "utf-8-sig"  # ไฟล์ต้นทางมี BOM และ output ต้องเปิดใน Excel ภาษาไทยได้

VALID_GENDER = {"M", "F", "Unknown"}
VALID_PAYMENT = {"Credit Card", "PromptPay", "Cash on Delivery", "Bank Transfer", "Unknown"}
VALID_STATUS = {"Completed", "Processing", "Cancelled", "Returned", "Unknown"}
QUANTITY_MIN, QUANTITY_MAX = 1, 20
TIMELINESS_SLA_HOURS = 24


def banner(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def step(text: str) -> None:
    print(f"\n--- {text}")


# ---------------------------------------------------------------------------
# Task 1 - Data Profiling
# ---------------------------------------------------------------------------
def task1_profiling(df: pd.DataFrame) -> dict:
    banner("TASK 1 - DATA PROFILING")

    step("รูปร่างข้อมูล")
    print(f"rows = {df.shape[0]}, columns = {df.shape[1]}")

    step("ชนิดข้อมูลและ non-null count (df.info())")
    df.info()

    step("ตัวอย่างข้อมูล 5 แถวแรก (df.head())")
    print(df.head(5).to_string())

    step("Missing values รายคอลัมน์ (df.isnull().sum())")
    nulls = df.isnull().sum()
    print(nulls[nulls > 0].to_string() if nulls.any() else "ไม่พบ missing values")

    step("สถิติเชิงพรรณนา (df.describe(include='all').T)")
    print(df.describe(include="all").T.to_string())

    step("Exact duplicates (df.duplicated().sum())")
    n_exact_dup = int(df.duplicated().sum())
    n_dup_key = int(df["Transaction_ID"].duplicated().sum())
    print(f"แถวซ้ำทั้งแถว = {n_exact_dup} | Transaction_ID ซ้ำ = {n_dup_key}")

    step("ความหลากหลายของค่าในคอลัมน์ categorical (ที่มาของปัญหา Consistency)")
    for col in ["Gender", "Payment_Method", "Order_Status", "Is_Promotion"]:
        vals = df[col].value_counts(dropna=False)
        print(f"\n[{col}] มี {vals.size} ค่าที่แตกต่างกัน")
        print(vals.to_string())

    step("รูปแบบของ Order_Date")
    print(_date_format_breakdown(df["Order_Date"]).to_string())

    step("ค่าที่ผิดกฎธุรกิจ")
    qty_bad = int((~df["Quantity"].between(QUANTITY_MIN, QUANTITY_MAX)).sum())
    amt_neg = int((df["Transaction_Amount"] < 0).sum())
    print(f"Quantity นอกช่วง {QUANTITY_MIN}-{QUANTITY_MAX} = {qty_bad} แถว "
          f"(min={df['Quantity'].min()}, max={df['Quantity'].max()})")
    print(f"Transaction_Amount ติดลบ = {amt_neg} แถว "
          f"(min={df['Transaction_Amount'].min():,.2f}, max={df['Transaction_Amount'].max():,.2f})")

    step("สรุปปัญหาที่พบ จับคู่กับ 6 มิติของ Data Quality")
    issues = pd.DataFrame(
        [
            ("Completeness", "Customer_Email ว่าง",
             f"{int(nulls.get('Customer_Email', 0))} แถว", "เติมจาก reference แล้ว fallback unknown + ติด flag"),
            ("Completeness", "Province ว่าง",
             f"{int(nulls.get('Province', 0))} แถว", "เติมจาก reference แล้ว fallback 'Unknown' + ติด flag"),
            ("Consistency", "Gender เขียนหลายรูปแบบ",
             f"{df['Gender'].nunique(dropna=False)} รูปแบบ", "map เป็น M / F / Unknown"),
            ("Consistency", "Payment_Method เขียนหลายรูปแบบ",
             f"{df['Payment_Method'].nunique(dropna=False)} รูปแบบ", "map เป็น 4 ค่ามาตรฐาน + Unknown"),
            ("Consistency", "Order_Date หลายรูปแบบ / กำกวม DD-MM vs MM-DD",
             "4 รูปแบบ + ค่าที่ไม่ใช่วันที่", "parse รายแถว ใช้ Load_Timestamp ตัดสิน + เก็บวิธี parse"),
            ("Uniqueness", "แถวซ้ำทั้งแถว",
             f"{n_exact_dup} แถว", "drop_duplicates(keep='first')"),
            ("Uniqueness", "ลูกค้าคนเดียวกันแต่ชื่อเขียนต่างกัน",
             "ตรวจใน Task 4", "รายงานเป็น near duplicate ไม่ลบอัตโนมัติ"),
            ("Validity", "Quantity นอกช่วง 1-20",
             f"{qty_bad} แถว", "ติด flag แล้ว clip เข้าช่วง"),
            ("Validity", "Order_Status ค่าไม่อยู่ในชุดที่กำหนด",
             "done / Cancel / unknown_status", "standardize + ติด flag"),
            ("Accuracy", "Transaction_Amount ไม่ตรงสูตร Qty x Price x (1-Disc)",
             "ตรวจใน Task 5", "ติด Accuracy_Flag ไม่แก้ยอดอัตโนมัติ"),
            ("Accuracy", "ยอดผิดปกติ / ติดลบ / ค่า sentinel 999999",
             f"ติดลบ {amt_neg} แถว", "IQR capping เฉพาะรายการที่ไม่ใช่โปรโมชัน"),
            ("Timeliness", "ข้อมูลเข้า Warehouse ช้ากว่า SLA 24 ชม.",
             "ตรวจใน Task 7", "คำนวณ Load_Delay_Hours + ติดป้าย Late"),
        ],
        columns=["มิติ Data Quality", "ปัญหาที่พบ", "ขนาดของปัญหา", "แนวทางจัดการ"],
    )
    print(issues.to_string(index=False))

    return {
        "rows_raw": int(df.shape[0]),
        "missing_email_before": int(nulls.get("Customer_Email", 0)),
        "missing_province_before": int(nulls.get("Province", 0)),
        "exact_duplicates_before": n_exact_dup,
        "distinct_gender_before": int(df["Gender"].nunique(dropna=False)),
        "distinct_payment_before": int(df["Payment_Method"].nunique(dropna=False)),
        "distinct_status_before": int(df["Order_Status"].nunique(dropna=False)),
        "invalid_quantity_before": qty_bad,
        "negative_amount_before": amt_neg,
        "total_amount_before": float(df["Transaction_Amount"].sum()),
    }


ISO_DATE_RE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
AMBIGUOUS_DATE_RE = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$")


def _date_format_breakdown(series: pd.Series) -> pd.Series:
    """จัดกลุ่มรูปแบบข้อความของวันที่ เพื่อดูว่าต้อง parse กี่แบบ"""
    text = series.astype("string").fillna("<NA>")
    labels = pd.Series("OTHER (ไม่ใช่วันที่)", index=text.index)
    labels[text.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)] = "YYYY-MM-DD"
    labels[text.str.match(r"^\d{4}/\d{2}/\d{2}$", na=False)] = "YYYY/MM/DD"
    labels[text.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)] = "xx/xx/YYYY (กำกวม)"
    labels[text.str.match(r"^\d{2}-\d{2}-\d{4}$", na=False)] = "xx-xx-YYYY (กำกวม)"
    return labels.value_counts()


# ---------------------------------------------------------------------------
# Task 2 - Completeness
# ---------------------------------------------------------------------------
def task2_completeness(df: pd.DataFrame, ref: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    banner("TASK 2 - COMPLETENESS")
    df = df.copy()

    # 1) ติด flag ก่อนแก้ค่า มิฉะนั้นจะไม่รู้ว่าค่าไหนเป็นของจริงและค่าไหนถูกเติม
    df["Customer_Email_Was_Missing"] = df["Customer_Email"].isna()
    df["Province_Was_Missing"] = df["Province"].isna()
    n_email_missing = int(df["Customer_Email_Was_Missing"].sum())
    n_province_missing = int(df["Province_Was_Missing"].sum())
    step("ติด flag ก่อนแก้ค่า")
    print(f"Customer_Email_Was_Missing = {n_email_missing} แถว")
    print(f"Province_Was_Missing       = {n_province_missing} แถว")

    step("ผลกระทบถ้า drop แถวที่ Customer_Email หาย (คำถามวิเคราะห์ข้อ 1)")
    lost_amount = float(df.loc[df["Customer_Email_Was_Missing"], "Transaction_Amount"].sum())
    total_amount = float(df["Transaction_Amount"].sum())
    print(f"ยอดขายที่จะสูญหาย = {lost_amount:,.2f} บาท จากทั้งหมด {total_amount:,.2f} บาท "
          f"({lost_amount / total_amount * 100:.2f}%) และเสีย Fact row ไป {n_email_missing} แถว")

    # 2) เติมจาก customer_reference.csv (conformed dimension) ก่อนใช้ค่า unknown
    assert not ref["Customer_ID"].duplicated().any(), "reference มี Customer_ID ซ้ำ merge จะขยายแถว"
    merged = df.merge(
        ref[["Customer_ID", "Customer_Email", "Province"]],
        on="Customer_ID", how="left", suffixes=("", "_ref"),
    )
    assert len(merged) == len(df), "จำนวนแถวเปลี่ยนหลัง merge"

    merged["Customer_Email_Filled_From_Reference"] = (
        merged["Customer_Email"].isna() & merged["Customer_Email_ref"].notna()
    )
    merged["Province_Filled_From_Reference"] = (
        merged["Province"].isna() & merged["Province_ref"].notna()
    )
    merged["Customer_Email"] = merged["Customer_Email"].fillna(merged["Customer_Email_ref"])
    merged["Province"] = merged["Province"].fillna(merged["Province_ref"])
    df = merged.drop(columns=["Customer_Email_ref", "Province_ref"])

    n_email_from_ref = int(df["Customer_Email_Filled_From_Reference"].sum())
    n_province_from_ref = int(df["Province_Filled_From_Reference"].sum())
    step("เติมจาก customer_reference.csv ตาม Customer_ID")
    print(f"Customer_Email เติมได้ {n_email_from_ref}/{n_email_missing} แถว")
    print(f"Province       เติมได้ {n_province_from_ref}/{n_province_missing} แถว")

    # 3) ที่เหลือใช้ค่า placeholder ที่ traceable กลับไปหาลูกค้าได้
    still_missing_email = df["Customer_Email"].isna()
    df.loc[still_missing_email, "Customer_Email"] = (
        "unknown_" + df.loc[still_missing_email, "Customer_ID"].astype(str) + "@unknown.local"
    )
    df["Province"] = df["Province"].fillna("Unknown")
    step("เติมค่าที่เหลือด้วย placeholder แบบ traceable")
    print(f"Customer_Email -> unknown_<Customer_ID>@unknown.local : {int(still_missing_email.sum())} แถว")
    if still_missing_email.any():
        print(df.loc[still_missing_email, ["Transaction_ID", "Customer_ID", "Customer_Email"]].to_string(index=False))
    print(f"Province -> 'Unknown' : {int(df['Province_Was_Missing'].sum()) - n_province_from_ref} แถว")

    assert df["Customer_Email"].notna().all(), "ยังมี Customer_Email ว่าง"
    assert df["Province"].notna().all(), "ยังมี Province ว่าง"
    assert len(df) == n_email_missing + int((~df["Customer_Email_Was_Missing"]).sum()), "จำนวนแถวเปลี่ยน"

    return df, {
        "sales_at_risk_if_dropped": lost_amount,
        "email_filled_from_reference": n_email_from_ref,
        "province_filled_from_reference": n_province_from_ref,
        "email_filled_unknown": int(still_missing_email.sum()),
    }


# ---------------------------------------------------------------------------
# Task 3 - Consistency
# ---------------------------------------------------------------------------
GENDER_MAP = {"m": "M", "male": "M", "f": "F", "female": "F"}
PAYMENT_MAP = {
    "credit card": "Credit Card", "creditcard": "Credit Card", "cc": "Credit Card", "card": "Credit Card",
    "promptpay": "PromptPay", "prompt pay": "PromptPay", "pp": "PromptPay",
    "cash on delivery": "Cash on Delivery", "cod": "Cash on Delivery", "cash": "Cash on Delivery",
    "bank transfer": "Bank Transfer", "transfer": "Bank Transfer", "banktransfer": "Bank Transfer",
}


def _normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .str.replace("_", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )


def _to_timestamp(year: int, month: int, day: int) -> pd.Timestamp | None:
    """คืน Timestamp เฉพาะเมื่อเป็นวันที่จริงตามปฏิทิน (2026-13-05 และ 31/02/2026 จะได้ None)"""
    try:
        return pd.Timestamp(year=year, month=month, day=day)
    except ValueError:
        return None


def resolve_order_date(raw_value, load_ts: pd.Timestamp) -> tuple[pd.Timestamp, str, bool]:
    """แปลง Order_Date หนึ่งค่า คืน (วันที่, วิธีที่ใช้, ถูก impute หรือไม่)

    ลำดับการตัดสิน
      1. รูปแบบ YYYY-MM-DD / YYYY/MM/DD ไม่กำกวมอยู่แล้ว
      2. รูปแบบ xx/xx/YYYY สร้าง candidate ทั้ง DD/MM และ MM/DD
         - ถ้ามีตัวเดียวที่เป็นวันจริง -> ตัดสินด้วยปฏิทิน
         - ถ้าเป็นวันจริงทั้งคู่ -> เลือกตัวที่ Load_Timestamp - Order_Date >= 0 และน้อยที่สุด
           (ข้อมูลจริงยืนยันว่า Load_Timestamp มาทีหลัง Order_Date เสมอ)
      3. อ่านไม่ได้เลย -> fallback เป็นวันของ Load_Timestamp และติด flag
    """
    text = "" if pd.isna(raw_value) else str(raw_value).strip()

    m = ISO_DATE_RE.match(text)
    if m:
        ts = _to_timestamp(int(m[1]), int(m[2]), int(m[3]))
        if ts is not None:
            return ts, "ISO_UNAMBIGUOUS", False

    m = AMBIGUOUS_DATE_RE.match(text)
    if m:
        first, second, year = int(m[1]), int(m[2]), int(m[3])
        candidates = {}
        if (ts := _to_timestamp(year, second, first)) is not None:
            candidates["DD/MM/YYYY"] = ts
        if (ts := _to_timestamp(year, first, second)) is not None:
            candidates["MM/DD/YYYY"] = ts

        if len(candidates) == 1:
            fmt, ts = next(iter(candidates.items()))
            return ts, f"RESOLVED_BY_CALENDAR ({fmt})", False
        if len(candidates) == 2:
            if candidates["DD/MM/YYYY"] == candidates["MM/DD/YYYY"]:
                return candidates["DD/MM/YYYY"], "IDENTICAL_EITHER_WAY", False
            plausible = {f: ts for f, ts in candidates.items() if load_ts >= ts}
            if plausible:
                fmt, ts = min(plausible.items(), key=lambda kv: load_ts - kv[1])
                return ts, f"RESOLVED_BY_LOAD_TS ({fmt})", False

    return load_ts.normalize(), "IMPUTED_FROM_LOAD_TS", True


def task3_consistency(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    banner("TASK 3 - CONSISTENCY")
    df = df.copy()

    step("Gender -> M / F / Unknown")
    print("ก่อน:", sorted(df["Gender"].dropna().unique().tolist()))
    df["Gender"] = _normalize_text(df["Gender"]).map(GENDER_MAP).fillna("Unknown")
    print("หลัง:", df["Gender"].value_counts().to_dict())
    unmapped = set(df["Gender"].unique()) - VALID_GENDER
    assert not unmapped, f"Gender มีค่าที่ไม่รู้จัก: {unmapped}"

    step("Payment_Method -> 4 ค่ามาตรฐาน + Unknown")
    print(f"ก่อน: {df['Payment_Method'].nunique(dropna=False)} รูปแบบ ->",
          sorted(df["Payment_Method"].dropna().unique().tolist()))
    normalized_payment = _normalize_text(df["Payment_Method"])
    unknown_payment = set(normalized_payment.dropna().unique()) - set(PAYMENT_MAP)
    assert not unknown_payment, f"Payment_Method มีค่าที่ mapping ยังไม่ครอบคลุม: {unknown_payment}"
    df["Payment_Method"] = normalized_payment.map(PAYMENT_MAP).fillna("Unknown")
    print("หลัง:", df["Payment_Method"].value_counts().to_dict())
    assert not set(df["Payment_Method"].unique()) - VALID_PAYMENT

    step("Order_Date -> YYYY-MM-DD (ตัดสินวันกำกวมด้วย Load_Timestamp)")
    df["Load_Timestamp"] = pd.to_datetime(df["Load_Timestamp"], errors="coerce")
    assert df["Load_Timestamp"].notna().all(), "Load_Timestamp ต้องอ่านได้ทุกแถว เพราะใช้เป็นหลักฐานตัดสินวันที่"

    df["Order_Date_Raw"] = df["Order_Date"]
    resolved = [
        resolve_order_date(raw, load_ts)
        for raw, load_ts in zip(df["Order_Date_Raw"], df["Load_Timestamp"])
    ]
    df["Order_Date"] = pd.to_datetime([r[0] for r in resolved])
    df["Order_Date_Parse_Method"] = [r[1] for r in resolved]
    df["Order_Date_Was_Imputed"] = [r[2] for r in resolved]

    print(df["Order_Date_Parse_Method"].value_counts().to_string())
    n_imputed = int(df["Order_Date_Was_Imputed"].sum())
    print(f"\nแถวที่อ่านวันที่ไม่ได้เลยและต้อง impute = {n_imputed} แถว")
    print(df.loc[df["Order_Date_Was_Imputed"],
                 ["Transaction_ID", "Order_Date_Raw", "Load_Timestamp", "Order_Date"]].to_string(index=False))

    step("ตัวอย่างวันกำกวมที่ตัดสินด้วย Load_Timestamp (คำถามวิเคราะห์ข้อ 2)")
    ambiguous = df[df["Order_Date_Parse_Method"].str.startswith("RESOLVED_BY_LOAD_TS")].copy()
    ambiguous["Delay_Hours"] = (ambiguous["Load_Timestamp"] - ambiguous["Order_Date"]).dt.total_seconds() / 3600
    print(f"จำนวนแถวที่ต้องใช้ Load_Timestamp ตัดสิน = {len(ambiguous)} แถว")
    print(ambiguous[["Transaction_ID", "Order_Date_Raw", "Load_Timestamp", "Order_Date",
                     "Order_Date_Parse_Method", "Delay_Hours"]].head(8).to_string(index=False))

    assert df["Order_Date"].notna().all(), "ยังมี Order_Date ที่แปลงไม่ได้"
    delay = (df["Load_Timestamp"] - df["Order_Date"]).dt.total_seconds()
    assert (delay >= 0).all(), (
        f"มี {int((delay < 0).sum())} แถวที่ Order_Date มาหลัง Load_Timestamp -> การตัดสินวันที่ยังผิด"
    )

    return df, {
        "order_date_imputed": n_imputed,
        "order_date_resolved_by_load_ts": len(ambiguous),
        "distinct_gender_after": int(df["Gender"].nunique()),
        "distinct_payment_after": int(df["Payment_Method"].nunique()),
    }


# ---------------------------------------------------------------------------
# Task 4 - Uniqueness
# ---------------------------------------------------------------------------
def _normalize_name(series: pd.Series) -> pd.Series:
    """บีบช่องว่างซ้ำและตัด case ออก เพื่อจับชื่อที่ 'ตาเห็นว่าเหมือน' แต่ byte ไม่เท่ากัน"""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.casefold()
    )


def task4_uniqueness(df: pd.DataFrame, ref: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    banner("TASK 4 - UNIQUENESS")
    df = df.copy()

    step("Exact duplicate")
    # เทียบเฉพาะคอลัมน์ต้นฉบับ เพราะคอลัมน์ flag ที่เพิ่มมาไม่ใช่เนื้อหาของธุรกรรม
    business_cols = [c for c in df.columns if not c.endswith(("_Was_Missing", "_From_Reference",
                                                              "_Parse_Method", "_Was_Imputed", "_Raw"))]
    n_exact = int(df.duplicated(subset=business_cols).sum())
    print(f"แถวซ้ำทั้งแถว = {n_exact} | Transaction_ID ซ้ำ = {int(df['Transaction_ID'].duplicated().sum())}")
    print("ตัวอย่างคู่ที่ซ้ำ:")
    dup_ids = df.loc[df["Transaction_ID"].duplicated(keep=False), "Transaction_ID"].unique()[:2]
    print(df[df["Transaction_ID"].isin(dup_ids)][
        ["Transaction_ID", "Customer_ID", "Order_Date", "Transaction_Amount", "Order_Status"]
    ].to_string(index=False))

    before = len(df)
    df = df.drop_duplicates(subset=business_cols, keep="first").reset_index(drop=True)
    print(f"\nหลัง drop_duplicates(keep='first'): {before} -> {len(df)} แถว (ลบ {before - len(df)} แถว)")
    assert not df["Transaction_ID"].duplicated().any(), "ยังมี Transaction_ID ซ้ำหลัง dedup"

    step("Near duplicate: ชื่อลูกค้าที่เขียนต่างกันแต่เป็นคนเดียวกัน")
    df["Customer_Name_Normalized"] = _normalize_name(df["Customer_Name"]).str.title()
    ref_names = _normalize_name(ref["Customer_Name"]).str.title()
    golden = dict(zip(ref["Customer_ID"], ref["Customer_Name"]))

    near_dups = []
    for key_col in ["Customer_ID", "Customer_Email"]:
        grouped = df.groupby(key_col)["Customer_Name"].agg(["nunique", lambda s: sorted(set(s))])
        conflicts = grouped[grouped["nunique"] > 1]
        for key, row in conflicts.iterrows():
            near_dups.append({"Secondary_Key": key_col, "Key_Value": key,
                              "ชื่อที่พบในข้อมูล": " | ".join(repr(n) for n in row.iloc[1]),
                              "Golden Record": golden.get(key, "-")})

    # เทียบกับ reference: ชื่อใน raw ต่างจาก golden record แต่ normalize แล้วตรงกัน
    ref_lookup = dict(zip(ref["Customer_ID"], ref["Customer_Name"]))
    ref_norm_lookup = dict(zip(ref["Customer_ID"], ref_names))
    mismatch = df[
        df["Customer_ID"].map(ref_lookup).notna()
        & (df["Customer_Name"] != df["Customer_ID"].map(ref_lookup))
    ]
    for _, row in mismatch.iterrows():
        same_after_normalize = _normalize_name(pd.Series([row["Customer_Name"]])).str.title().iloc[0] \
                               == ref_norm_lookup.get(row["Customer_ID"])
        near_dups.append({
            "Secondary_Key": "Customer_ID vs reference",
            "Key_Value": row["Customer_ID"],
            "ชื่อที่พบในข้อมูล": f"{row['Customer_Name']!r} (normalize แล้วตรงกับ golden: {same_after_normalize})",
            "Golden Record": ref_lookup[row["Customer_ID"]],
        })

    near_dup_df = pd.DataFrame(near_dups).drop_duplicates().reset_index(drop=True)
    if near_dup_df.empty:
        print("ไม่พบ near duplicate")
    else:
        print(near_dup_df.to_string(index=False))
    print("\nหมายเหตุ: near duplicate ถูกรายงานไว้เท่านั้น ไม่ลบอัตโนมัติ เพราะต้องมี human review "
          "ก่อนรวมลูกค้าสองรายเข้าด้วยกัน (ผิดแล้วยอดขายจะไปผูกกับคนผิด)")

    return df, {
        "exact_duplicates_removed": before - len(df),
        "rows_after_dedup": len(df),
        "near_duplicate_cases": len(near_dup_df),
    }


# ---------------------------------------------------------------------------
# Task 5 - Accuracy & Validity
# ---------------------------------------------------------------------------
STATUS_MAP = {
    "completed": "Completed", "done": "Completed",
    "processing": "Processing",
    "cancelled": "Cancelled", "canceled": "Cancelled", "cancel": "Cancelled",
    "returned": "Returned",
    "unknown status": "Unknown", "unknown": "Unknown",
}


def task5_accuracy_validity(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    banner("TASK 5 - ACCURACY & VALIDITY")
    df = df.copy()

    step(f"Business rule: Quantity ต้องอยู่ในช่วง {QUANTITY_MIN}-{QUANTITY_MAX}")
    df["Quantity_Was_Invalid"] = ~df["Quantity"].between(QUANTITY_MIN, QUANTITY_MAX)
    n_qty_invalid = int(df["Quantity_Was_Invalid"].sum())
    print(f"พบ {n_qty_invalid} แถว:")
    print(df.loc[df["Quantity_Was_Invalid"],
                 ["Transaction_ID", "Quantity", "Unit_Price", "Transaction_Amount"]].to_string(index=False))
    df["Quantity"] = df["Quantity"].clip(QUANTITY_MIN, QUANTITY_MAX)
    assert df["Quantity"].between(QUANTITY_MIN, QUANTITY_MAX).all()
    print(f"หลัง clip: Quantity อยู่ในช่วง {df['Quantity'].min()}-{df['Quantity'].max()}")

    step("Accuracy: Expected_Amount = Quantity * Unit_Price * (1 - Discount_Rate)")
    df["Expected_Amount"] = (
        df["Quantity"] * df["Unit_Price"] * (1 - df["Discount_Rate"])
    ).round(2)
    df["Amount_Difference"] = (df["Transaction_Amount"] - df["Expected_Amount"]).round(2)
    df["Accuracy_Flag"] = df["Amount_Difference"].abs() > 1
    n_accuracy = int(df["Accuracy_Flag"].sum())
    print(f"ยอดที่ไม่ตรงสูตรเกิน 1 บาท = {n_accuracy} แถว")
    print(df.loc[df["Accuracy_Flag"],
                 ["Transaction_ID", "Quantity", "Unit_Price", "Discount_Rate",
                  "Transaction_Amount", "Expected_Amount", "Amount_Difference", "Is_Promotion"]]
          .head(10).to_string(index=False))
    print("\nหมายเหตุ: ไม่เขียน Expected_Amount ทับ Transaction_Amount เพราะยอดที่ไม่ตรงสูตรอาจมาจาก "
          "ค่าส่ง ภาษี หรือส่วนลดโปรโมชันที่ไม่ได้บันทึกใน Discount_Rate -> ต้องให้ business ตรวจก่อน")

    step("Validity: Transaction_Amount ต้องไม่ติดลบ และไม่ใช่ค่า sentinel")
    # IQR จับค่าติดลบไม่ได้ เพราะ lower bound ของข้อมูลชุดนี้ติดลบอยู่แล้ว (ดู Task 6)
    # ยอดติดลบจึงต้องตรวจด้วย business rule แยก ไม่ใช่ปล่อยให้เป็นหน้าที่ของ outlier detection
    df["Amount_Was_Negative"] = df["Transaction_Amount"] < 0
    n_negative = int(df["Amount_Was_Negative"].sum())
    print(f"ยอดติดลบ = {n_negative} แถว")
    if n_negative:
        print(df.loc[df["Amount_Was_Negative"],
                     ["Transaction_ID", "Quantity", "Unit_Price", "Transaction_Amount",
                      "Expected_Amount", "Order_Status"]].to_string(index=False))

    # ค่าที่เป็นเลขหลักเดียวซ้ำกัน 6 หลัก (666666, 999999) เป็น sentinel ของระบบต้นทาง ไม่ใช่ยอดขายจริง
    amount_text = df["Transaction_Amount"].astype("int64", errors="ignore").astype(str)
    df["Amount_Looks_Like_Sentinel"] = amount_text.str.match(r"^(\d)\1{5}$") & (df["Transaction_Amount"] >= 100_000)
    sentinel_total = float(df.loc[df["Amount_Looks_Like_Sentinel"], "Transaction_Amount"].sum())
    print(f"\nค่า sentinel = {int(df['Amount_Looks_Like_Sentinel'].sum())} แถว รวม {sentinel_total:,.2f} บาท")
    if df["Amount_Looks_Like_Sentinel"].any():
        print(df.loc[df["Amount_Looks_Like_Sentinel"],
                     ["Transaction_ID", "Transaction_Amount", "Expected_Amount", "Is_Promotion"]]
              .to_string(index=False))
    print("ค่าเหล่านี้จะถูกจัดการใน Task 6 (capping) แต่ติด flag ไว้ที่นี่เพื่อให้อธิบายได้ว่า "
          "ยอดขายรวมที่ลดลงมากมาจากค่า sentinel ไม่ใช่ข้อมูลจริงที่หายไป")

    step("Validity: Order_Status ต้องอยู่ในชุด Completed / Processing / Cancelled / Returned")
    print("ก่อน:", df["Order_Status"].value_counts(dropna=False).to_dict())
    normalized_status = _normalize_text(df["Order_Status"])
    unknown_status = set(normalized_status.dropna().unique()) - set(STATUS_MAP)
    assert not unknown_status, f"Order_Status มีค่าที่ mapping ยังไม่ครอบคลุม: {unknown_status}"
    df["Status_Was_Invalid"] = ~df["Order_Status"].isin(VALID_STATUS - {"Unknown"})
    df["Order_Status"] = normalized_status.map(STATUS_MAP).fillna("Unknown")
    print("หลัง:", df["Order_Status"].value_counts().to_dict())
    print(f"Status_Was_Invalid = {int(df['Status_Was_Invalid'].sum())} แถว")
    assert not set(df["Order_Status"].unique()) - VALID_STATUS

    return df, {
        "invalid_quantity_fixed": n_qty_invalid,
        "accuracy_mismatch": n_accuracy,
        "negative_amount_rows": n_negative,
        "sentinel_amount_rows": int(df["Amount_Looks_Like_Sentinel"].sum()),
        "sentinel_amount_total": round(sentinel_total, 2),
        "invalid_status_fixed": int(df["Status_Was_Invalid"].sum()),
        "distinct_status_after": int(df["Order_Status"].nunique()),
    }


# ---------------------------------------------------------------------------
# Task 6 - Outliers (IQR + Capping)
# ---------------------------------------------------------------------------
def _boxplot(df: pd.DataFrame, path: Path, title: str) -> None:
    groups = [
        df.loc[df["Is_Promotion"] != "Y", "Transaction_Amount"].to_numpy(),
        df.loc[df["Is_Promotion"] == "Y", "Transaction_Amount"].to_numpy(),
    ]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.boxplot(groups, tick_labels=["Non-promotion (N)", "Promotion (Y)"])
    ax.set_title(title)
    ax.set_ylabel("Transaction_Amount (THB)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"บันทึกกราฟ: {path.name}")


def task6_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    banner("TASK 6 - OUTLIERS (IQR + CAPPING)")
    df = df.copy()
    df["Transaction_Amount_Before_Capping"] = df["Transaction_Amount"]

    step("Boxplot ก่อนทำความสะอาด")
    _boxplot(df, BOXPLOT_BEFORE, "Transaction_Amount BEFORE capping")
    print(df.groupby("Is_Promotion")["Transaction_Amount"].describe().round(2).to_string())

    step("คำนวณ IQR จากรายการที่ไม่ใช่โปรโมชันเท่านั้น (Is_Promotion != 'Y')")
    baseline = df.loc[df["Is_Promotion"] != "Y", "Transaction_Amount"]
    q1, q3 = baseline.quantile(0.25), baseline.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    print(f"ใช้ข้อมูล {len(baseline)} แถวเป็นฐาน (ตัดโปรโมชัน {int((df['Is_Promotion'] == 'Y').sum())} แถวออก)")
    print(f"Q1={q1:,.2f} Q3={q3:,.2f} IQR={iqr:,.2f} -> lower={lower:,.2f} upper={upper:,.2f}")
    print("เหตุผล: ถ้าเอายอดโปรโมชันมาคำนวณด้วย ขอบเขตจะกว้างเกินจริงและกลืน outlier ที่เป็นข้อมูลผิดพลาด")
    if lower < 0:
        print(f"ข้อสังเกตสำคัญ: lower bound = {lower:,.2f} ซึ่งติดลบ -> IQR จับยอดติดลบไม่ได้เลย "
              "เพราะถือว่ายังอยู่ในขอบเขต ยอดติดลบจึงต้องตรวจด้วย business rule ใน Task 5 แยกจากกัน")

    # flag ก่อนแก้ค่า
    df["Outlier_Flag_Before_Capping"] = ~df["Transaction_Amount"].between(lower, upper)
    df["Amount_Was_Capped"] = df["Outlier_Flag_Before_Capping"] & (df["Is_Promotion"] != "Y")

    step("Outlier ที่ตรวจพบ")
    print(f"อยู่นอกขอบเขตทั้งหมด = {int(df['Outlier_Flag_Before_Capping'].sum())} แถว "
          f"(เป็นโปรโมชัน {int((df['Outlier_Flag_Before_Capping'] & (df['Is_Promotion'] == 'Y')).sum())} แถว "
          f"-> ไม่แก้ค่า)")
    print(df.loc[df["Outlier_Flag_Before_Capping"],
                 ["Transaction_ID", "Quantity", "Unit_Price", "Transaction_Amount",
                  "Expected_Amount", "Is_Promotion", "Amount_Was_Capped"]].to_string(index=False))

    step("Capping ด้วย clip() เฉพาะแถวที่ไม่ใช่โปรโมชัน")
    to_cap = df["Amount_Was_Capped"]
    df.loc[to_cap, "Transaction_Amount"] = df.loc[to_cap, "Transaction_Amount"].clip(lower, upper)
    print(f"แก้ค่าไป {int(to_cap.sum())} แถว")
    print(df.loc[to_cap, ["Transaction_ID", "Transaction_Amount_Before_Capping",
                          "Transaction_Amount", "Is_Promotion"]].to_string(index=False))

    # ข้อกำหนดสำคัญของโจทย์: รายการโปรโมชันต้องไม่ถูกแตะ
    promo = df["Is_Promotion"] == "Y"
    assert (df.loc[promo, "Transaction_Amount"]
            == df.loc[promo, "Transaction_Amount_Before_Capping"]).all(), \
        "รายการโปรโมชันถูกแก้ค่า ซึ่งขัดกับข้อกำหนดของโจทย์"
    print(f"\nยืนยัน: รายการโปรโมชัน {int(promo.sum())} แถว มียอดเท่าเดิมทุกบาท")

    step("Boxplot หลังทำความสะอาด")
    _boxplot(df, BOXPLOT_AFTER, "Transaction_Amount AFTER capping (promotions untouched)")
    print(df.groupby("Is_Promotion")["Transaction_Amount"].describe().round(2).to_string())

    return df, {
        "iqr_q1": round(float(q1), 2), "iqr_q3": round(float(q3), 2),
        "iqr_lower_bound": round(float(lower), 2), "iqr_upper_bound": round(float(upper), 2),
        "outliers_detected": int(df["Outlier_Flag_Before_Capping"].sum()),
        "outliers_capped": int(to_cap.sum()),
        "promotion_outliers_kept": int((df["Outlier_Flag_Before_Capping"] & promo).sum()),
    }


# ---------------------------------------------------------------------------
# Task 7 - Timeliness, Report, Export
# ---------------------------------------------------------------------------
def task7_timeliness_report(df: pd.DataFrame, raw: pd.DataFrame, metrics: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    banner("TASK 7 - TIMELINESS, REPORT, EXPORT")
    df = df.copy()

    step(f"Load_Delay_Hours และ SLA {TIMELINESS_SLA_HOURS} ชั่วโมง")
    df["Load_Delay_Hours"] = (
        (df["Load_Timestamp"] - df["Order_Date"]).dt.total_seconds() / 3600
    ).round(1)
    df["Timeliness_Status"] = (df["Load_Delay_Hours"] > TIMELINESS_SLA_HOURS).map(
        {True: "Late", False: "On Time"}
    )
    assert (df["Load_Delay_Hours"] >= 0).all(), "มี Load_Delay_Hours ติดลบ"
    n_late = int((df["Timeliness_Status"] == "Late").sum())
    print(df["Load_Delay_Hours"].describe().round(1).to_string())
    print(f"\nLate = {n_late} แถว ({n_late / len(df) * 100:.1f}%) | On Time = {len(df) - n_late} แถว")
    print("\nแถวที่ล่าช้ามากที่สุด 5 อันดับ:")
    print(df.nlargest(5, "Load_Delay_Hours")[
        ["Transaction_ID", "Order_Date", "Load_Timestamp", "Load_Delay_Hours",
         "Order_Date_Parse_Method"]].to_string(index=False))

    # ---- before metrics ที่ต้องคำนวณจาก raw ----
    raw_dates = pd.to_datetime(raw["Order_Date"], format="%Y-%m-%d", errors="coerce")
    raw_load = pd.to_datetime(raw["Load_Timestamp"])
    measurable = raw_dates.notna()
    raw_delay = (raw_load[measurable] - raw_dates[measurable]).dt.total_seconds() / 3600
    n_unmeasurable_before = int((~measurable).sum())
    n_late_before = int((raw_delay > TIMELINESS_SLA_HOURS).sum())

    # sentinel ที่ยังเหลืออยู่หลัง capping (คำนวณด้วยกฎเดียวกับ Task 5 จากยอดปัจจุบัน)
    sentinel_after = int(
        (df["Transaction_Amount"].round().astype("int64").astype(str).str.match(r"^(\d)\1{5}$")
         & (df["Transaction_Amount"] >= 100_000)).sum()
    )
    revenue_before_excl_sentinel = metrics["total_amount_before"] - metrics["sentinel_amount_total"]

    step("Data Quality Report (ก่อน vs หลัง)")
    rows = [
        ("Overall", "จำนวนแถวทั้งหมด", metrics["rows_raw"], len(df)),
        ("Completeness", "Customer_Email ว่าง", metrics["missing_email_before"], int(df["Customer_Email"].isna().sum())),
        ("Completeness", "Province ว่าง", metrics["missing_province_before"], int(df["Province"].isna().sum())),
        ("Uniqueness", "แถวซ้ำทั้งแถว (exact duplicate)", metrics["exact_duplicates_before"],
         int(df.duplicated().sum())),
        ("Uniqueness", "Transaction_ID ซ้ำ", metrics["exact_duplicates_before"],
         int(df["Transaction_ID"].duplicated().sum())),
        ("Consistency", "จำนวนรูปแบบของ Gender", metrics["distinct_gender_before"], int(df["Gender"].nunique())),
        ("Consistency", "จำนวนรูปแบบของ Payment_Method", metrics["distinct_payment_before"],
         int(df["Payment_Method"].nunique())),
        ("Consistency", "จำนวนรูปแบบของ Order_Status", metrics["distinct_status_before"],
         int(df["Order_Status"].nunique())),
        ("Consistency", "Order_Date ที่ไม่อยู่ในรูป YYYY-MM-DD", n_unmeasurable_before,
         int((~df["Order_Date"].dt.strftime("%Y-%m-%d").str.match(r"^\d{4}-\d{2}-\d{2}$")).sum())),
        ("Validity", f"Quantity นอกช่วง {QUANTITY_MIN}-{QUANTITY_MAX}", metrics["invalid_quantity_before"],
         int((~df["Quantity"].between(QUANTITY_MIN, QUANTITY_MAX)).sum())),
        ("Validity", "Order_Status ที่ยังไม่อยู่ใน 4 ค่ามาตรฐาน (นับ Unknown ที่ไม่ทราบค่าจริง)",
         metrics["invalid_status_fixed"], int((~df["Order_Status"].isin(VALID_STATUS - {"Unknown"})).sum())),
        ("Validity", "Transaction_Amount ติดลบ (ติด flag ไว้ ไม่แก้ค่า รอ business ตรวจว่าเป็น refund หรือไม่)",
         metrics["negative_amount_before"], int((df["Transaction_Amount"] < 0).sum())),
        ("Validity", "Transaction_Amount ที่เป็นค่า sentinel ของระบบต้นทาง",
         metrics["sentinel_amount_rows"], sentinel_after),
        ("Accuracy", "Transaction_Amount ไม่ตรงสูตรเกิน 1 บาท (ไม่แก้ค่า รอ business ตรวจ)",
         metrics["accuracy_mismatch"], int(df["Accuracy_Flag"].sum())),
        ("Accuracy", "Outlier ตาม IQR (นับรวมโปรโมชัน)", metrics["outliers_detected"],
         int((~df["Transaction_Amount"].between(metrics["iqr_lower_bound"], metrics["iqr_upper_bound"])).sum())),
        ("Timeliness", "แถวที่วัด Load_Delay_Hours ไม่ได้เพราะวันที่เสีย", n_unmeasurable_before,
         int(df["Load_Delay_Hours"].isna().sum())),
        ("Timeliness", f"แถวที่ล่าช้ากว่า {TIMELINESS_SLA_HOURS} ชม. "
                       f"(before วัดได้เฉพาะ {int(measurable.sum())} แถวที่วันที่อ่านได้)",
         n_late_before, n_late),
        ("Overall", "ยอดขายรวม (บาท)", round(metrics["total_amount_before"], 2),
         round(float(df["Transaction_Amount"].sum()), 2)),
        ("Overall", f"ยอดขายรวมเมื่อตัดค่า sentinel {metrics['sentinel_amount_rows']} แถวออก (บาท) "
                    "- ตัวเลขนี้อธิบายว่ายอดที่ลดลงมาจาก sentinel ไม่ใช่ข้อมูลจริงที่หายไป",
         round(revenue_before_excl_sentinel, 2), round(float(df["Transaction_Amount"].sum()), 2)),
    ]
    report = pd.DataFrame(rows, columns=["Dimension", "Metric", "Before", "After"])
    report["Change"] = report["After"] - report["Before"]
    print(report.to_string(index=False))

    step("Export")
    export_df = df.copy()
    export_df["Order_Date"] = export_df["Order_Date"].dt.strftime("%Y-%m-%d")
    export_df["Load_Timestamp"] = export_df["Load_Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    export_df.to_csv(CLEAN_PATH, index=False, encoding=ENCODING)
    report.to_csv(REPORT_PATH, index=False, encoding=ENCODING)
    print(f"{CLEAN_PATH.name}: {export_df.shape[0]} แถว {export_df.shape[1]} คอลัมน์")
    print(f"{REPORT_PATH.name}: {report.shape[0]} ตัวชี้วัด")

    return df, report


def final_checks(df: pd.DataFrame, raw: pd.DataFrame, metrics: dict) -> None:
    banner("FINAL VERIFICATION")
    checks = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append((name, condition, detail))

    check("จำนวนแถว = 630 - แถวซ้ำ", len(df) == metrics["rows_raw"] - metrics["exact_duplicates_removed"],
          f"{len(df)} แถว")
    check("Customer_Email / Province ไม่มีค่าว่าง",
          not df["Customer_Email"].isna().any() and not df["Province"].isna().any())
    check("Gender อยู่ในชุดมาตรฐาน", not set(df["Gender"].unique()) - VALID_GENDER,
          str(sorted(df["Gender"].unique())))
    check("Payment_Method อยู่ในชุดมาตรฐาน", not set(df["Payment_Method"].unique()) - VALID_PAYMENT,
          str(sorted(df["Payment_Method"].unique())))
    check("Order_Status อยู่ในชุดมาตรฐาน", not set(df["Order_Status"].unique()) - VALID_STATUS,
          str(sorted(df["Order_Status"].unique())))
    check("Order_Date เป็นวันที่จริงทุกแถว", df["Order_Date"].notna().all())
    check("Order_Date_Was_Imputed = 7 แถว", int(df["Order_Date_Was_Imputed"].sum()) == 7,
          f"{int(df['Order_Date_Was_Imputed'].sum())} แถว")
    check(f"Quantity อยู่ในช่วง {QUANTITY_MIN}-{QUANTITY_MAX}",
          df["Quantity"].between(QUANTITY_MIN, QUANTITY_MAX).all(),
          f"{df['Quantity'].min()}-{df['Quantity'].max()}")
    check("Load_Delay_Hours ไม่ติดลบ", (df["Load_Delay_Hours"] >= 0).all(),
          f"min={df['Load_Delay_Hours'].min()}")
    # ยอดติดลบไม่ได้ถูกแก้ค่า แต่ต้องถูก flag ไว้ครบทุกแถว เพื่อให้ business ตามไปตรวจได้
    negative = df["Transaction_Amount"] < 0
    check("ยอดติดลบทุกแถวถูก flag ไว้ครบ (ไม่แก้ค่าอัตโนมัติ)",
          bool((negative == df["Amount_Was_Negative"]).all()),
          f"{int(negative.sum())} แถว, min={df['Transaction_Amount'].min():,.2f}")
    check("ไม่มีค่า sentinel เหลืออยู่หลัง capping",
          bool(df.loc[df["Amount_Looks_Like_Sentinel"], "Transaction_Amount"].lt(100_000).all()),
          f"{int(df['Amount_Looks_Like_Sentinel'].sum())} แถวถูก cap แล้ว")

    # รายการโปรโมชันต้องเหมือน raw ทุกบาท
    raw_first = raw.drop_duplicates(subset=["Transaction_ID"], keep="first").set_index("Transaction_ID")
    promo = df[df["Is_Promotion"] == "Y"].set_index("Transaction_ID")
    same = (promo["Transaction_Amount"] == raw_first.loc[promo.index, "Transaction_Amount"]).all()
    check(f"รายการโปรโมชัน {len(promo)} แถว มียอดเท่ากับไฟล์ต้นฉบับทุกบาท", bool(same))

    non_promo_max = df.loc[df["Is_Promotion"] != "Y", "Transaction_Amount"].max()
    check("ยอดกลุ่ม non-promotion ไม่เกิน upper bound",
          non_promo_max <= metrics["iqr_upper_bound"] + 1e-6, f"max={non_promo_max:,.2f}")
    check("คอลัมน์ flag ยังอยู่ครบเพื่อ audit",
          all(c in df.columns for c in ["Customer_Email_Was_Missing", "Province_Was_Missing",
                                        "Order_Date_Was_Imputed", "Quantity_Was_Invalid",
                                        "Accuracy_Flag", "Status_Was_Invalid",
                                        "Outlier_Flag_Before_Capping", "Amount_Was_Capped"]))
    check("ไฟล์ output มี BOM (เปิด Excel ภาษาไทยได้)",
          CLEAN_PATH.read_bytes()[:3] == b"\xef\xbb\xbf" and REPORT_PATH.read_bytes()[:3] == b"\xef\xbb\xbf")

    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))
    failed = [n for n, ok, _ in checks if not ok]
    assert not failed, f"การตรวจสอบไม่ผ่าน: {failed}"
    print(f"\nผ่านทั้งหมด {len(checks)}/{len(checks)} ข้อ")


def main() -> None:
    matplotlib.use("Agg")  # รันเป็น script ไม่มี GUI จึงบันทึกกราฟลงไฟล์เท่านั้น
    FIG_DIR.mkdir(parents=True, exist_ok=True)  # กันกรณี clone repo มาแล้วยังไม่มีโฟลเดอร์ output
    raw = pd.read_csv(RAW_PATH, encoding=ENCODING)
    ref = pd.read_csv(REF_PATH, encoding=ENCODING)
    print(f"โหลด {RAW_PATH.name}: {raw.shape} | {REF_PATH.name}: {ref.shape}")

    metrics = {}
    metrics |= task1_profiling(raw)
    df, m = task2_completeness(raw, ref); metrics |= m
    df, m = task3_consistency(df); metrics |= m
    df, m = task4_uniqueness(df, ref); metrics |= m
    df, m = task5_accuracy_validity(df); metrics |= m
    df, m = task6_outliers(df); metrics |= m
    df, report = task7_timeliness_report(df, raw, metrics)

    final_checks(df, raw, metrics)

    banner("METRICS ทั้งหมด")
    for key, value in metrics.items():
        print(f"{key:35s} = {value}")


if __name__ == "__main__":
    main()
