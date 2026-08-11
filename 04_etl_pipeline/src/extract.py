import json
import logging
import sqlite3
import pandas as pd
from .config import RAW_DIR, SOURCE_DB

def extract_data():
    """
    Extract data from:
      - customers.csv
      - orders.csv
      - products.json
      - stores table in store.db
    Return a dictionary of DataFrames.
    """
    customers = pd.read_csv(RAW_DIR / "customers.csv")
    orders = pd.read_csv(RAW_DIR / "orders.csv")

    with open(RAW_DIR / "products.json", encoding="utf-8") as f:
        products = pd.json_normalize(json.load(f))

    with sqlite3.connect(SOURCE_DB) as conn:
        stores = pd.read_sql("SELECT * FROM stores", conn)

    raw = {
        "customers": customers,
        "orders": orders,
        "products": products,
        "stores": stores,
    }

    for name, df in raw.items():
        logging.info(
            "extract | %s | shape=%s | columns=%s",
            name, df.shape, list(df.columns)
        )

    return raw
