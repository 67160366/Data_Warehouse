import logging
import pandas as pd
from .config import PROVINCE_MAP

# order_date มาปนกัน 4 รูปแบบ ไล่ parse ตามลำดับนี้ (%Y/%m/%d ต้องมาก่อน %d/%m/%Y
# ไม่งั้น 2026/08/02 จะถูกอ่านเป็น day=2026)
DATE_FORMATS = ["%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"]

KEEP_STATUS = {"paid", "completed"}

UNKNOWN = "Unknown"


def _tag_rejects(df, reason, stage):
    """
    คืน copy ของ df ที่ติดป้ายเหตุผลไว้ พร้อมเข้ากอง rejects
    reason รับได้ทั้ง string เดียวและ Series (กรณีแต่ละแถวผิดคนละกฎ)
    """
    out = df.copy()
    out.insert(0, "reject_reason", reason if isinstance(reason, str) else reason.loc[df.index])
    out.insert(0, "reject_stage", stage)
    return out


def _combine_reasons(rules, index):
    """รวมเหตุผลของแถวที่ผิดหลายกฎพร้อมกันไว้ในช่องเดียว คั่นด้วย ;"""
    reasons = pd.Series("", index=index, dtype="string")
    for reason, mask in rules.items():
        reasons = reasons.where(~mask, reasons.str.cat(pd.Series(reason, index=index), sep=";"))
        logging.info("transform | rule=%s failed=%d", reason, int(mask.sum()))
    return reasons.str.lstrip(";")


def _parse_mixed_dates(s):
    """parse วันที่หลายรูปแบบ ค่าที่ไม่เข้าฟอร์แมตไหนเลยจะได้ NaT"""
    text = s.astype("string").str.strip()
    out = pd.Series(pd.NaT, index=text.index, dtype="datetime64[ns]")

    for fmt in DATE_FORMATS:
        todo = out.isna() & text.notna()
        if not todo.any():
            break
        out.loc[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")

    return out


def _clean_customers(raw_customers):
    df = raw_customers.copy()

    dup_mask = df["customer_id"].duplicated(keep="first")
    dup_rejects = _tag_rejects(df[dup_mask], "duplicate_customer_id", "customers")
    df = df[~dup_mask].copy()

    df["province"] = (
        df["province"].astype("string").str.strip().str.lower()
        .map(PROVINCE_MAP)
        .fillna(UNKNOWN)
    )
    df["name"] = df["name"].astype("string").str.strip().fillna(UNKNOWN)
    df["email"] = df["email"].astype("string").str.strip().fillna(UNKNOWN)
    df.loc[df["email"] == "", "email"] = UNKNOWN

    logging.info(
        "transform | customers | kept=%d dropped_duplicates=%d provinces=%s",
        len(df), int(dup_mask.sum()), sorted(df["province"].unique())
    )
    return df[["customer_id", "name", "province", "email"]], dup_rejects


def _clean_products(raw_products):
    df = raw_products.rename(columns={
        "category.name": "category",
        "pricing.price": "price",
    }).copy()

    dup_mask = df["product_id"].duplicated(keep="first")
    dup_rejects = _tag_rejects(df[dup_mask], "duplicate_product_id", "products")
    df = df[~dup_mask].copy()

    # price บางแถวเป็น string มี comma คั่นหลักพัน เช่น "1,299.00"
    df["price"] = pd.to_numeric(
        df["price"].astype("string").str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )
    df["category"] = df["category"].astype("string").str.strip().fillna(UNKNOWN)
    df.loc[df["category"] == "", "category"] = UNKNOWN
    df["product_name"] = df["product_name"].astype("string").str.strip().fillna(UNKNOWN)

    logging.info(
        "transform | products | kept=%d dropped_duplicates=%d price_unparsed=%d",
        len(df), int(dup_mask.sum()), int(df["price"].isna().sum())
    )
    return df[["product_id", "product_name", "category", "price"]], dup_rejects


def _clean_orders(raw_orders, valid_customer_ids, valid_product_ids):
    """
    คืน (orders ที่ผ่านกฎทุกข้อ, reject_frames)

    การตรวจ foreign key ทำ *ก่อน* กรอง status เพราะ order ที่อ้าง customer/product
    ที่ไม่มีจริงถือเป็นข้อมูลผิด ต้องบันทึกไว้ใน rejects ไม่ว่าจะ status ไหน
    (ถ้าตรวจทีหลัง ออเดอร์กำพร้าที่เป็น cancelled จะหายไปเงียบ ๆ)
    """
    df = raw_orders.copy()
    reject_frames = []

    dup_mask = df["order_id"].duplicated(keep="first")
    reject_frames.append(_tag_rejects(raw_orders[dup_mask], "duplicate_order_id", "orders"))
    df = df[~dup_mask]

    order_date = _parse_mixed_dates(df["order_date"])
    numeric = {c: pd.to_numeric(df[c], errors="coerce")
               for c in ["qty", "unit_price", "discount_pct"]}

    reasons = _combine_reasons({
        "qty_not_positive": numeric["qty"].isna() | (numeric["qty"] <= 0),
        "unit_price_not_positive": numeric["unit_price"].isna() | (numeric["unit_price"] <= 0),
        "discount_pct_out_of_range": (
            numeric["discount_pct"].isna()
            | (numeric["discount_pct"] < 0)
            | (numeric["discount_pct"] > 100)
        ),
        "invalid_order_date": order_date.isna(),
        "unknown_customer_id": ~df["customer_id"].isin(valid_customer_ids),
        "unknown_product_id": ~df["product_id"].isin(valid_product_ids),
    }, df.index)

    bad_mask = reasons != ""
    # รายงาน rejects ด้วยค่าดิบจากไฟล์ต้นทาง เพื่อให้ตรวจย้อนหลังได้ว่าอะไรผิด
    reject_frames.append(_tag_rejects(raw_orders.loc[df.index[bad_mask]], reasons, "orders"))

    good = df[~bad_mask].copy()
    good["order_date"] = order_date[~bad_mask]
    good["status"] = good["status"].astype("string").str.strip().str.lower()
    for col, values in numeric.items():
        good[col] = values[~bad_mask]

    logging.info(
        "transform | orders | kept=%d dropped_duplicates=%d rule_rejects=%d",
        len(good), int(dup_mask.sum()), int(bad_mask.sum())
    )
    return good, reject_frames


def transform_data(raw):
    """
    ล้าง customers / products / orders, แยก record ที่ผิดกฎออกเป็น rejects,
    เก็บเฉพาะออเดอร์ paid/completed แล้ว join กับ master + คำนวณยอดขาย

    Return: (clean_customers, clean_products, sales, rejects)
    """
    customers, cust_rejects = _clean_customers(raw["customers"])
    products, prod_rejects = _clean_products(raw["products"])
    orders, order_reject_frames = _clean_orders(
        raw["orders"], set(customers["customer_id"]), set(products["product_id"])
    )

    reject_frames = [cust_rejects, prod_rejects, *order_reject_frames]

    # เก็บเฉพาะ paid/completed — เป็น business filter ไม่ใช่ข้อมูลผิด จึงไม่นับเป็น reject
    status_mask = orders["status"].isin(KEEP_STATUS)
    logging.info(
        "transform | status filter | kept=%d filtered_out=%d (%s)",
        int(status_mask.sum()), int((~status_mask).sum()),
        orders.loc[~status_mask, "status"].value_counts().to_dict(),
    )
    orders = orders[status_mask]

    # ออเดอร์กำพร้าถูกคัดออกไปแล้วใน _clean_orders จุดนี้จึง join ติดครบทุกแถว
    sales = (
        orders
        .merge(customers, on="customer_id", how="inner")
        .merge(products, on="product_id", how="inner")
    )
    assert len(sales) == len(orders), "join กับ master แล้วจำนวนแถวเปลี่ยน"

    sales["gross_amount"] = (sales["qty"] * sales["unit_price"]).round(2)
    sales["discount_amount"] = (sales["gross_amount"] * sales["discount_pct"] / 100).round(2)
    sales["sales_amount"] = (sales["gross_amount"] - sales["discount_amount"]).round(2)
    sales["order_date"] = sales["order_date"].dt.strftime("%Y-%m-%d")
    sales["qty"] = sales["qty"].astype(int)

    rejects = pd.concat(reject_frames, ignore_index=True, sort=False)

    logging.info(
        "transform | done | sales_rows=%d total_sales=%.2f rejects=%d",
        len(sales), sales["sales_amount"].sum(), len(rejects)
    )
    logging.info(
        "transform | rejects by reason | %s",
        rejects["reject_reason"].value_counts().to_dict(),
    )

    sales = sales[[
        "order_id", "customer_id", "product_id", "order_date",
        "qty", "unit_price", "discount_pct",
        "gross_amount", "discount_amount", "sales_amount",
    ]]

    return customers, products, sales, rejects
