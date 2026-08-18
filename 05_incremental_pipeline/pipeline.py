"""
Week07 Lab - Python Data Pipeline Engineering
สร้าง ETL Pipeline สำหรับข้อมูลยอดขายแบบ Incremental และ Idempotent

โครงสร้างตามภารกิจในโจทย์
    Task 1  PipelineConfig + extract   -> PipelineConfig, extract_dimensions, extract_batch
    Task 2  transform + data quality   -> normalize, validate_rows, deduplicate, compute_amounts
    Task 3  star schema + load         -> create_schema, load_dimensions, load_fact
    Task 4  idempotency + incremental  -> load_fact (upsert ตาม updated_at), log_run
    Task 5  orchestration + KPI        -> run_pipeline, summarize_kpi

การใช้งาน
    python pipeline.py --reset --batch 1     รีเซ็ต warehouse แล้วโหลด batch 1
    python pipeline.py --batch 1             โหลด batch 1 ซ้ำ (แถวใน fact ต้องไม่เพิ่ม)
    python pipeline.py --batch all           โหลดครบ 3 batch ตามลำดับ
    python pipeline.py --tests               รัน acceptance tests อย่างเดียว
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("pipeline")

# รูปแบบวันที่เดียวที่ยอมรับ ค่าที่ไม่ตรงรูปแบบนี้ (เช่น 31/02/2026) จะกลายเป็น NaT แล้วถูกกักกัน
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# mapping ที่อธิบายได้ตาม data_dictionary: normalize ตัวพิมพ์ และ map E-Commerce -> Online
PAYMENT_MAP = {
    "cash": "Cash",
    "credit card": "Credit Card",
    "creditcard": "Credit Card",
    "bank transfer": "Bank Transfer",
    "banktransfer": "Bank Transfer",
    "promptpay": "PromptPay",
    "prompt pay": "PromptPay",
}
CHANNEL_MAP = {
    "online": "Online",
    "store": "Store",
    "marketplace": "Marketplace",
    "e-commerce": "Online",
    "ecommerce": "Online",
    "e commerce": "Online",
}


# ---------------------------------------------------------------- Task 1: config
@dataclass(frozen=True)
class PipelineConfig:
    """พารามิเตอร์ทั้งหมดของการรันหนึ่งครั้ง รวมไว้ที่เดียวเพื่อให้เปลี่ยน path หรือทดสอบได้ง่าย"""

    source_xlsx: Path = ROOT / "data" / "Python_Data_Pipeline_Lab_Dataset.xlsx"
    db_path: Path = ROOT / "output" / "retail_dw.db"
    output_dir: Path = ROOT / "output"
    log_dir: Path = ROOT / "logs"
    batches: tuple[str, ...] = ("orders_batch_1", "orders_batch_2", "orders_batch_3")
    customer_sheet: str = "customers"
    product_sheet: str = "products"
    # quarantine = แถวเสียถูกกักกันแล้วไปต่อ (ค่าเริ่มต้น) / fail_fast = เจอแถวเสียให้ทั้ง batch ล้ม
    error_mode: str = "quarantine"

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class BatchMetrics:
    """ตัวชี้วัดของ batch หนึ่งรอบ ใช้เขียนลง pipeline_run_log (Task 4)"""

    batch: str
    started_at: str
    ended_at: str = ""
    rows_read: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_duplicate: int = 0
    rows_loaded: int = 0
    rows_updated: int = 0
    rows_skipped_stale: int = 0
    rows_repaired: int = 0
    status: str = "RUNNING"
    message: str = ""


# ---------------------------------------------------------------- Task 1: extract
def extract_dimensions(cfg: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """อ่าน sheet customers และ products (อ่านอย่างเดียว ไม่แตะไฟล์ต้นฉบับ)"""
    customers = pd.read_excel(cfg.source_xlsx, sheet_name=cfg.customer_sheet, dtype=str)
    products = pd.read_excel(cfg.source_xlsx, sheet_name=cfg.product_sheet)
    LOG.info("extract dimensions | customers=%d products=%d", len(customers), len(products))
    return customers, products


def extract_batch(cfg: PipelineConfig, sheet: str) -> pd.DataFrame:
    """อ่าน order หนึ่ง batch พร้อม log ชื่อ batch จำนวนแถว และเวลาเริ่ม-สิ้นสุด (โจทย์ Task 1)"""
    started = datetime.now()
    LOG.info("extract %s | started_at=%s", sheet, started.isoformat(timespec="seconds"))
    try:
        df = pd.read_excel(cfg.source_xlsx, sheet_name=sheet, dtype=str)
    except Exception as exc:  # ไฟล์หาย / sheet ผิดชื่อ / ไฟล์เสีย
        LOG.error("extract %s | FAILED: %s", sheet, exc)
        raise
    ended = datetime.now()
    LOG.info(
        "extract %s | rows=%d ended_at=%s duration=%.2fs",
        sheet,
        len(df),
        ended.isoformat(timespec="seconds"),
        (ended - started).total_seconds(),
    )
    return df


# ------------------------------------------------------- Task 2: transform + DQ
def normalize(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    แปลงชนิดข้อมูลอย่างปลอดภัยด้วยแนวคิด errors="coerce"

    ซ่อมเฉพาะปัญหา "รูปแบบ" ที่แก้ได้แน่นอนโดยไม่เดาค่า
        "THB 979.4" -> 979.4 | "credit card" -> "Credit Card" | "E-Commerce" -> "Online"
    ค่าที่ตีความไม่ได้จะกลายเป็น NaN/NaT แล้วให้ validate_rows ตัดสินว่าจะกักกันด้วยเหตุผลอะไร
    """
    out = df.copy()
    repaired = 0

    # เก็บสภาพเดิมไว้ก่อน coerce เพื่อแยก "ค่าว่างตั้งแต่ต้นทาง" ออกจาก "ค่าที่แปลงไม่ได้"
    price_raw = out["unit_price"]
    out["price_was_null"] = price_raw.isna() | (price_raw.astype(str).str.strip().isin(["", "nan", "None"]))

    price_txt = price_raw.astype(str).str.strip()
    repaired += int(price_txt.str.match(r"(?i)^THB\b").sum())
    price_txt = price_txt.str.replace(r"(?i)^THB\s*", "", regex=True).str.replace(",", "", regex=False)
    out["unit_price"] = pd.to_numeric(price_txt, errors="coerce")

    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["discount_pct"] = pd.to_numeric(out["discount_pct"], errors="coerce")

    # format ตายตัว: อะไรที่ไม่ตรง (not-a-date, 31/02/2026) กลายเป็น NaT ทันที ไม่เดาแทนต้นทาง
    out["order_datetime"] = pd.to_datetime(out["order_datetime"], format=DATETIME_FORMAT, errors="coerce")
    out["updated_at"] = pd.to_datetime(out["updated_at"], format=DATETIME_FORMAT, errors="coerce")

    for col, mapping in (("payment_method", PAYMENT_MAP), ("sales_channel", CHANNEL_MAP)):
        raw = out[col].astype(str).str.strip()
        mapped = raw.str.lower().map(mapping)
        repaired += int((mapped.notna() & (mapped != raw)).sum())
        out[col] = mapped  # ค่าที่ map ไม่ได้จะเป็น NaN แล้วถูกกักกัน

    for col in ("order_id", "customer_id", "product_id"):
        out[col] = out[col].astype(str).str.strip().replace({"": None, "nan": None, "None": None})

    return out, repaired


def validate_rows(
    df: pd.DataFrame, customer_ids: set[str], product_ids: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ตรวจกฎคุณภาพข้อมูลทีละแถว คืน (clean, quarantine) โดย quarantine ทุกแถวมี reason_code เสมอ"""
    reasons: list[str] = []

    for row in df.itertuples(index=False):
        why: list[str] = []

        if row.order_id is None or pd.isna(row.order_id):
            why.append("ORDER_ID_MISSING")
        if pd.isna(row.order_datetime):
            why.append("INVALID_DATE")
        if pd.isna(row.updated_at):
            why.append("INVALID_UPDATED_AT")

        if pd.isna(row.quantity):
            why.append("QTY_NOT_NUMERIC")
        elif row.quantity != int(row.quantity):
            why.append("QTY_NOT_INTEGER")
        elif not 1 <= row.quantity <= 20:  # data_dictionary: integer 1-20
            why.append("QTY_OUT_OF_RANGE")

        if row.price_was_null:
            why.append("PRICE_MISSING")
        elif pd.isna(row.unit_price):
            why.append("PRICE_NOT_NUMERIC")
        elif row.unit_price <= 0:
            why.append("PRICE_NOT_POSITIVE")

        if pd.isna(row.discount_pct):
            why.append("DISCOUNT_NOT_NUMERIC")
        elif not 0 <= row.discount_pct <= 100:
            why.append("DISCOUNT_OUT_OF_RANGE")

        if row.customer_id is None or pd.isna(row.customer_id):
            why.append("CUSTOMER_MISSING")
        elif row.customer_id not in customer_ids:
            why.append("CUSTOMER_NOT_FOUND")

        if row.product_id is None or pd.isna(row.product_id):
            why.append("PRODUCT_MISSING")
        elif row.product_id not in product_ids:
            why.append("PRODUCT_NOT_FOUND")

        if pd.isna(row.payment_method):
            why.append("PAYMENT_METHOD_UNKNOWN")
        if pd.isna(row.sales_channel):
            why.append("SALES_CHANNEL_UNKNOWN")

        reasons.append("|".join(why))

    reason_series = pd.Series(reasons, index=df.index)
    bad = reason_series != ""

    quarantine = df[bad].copy()
    quarantine["reason_code"] = reason_series[bad]
    clean = df[~bad].copy()
    return clean, quarantine


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """โจทย์ Task 2: dedupe ด้วย order_id โดยเก็บระเบียนที่ updated_at ล่าสุด"""
    before = len(df)
    out = df.sort_values("updated_at", kind="stable").drop_duplicates("order_id", keep="last")
    return out, before - len(out)


def compute_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """gross_amount = quantity * unit_price ; net_amount = gross * (1 - discount/100)"""
    out = df.copy()
    out["gross_amount"] = (out["quantity"] * out["unit_price"]).round(2)
    out["net_amount"] = (out["gross_amount"] * (1 - out["discount_pct"] / 100)).round(2)
    return out


# ------------------------------------------------- Task 3: star schema + load
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   TEXT NOT NULL UNIQUE,
    customer_name TEXT,
    province      TEXT,
    segment       TEXT,
    signup_date   TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL UNIQUE,
    product_name TEXT,
    category     TEXT,
    unit_price   REAL,
    active_flag  TEXT
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key  INTEGER PRIMARY KEY,          -- YYYYMMDD
    full_date TEXT NOT NULL UNIQUE,
    day       INTEGER NOT NULL,
    month     INTEGER NOT NULL,
    quarter   INTEGER NOT NULL,
    year      INTEGER NOT NULL
);

-- grain: หนึ่งรายการขายสินค้าที่ผ่านการตรวจสอบ ต่อหนึ่ง order_id
CREATE TABLE IF NOT EXISTS fact_sales (
    order_id       TEXT PRIMARY KEY,
    date_key       INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key   INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    product_key    INTEGER NOT NULL REFERENCES dim_product(product_key),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     REAL    NOT NULL CHECK (unit_price > 0),
    discount_pct   REAL    NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
    gross_amount   REAL    NOT NULL CHECK (gross_amount >= 0),
    net_amount     REAL    NOT NULL CHECK (net_amount >= 0),
    payment_method TEXT    NOT NULL,
    sales_channel  TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,        -- ใช้ตัดสินว่า record ใหม่กว่าของเดิมหรือไม่
    source_batch   TEXT    NOT NULL,
    loaded_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_date     ON fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_customer ON fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_product  ON fact_sales(product_key);

CREATE TABLE IF NOT EXISTS quarantine (
    row_uid        TEXT PRIMARY KEY,        -- hash ของ batch+แถว+เหตุผล ทำให้รันซ้ำไม่เกิด quarantine ซ้ำ
    order_id       TEXT,
    source_batch   TEXT NOT NULL,
    source_row     INTEGER,                 -- เลขแถวใน sheet ต้นทาง ใช้ไล่กลับไปดูข้อมูลดิบ
    reason_code    TEXT NOT NULL,
    raw_payload    TEXT NOT NULL,
    quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    batch              TEXT NOT NULL,
    started_at         TEXT NOT NULL,
    ended_at           TEXT,
    rows_read          INTEGER DEFAULT 0,
    rows_valid         INTEGER DEFAULT 0,
    rows_rejected      INTEGER DEFAULT 0,
    rows_duplicate     INTEGER DEFAULT 0,
    rows_loaded        INTEGER DEFAULT 0,
    rows_updated       INTEGER DEFAULT 0,
    rows_skipped_stale INTEGER DEFAULT 0,
    rows_repaired      INTEGER DEFAULT 0,
    status             TEXT NOT NULL,
    message            TEXT
);
"""


def connect(cfg: PipelineConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("PRAGMA foreign_keys = ON")  # บังคับ referential integrity ที่ระดับ engine
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _records(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """แปลง DataFrame เป็น tuple สำหรับ executemany โดยเปลี่ยน NaN เป็น None ให้ sqlite เข้าใจ"""
    sub = df[columns].astype(object).where(pd.notna(df[columns]), None)
    return list(sub.itertuples(index=False, name=None))


def load_dimensions(conn: sqlite3.Connection, customers: pd.DataFrame, products: pd.DataFrame) -> None:
    """upsert dimension ตาม business key จึงรันซ้ำได้โดย surrogate key ไม่เปลี่ยน"""
    with conn:
        conn.executemany(
            """
            INSERT INTO dim_customer (customer_id, customer_name, province, segment, signup_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                customer_name = excluded.customer_name,
                province      = excluded.province,
                segment       = excluded.segment,
                signup_date   = excluded.signup_date
            """,
            _records(customers, ["customer_id", "customer_name", "province", "segment", "signup_date"]),
        )
        conn.executemany(
            """
            INSERT INTO dim_product (product_id, product_name, category, unit_price, active_flag)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                product_name = excluded.product_name,
                category     = excluded.category,
                unit_price   = excluded.unit_price,
                active_flag  = excluded.active_flag
            """,
            _records(products, ["product_id", "product_name", "category", "unit_price", "active_flag"]),
        )
    LOG.info("load dimensions | dim_customer=%d dim_product=%d", len(customers), len(products))


def load_dim_date(conn: sqlite3.Connection, dates: pd.Series) -> None:
    """สร้าง dim_date จากวันที่ที่ผ่านการตรวจสอบแล้วเท่านั้น (insert-or-ignore จึงรันซ้ำได้)"""
    if dates.empty:
        return
    days = pd.DatetimeIndex(dates.dt.normalize().unique())
    rows = [
        (
            int(d.strftime("%Y%m%d")),
            d.strftime("%Y-%m-%d"),
            int(d.day),
            int(d.month),
            (int(d.month) - 1) // 3 + 1,
            int(d.year),
        )
        for d in days
    ]
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO dim_date (date_key, full_date, day, month, quarter, year)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )


def load_fact(conn: sqlite3.Connection, df: pd.DataFrame, metrics: BatchMetrics) -> None:
    """
    หัวใจของ Task 3-4: upsert ด้วย ON CONFLICT(order_id) และอัปเดตเฉพาะเมื่อ updated_at ใหม่กว่า

      - รัน batch เดิมซ้ำ    -> updated_at เท่าเดิม   -> ไม่ insert ไม่ update -> จำนวนแถวคงที่
      - record ถูกแก้มาใหม่  -> updated_at ใหม่กว่า  -> update ทับ
      - record เก่ามาทีหลัง  -> updated_at เก่ากว่า  -> ข้าม ไม่ให้ข้อมูลเก่าทับของใหม่

    ทั้ง batch อยู่ใน transaction เดียว ถ้าพังกลางทางจะ rollback ไม่ทิ้งข้อมูลค้างครึ่งทาง
    """
    if df.empty:
        return

    cust_key = dict(conn.execute("SELECT customer_id, customer_key FROM dim_customer").fetchall())
    prod_key = dict(conn.execute("SELECT product_id, product_key FROM dim_product").fetchall())
    existing = dict(conn.execute("SELECT order_id, updated_at FROM fact_sales").fetchall())

    now = datetime.now().isoformat(timespec="seconds")
    payload = []
    for r in df.itertuples(index=False):
        updated_at = r.updated_at.strftime(DATETIME_FORMAT)
        prev = existing.get(r.order_id)
        if prev is None:
            metrics.rows_loaded += 1
        elif updated_at > prev:  # รูปแบบ ISO จึงเทียบเป็นข้อความได้ตรงกับที่ SQL เทียบ
            metrics.rows_updated += 1
        else:
            metrics.rows_skipped_stale += 1
        payload.append(
            (
                r.order_id,
                int(r.order_datetime.strftime("%Y%m%d")),
                cust_key[r.customer_id],
                prod_key[r.product_id],
                int(r.quantity),
                float(r.unit_price),
                float(r.discount_pct),
                float(r.gross_amount),
                float(r.net_amount),
                r.payment_method,
                r.sales_channel,
                updated_at,
                str(r.source_batch),
                now,
            )
        )

    with conn:  # transaction เดียวต่อหนึ่ง batch
        conn.executemany(
            """
            INSERT INTO fact_sales (
                order_id, date_key, customer_key, product_key,
                quantity, unit_price, discount_pct, gross_amount, net_amount,
                payment_method, sales_channel, updated_at, source_batch, loaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                date_key       = excluded.date_key,
                customer_key   = excluded.customer_key,
                product_key    = excluded.product_key,
                quantity       = excluded.quantity,
                unit_price     = excluded.unit_price,
                discount_pct   = excluded.discount_pct,
                gross_amount   = excluded.gross_amount,
                net_amount     = excluded.net_amount,
                payment_method = excluded.payment_method,
                sales_channel  = excluded.sales_channel,
                updated_at     = excluded.updated_at,
                source_batch   = excluded.source_batch,
                loaded_at      = excluded.loaded_at
            WHERE excluded.updated_at > fact_sales.updated_at
            """,
            payload,
        )


def load_quarantine(conn: sqlite3.Connection, df: pd.DataFrame, batch: str) -> None:
    """
    เก็บแถวเสียพร้อม reason_code และข้อมูลดิบ

    row_uid = hash ของ (batch, เลขแถวใน sheet, order_id, reason) จึง
      - รัน batch เดิมซ้ำ -> ได้ hash เดิม -> INSERT OR IGNORE ไม่เกิดรายการซ้ำ
      - แถวเสียที่ซ้ำกันเป๊ะแต่คนละแถวใน sheet -> hash ต่างกัน -> ยังนับครบทุกแถวจริง
    """
    if df.empty:
        return
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for idx, record in zip(df.index, df.to_dict(orient="records")):
        reason = record.pop("reason_code")
        record.pop("price_was_null", None)
        source_row = int(idx) + 2  # +2 = ข้ามหัวตาราง และ index เริ่มที่ 0 -> เลขแถวจริงใน Excel
        payload = json.dumps(
            {k: (None if pd.isna(v) else str(v)) for k, v in record.items()}, ensure_ascii=False
        )
        uid = hashlib.sha1(
            f"{batch}|{source_row}|{record.get('order_id')}|{reason}".encode()
        ).hexdigest()
        rows.append((uid, record.get("order_id"), batch, source_row, reason, payload, now))
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO quarantine"
            " (row_uid, order_id, source_batch, source_row, reason_code, raw_payload, quarantined_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def log_run(conn: sqlite3.Connection, m: BatchMetrics) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO pipeline_run_log (
                batch, started_at, ended_at, rows_read, rows_valid, rows_rejected, rows_duplicate,
                rows_loaded, rows_updated, rows_skipped_stale, rows_repaired, status, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.batch, m.started_at, m.ended_at, m.rows_read, m.rows_valid, m.rows_rejected,
                m.rows_duplicate, m.rows_loaded, m.rows_updated, m.rows_skipped_stale,
                m.rows_repaired, m.status, m.message,
            ),
        )


# ------------------------------------------------- Task 5: orchestration + KPI
def process_batch(
    conn: sqlite3.Connection,
    cfg: PipelineConfig,
    sheet: str,
    customers: pd.DataFrame,
    products: pd.DataFrame,
) -> BatchMetrics:
    """extract -> transform -> validate -> load ของหนึ่ง batch พร้อมบันทึก run log เสมอ"""
    metrics = BatchMetrics(batch=sheet, started_at=datetime.now().isoformat(timespec="seconds"))
    try:
        raw = extract_batch(cfg, sheet)
        metrics.rows_read = len(raw)

        normalized, metrics.rows_repaired = normalize(raw)
        clean, quarantined = validate_rows(
            normalized, set(customers["customer_id"]), set(products["product_id"])
        )
        metrics.rows_valid = len(clean)
        metrics.rows_rejected = len(quarantined)

        if metrics.rows_rejected and cfg.error_mode == "fail_fast":
            raise ValueError(f"error_mode=fail_fast: พบแถวไม่ผ่านการตรวจสอบ {metrics.rows_rejected} แถว")

        load_quarantine(conn, quarantined, sheet)

        clean, metrics.rows_duplicate = deduplicate(clean)
        clean = compute_amounts(clean)

        load_dim_date(conn, clean["order_datetime"])
        load_fact(conn, clean, metrics)

        metrics.status = "SUCCESS"
        LOG.info(
            "load %s | read=%d valid=%d rejected=%d duplicate=%d inserted=%d updated=%d"
            " skipped_stale=%d repaired=%d",
            sheet, metrics.rows_read, metrics.rows_valid, metrics.rows_rejected,
            metrics.rows_duplicate, metrics.rows_loaded, metrics.rows_updated,
            metrics.rows_skipped_stale, metrics.rows_repaired,
        )
    except Exception as exc:
        # batch เดียวล้มไม่ทำลายข้อมูลที่โหลดสำเร็จก่อนหน้า เพราะ commit แยกต่อ batch
        metrics.status = "FAILED"
        metrics.message = f"{type(exc).__name__}: {exc}"
        LOG.exception("load %s | FAILED", sheet)
    finally:
        metrics.ended_at = datetime.now().isoformat(timespec="seconds")
        log_run(conn, metrics)
    return metrics


def summarize_kpi(conn: sqlite3.Connection, runs: list[BatchMetrics]) -> dict:
    fact_rows, net_sales = conn.execute(
        "SELECT COUNT(*), COALESCE(ROUND(SUM(net_amount), 2), 0) FROM fact_sales"
    ).fetchone()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "rows_* = เฉพาะการรันครั้งนี้ | *_total = สถานะสะสมของ warehouse ทั้งหมด",
        "batches_processed": [r.batch for r in runs],
        "batch_status": {r.batch: r.status for r in runs},
        "rows_read": sum(r.rows_read for r in runs),
        "rows_valid": sum(r.rows_valid for r in runs),
        "rows_rejected": sum(r.rows_rejected for r in runs),
        "rows_duplicate": sum(r.rows_duplicate for r in runs),
        "rows_repaired": sum(r.rows_repaired for r in runs),
        "rows_inserted": sum(r.rows_loaded for r in runs),
        "rows_updated": sum(r.rows_updated for r in runs),
        "rows_skipped_stale": sum(r.rows_skipped_stale for r in runs),
        "fact_sales_rows_total": fact_rows,
        "quarantine_rows_total": conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0],
        "net_sales_total": net_sales,
        "formula": (
            "rows_read = rows_valid + rows_rejected (นับก่อน deduplicate); "
            "rows_valid = rows_duplicate + rows_inserted + rows_updated + rows_skipped_stale"
        ),
    }


def export_outputs(conn: sqlite3.Connection, cfg: PipelineConfig) -> None:
    """export ตาราง quarantine และ pipeline_run_log เป็น CSV ตาม deliverable ข้อ 5 ของโจทย์"""
    pd.read_sql_query("SELECT * FROM quarantine ORDER BY source_batch, order_id", conn).to_csv(
        cfg.output_dir / "quarantine.csv", index=False, encoding="utf-8-sig"
    )
    pd.read_sql_query("SELECT * FROM pipeline_run_log ORDER BY run_id", conn).to_csv(
        cfg.output_dir / "pipeline_run_log.csv", index=False, encoding="utf-8-sig"
    )


def run_pipeline(cfg: PipelineConfig, batches: tuple[str, ...] | None = None) -> dict:
    """orchestrator ตาม Task 5"""
    cfg.ensure_dirs()
    targets = batches or cfg.batches
    conn = connect(cfg)
    try:
        create_schema(conn)
        try:
            customers, products = extract_dimensions(cfg)
            load_dimensions(conn, customers, products)
        except Exception as exc:
            # ไฟล์ต้นทางหายหรือเปิดไม่ได้ = ไม่มี dimension ให้ตรวจ referential integrity จึงไม่โหลด batch ใดเลย
            # แต่ต้องบันทึก FAILED ให้ครบทุก batch ตามโจทย์ Task 5 และไม่แตะข้อมูลเดิมใน warehouse
            now = datetime.now().isoformat(timespec="seconds")
            message = f"{type(exc).__name__}: {exc}"
            LOG.error("extract dimensions | FAILED: %s | ไม่โหลด batch ใด ข้อมูลเดิมยังอยู่ครบ", message)
            runs = [
                BatchMetrics(batch=sheet, started_at=now, ended_at=now, status="FAILED", message=message)
                for sheet in targets
            ]
            for m in runs:
                log_run(conn, m)
            export_outputs(conn, cfg)
            return summarize_kpi(conn, runs)

        runs = [process_batch(conn, cfg, sheet, customers, products) for sheet in targets]
        export_outputs(conn, cfg)
        kpi = summarize_kpi(conn, runs)
        (cfg.output_dir / "kpi_summary.json").write_text(
            json.dumps(kpi, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return kpi
    finally:
        conn.close()


# ------------------------------------------------- Acceptance tests (โจทย์ข้อ 6)
def run_acceptance_tests(cfg: PipelineConfig) -> bool:
    """แปลงเกณฑ์ยอมรับทั้ง 7 ข้อในโจทย์เป็นคำสั่ง SQL ตรวจจริง แล้วพิมพ์ PASS/FAIL"""
    conn = connect(cfg)
    checks: list[tuple[str, bool, str]] = []
    try:
        total, distinct = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT order_id) FROM fact_sales"
        ).fetchone()
        checks.append(("order_id ใน fact_sales ไม่ซ้ำ", total == distinct, f"{total} แถว / {distinct} order_id"))

        batches = conn.execute("SELECT COUNT(DISTINCT source_batch) FROM fact_sales").fetchone()[0]
        checks.append(("โหลดครบ 3 batch", batches == 3, f"source_batch = {batches} ค่า"))

        orphan = conn.execute(
            """
            SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_customer c ON c.customer_key = f.customer_key
            LEFT JOIN dim_product  p ON p.product_key  = f.product_key
            LEFT JOIN dim_date     d ON d.date_key     = f.date_key
            WHERE c.customer_key IS NULL OR p.product_key IS NULL OR d.date_key IS NULL
            """
        ).fetchone()[0]
        checks.append(("foreign key เชื่อม dimension ได้ทุกแถว", orphan == 0, f"orphan = {orphan}"))

        neg = conn.execute(
            "SELECT COUNT(*) FROM fact_sales WHERE quantity <= 0 OR unit_price <= 0 OR net_amount < 0"
        ).fetchone()[0]
        checks.append(("quantity / unit_price / net_amount ไม่ติดลบ", neg == 0, f"พบ {neg} แถว"))

        no_reason = conn.execute(
            "SELECT COUNT(*) FROM quarantine WHERE reason_code IS NULL OR TRIM(reason_code) = ''"
        ).fetchone()[0]
        checks.append(
            ("ทุกแถวที่ถูกปฏิเสธมี reason_code", no_reason == 0, f"ไม่มี reason_code = {no_reason} แถว")
        )

        bad_formula = conn.execute(
            "SELECT COUNT(*) FROM pipeline_run_log"
            " WHERE status = 'SUCCESS' AND rows_read <> rows_valid + rows_rejected"
        ).fetchone()[0]
        checks.append(
            ("run log: rows_read = rows_valid + rows_rejected", bad_formula == 0, f"ผิดสูตร {bad_formula} รอบ")
        )

        rerun = conn.execute(
            """
            SELECT COUNT(*) FROM pipeline_run_log a
            WHERE a.status = 'SUCCESS'
              AND a.rows_loaded > 0
              AND EXISTS (
                    SELECT 1 FROM pipeline_run_log b
                    WHERE b.batch = a.batch AND b.run_id < a.run_id AND b.status = 'SUCCESS'
              )
            """
        ).fetchone()[0]
        checks.append(("รัน batch เดิมซ้ำไม่เพิ่มแถว fact", rerun == 0, f"รอบที่รันซ้ำแล้ว insert เพิ่ม = {rerun}"))
    finally:
        conn.close()

    print("\nAcceptance Tests")
    print("-" * 74)
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  ({detail})")
    print("-" * 74)
    print(f"  สรุป: {sum(ok for _, ok, _ in checks)}/{len(checks)} ผ่าน\n")
    return all(ok for _, ok, _ in checks)


# ------------------------------------------------------------------------ CLI
def setup_logging(cfg: PipelineConfig) -> None:
    cfg.ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        handlers=[
            logging.FileHandler(cfg.log_dir / "pipeline.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Week07 incremental & idempotent sales pipeline")
    parser.add_argument("--batch", default="all", help="1 | 2 | 3 | all (ค่าเริ่มต้น all)")
    parser.add_argument("--reset", action="store_true", help="ลบ warehouse เดิมก่อนรัน")
    parser.add_argument("--tests", action="store_true", help="รัน acceptance tests อย่างเดียว")
    parser.add_argument("--error-mode", default="quarantine", choices=["quarantine", "fail_fast"])
    args = parser.parse_args(argv)

    cfg = PipelineConfig(error_mode=args.error_mode)
    setup_logging(cfg)

    if args.tests:
        return 0 if run_acceptance_tests(cfg) else 1

    if args.reset and cfg.db_path.exists():
        cfg.db_path.unlink()
        LOG.warning("reset | ลบ %s แล้ว", cfg.db_path.name)

    targets = cfg.batches if args.batch == "all" else (f"orders_batch_{args.batch}",)
    unknown = [t for t in targets if t not in cfg.batches]
    if unknown:
        parser.error(f"ไม่รู้จัก batch: {unknown}")

    kpi = run_pipeline(cfg, targets)
    print("\nKPI Summary")
    print(json.dumps(kpi, ensure_ascii=False, indent=2))
    # คืน exit code 1 ถ้ามี batch ใดล้ม เพื่อให้ scheduler หรือ CI จับความล้มเหลวได้
    return 0 if all(s == "SUCCESS" for s in kpi["batch_status"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
