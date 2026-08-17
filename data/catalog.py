"""
data/catalog.py
---------------
Loads the sneaker catalog from sneakerdata.json at import time.

The catalog contains 1 668 sneakers with real StockX market data:
  retail_price, market_value, lowest_ask, highest_bid,
  last_sale, deadstock_sold, sales_this_period, release_date

SNEAKER_CATALOG is a plain dict keyed by sneaker name — the same
interface all agents expect.

USER_BUDGETS and USER_SNEAKER_COLLECTION remain as CLI/eval fallbacks.
In the web app, user data comes from the SQLite database (database.py).
"""

import json
import os

_HERE      = os.path.dirname(__file__)
_DATA_PATH = os.path.join(_HERE, "sneakerdata.json")

with open(_DATA_PATH, encoding="utf-8") as _f:
    SNEAKER_CATALOG: dict = json.load(_f)


# ─────────────────────────────────────────────────────────────────────────────
# CLI / eval fallbacks  (not used in web traffic)
# ─────────────────────────────────────────────────────────────────────────────

USER_BUDGETS: dict[str, float] = {
    "john":  300.00,
    "alice": 500.00,
    "demo":  400.00,
}

USER_SNEAKER_COLLECTION: dict[str, list[str]] = {
    "john": [
        "Nike Air Force 1 Low White",
        "Jordan 1 Retro High OG Bred",
        "Nike Dunk Low Retro White Black",
    ],
    "alice": [
        "New Balance 550 White Green",
        "Adidas Yeezy Boost 350 V2 Zebra",
        "Jordan 4 Retro Military Black",
        "Nike Air Max 90 White",
    ],
    "demo": [],
}
