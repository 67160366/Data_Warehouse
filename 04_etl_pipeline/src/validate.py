import logging
import sqlite3
from .config import WAREHOUSE_DB

# ยอดขายเก็บเป็นทศนิยม 2 ตำแหน่ง ต่างกันเกินนี้ถือว่าไม่ตรงกันจริง
SALES_TOLERANCE = 0.01


def validate_data(source_sales):
    """
    เทียบ transformed data กับสิ่งที่อยู่ใน warehouse จริง แล้วสรุป PASS / FAIL
    """
    with sqlite3.connect(WAREHOUSE_DB) as conn:
        warehouse_rows = conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
        duplicate_order_ids = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_sales"
        ).fetchone()[0]
        warehouse_total_sales = conn.execute(
            "SELECT COALESCE(SUM(sales_amount), 0) FROM fact_sales"
        ).fetchone()[0]

    source_valid_rows = len(source_sales)
    source_total_sales = round(float(source_sales["sales_amount"].sum()), 2)
    warehouse_total_sales = round(float(warehouse_total_sales), 2)

    checks = {
        "row_count_match": warehouse_rows == source_valid_rows,
        "no_duplicate_order_id": duplicate_order_ids == 0,
        "total_sales_match": abs(warehouse_total_sales - source_total_sales) < SALES_TOLERANCE,
    }
    for name, ok in checks.items():
        logging.info("validate | %s | %s", name, "PASS" if ok else "FAIL")

    result = {
        "source_valid_rows": source_valid_rows,
        "warehouse_rows": warehouse_rows,
        "duplicate_order_ids": duplicate_order_ids,
        "source_total_sales": source_total_sales,
        "warehouse_total_sales": warehouse_total_sales,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }

    logging.info("validate | done | status=%s", result["status"])
    return result
