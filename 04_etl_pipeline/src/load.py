import logging
import sqlite3
from .config import WAREHOUSE_DB

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS dim_customer (
        customer_id TEXT PRIMARY KEY,
        name        TEXT,
        province    TEXT,
        email       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_product (
        product_id   TEXT PRIMARY KEY,
        product_name TEXT,
        category     TEXT,
        price        REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_sales (
        order_id     TEXT PRIMARY KEY,
        customer_id  TEXT,
        product_id   TEXT,
        order_date   TEXT,
        qty          INTEGER,
        unit_price   REAL,
        discount_pct REAL,
        sales_amount REAL,
        FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
        FOREIGN KEY (product_id)  REFERENCES dim_product  (product_id)
    )
    """,
]

TABLE_COLUMNS = {
    "dim_customer": (["customer_id", "name", "province", "email"], "customer_id"),
    "dim_product": (["product_id", "product_name", "category", "price"], "product_id"),
    "fact_sales": (
        ["order_id", "customer_id", "product_id", "order_date",
         "qty", "unit_price", "discount_pct", "sales_amount"],
        "order_id",
    ),
}


def _upsert(conn, table, df):
    """
    เขียนแบบ UPSERT บน primary key — รันซ้ำจะอัปเดตค่าเดิม ไม่เพิ่มแถวใหม่
    (ต่างจาก to_sql(if_exists="append") ที่จะทำให้ข้อมูลซ้ำ)
    """
    columns, pk = TABLE_COLUMNS[table]
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c != pk)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))}) "
        f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
    )

    rows = df[columns].where(df[columns].notna(), None).itertuples(index=False, name=None)
    conn.executemany(sql, rows)

    after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    logging.info("load | %s | upserted=%d table_rows=%d", table, len(df), after)
    return after


def load_data(customers, products, sales):
    """
    โหลดเข้า warehouse.db 3 ตาราง: dim_customer, dim_product, fact_sales
    order_id / customer_id / product_id เป็น PRIMARY KEY จึงรัน pipeline ซ้ำได้
    โดยจำนวน record ใน fact_sales ไม่เพิ่ม
    """
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(WAREHOUSE_DB) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for ddl in SCHEMA:
            conn.execute(ddl)

        counts = {
            "dim_customer": _upsert(conn, "dim_customer", customers),
            "dim_product": _upsert(conn, "dim_product", products),
            "fact_sales": _upsert(conn, "fact_sales", sales),
        }
        conn.commit()

    logging.info("load | done | %s", counts)
    return counts
