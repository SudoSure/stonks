import os
import json
import time
from datetime import datetime, timezone
from typing import List

import requests
import alpaca_trade_api as tradeapi

FMP_URL = ""

FMP_API_KEY      = '' #os.getenv("FMP_API_KEY")
ALPACA_KEY_ID    = '' # os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET_KEY= ''#os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL  = '' #os.getenv("ALPACA_BASE_URL", "")

NAME_TO_TRACK = "" #os.getenv("NAME_TO_TRACK", "")
CAPITAL_PER_TRADE = 1000 #float(os.getenv("CAPITAL_PER_TRADE", "1000"))

STATE_FILE = "processed_trades.json"

HEADERS = {"User-Agent": "/1.0"}

api = tradeapi.REST(ALPACA_KEY_ID, ALPACA_SECRET_KEY, ALPACA_BASE_URL, api_version="v2")

def load_state() -> List[str]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return []

def save_state(trade_ids: List[str]):
    with open(STATE_FILE, "w") as f:
        json.dump(trade_ids, f, indent=2)

def fetch_latest_pelosi_trades() -> List[dict]:
    params = {"name": NAME_TO_TRACK, "apikey": FMP_API_KEY}
    resp = requests.get(FMP_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # FMP returns newest first. Keep only items that reference a valid ticker and amount.
    return [t for t in data if t.get("symbol")]

def get_market_price(symbol: str) -> float:
    quote = api.get_latest_trade(symbol)
    return quote.price

def calc_qty(price: float) -> int:
    return max(1, int(CAPITAL_PER_TRADE // price))

def place_order(symbol: str, side: str, qty: int, comment: str = "PelosiCopy"):
    api.submit_order(
        symbol=symbol,
        side=side,
        qty=qty,
        type="market",
        time_in_force="day",
        client_order_id=f"{comment}-{int(time.time())}"
    )
    print(f"[EXEC] {side.upper()} {qty} {symbol} @ mkt")

def replicate():
    processed = set(load_state())
    new_processed = set(processed)

    trades = fetch_latest_pelosi_trades()

    for t in trades:
        trade_id = t["transactionDate"] + t["symbol"] + t.get("type", "")
        if trade_id in processed:
            continue

        symbol = t["symbol"]
        side = "buy" if t["type"].lower().startswith("purchase") else "sell"

        try:
            price = get_market_price(symbol)
        except Exception as exc:
            print(f"[WARN] Could not get price for {symbol}: {exc}")
            continue

        qty = calc_qty(price)
        try:
            place_order(symbol, side, qty)
            new_processed.add(trade_id)
        except Exception as exc:
            print(f"[ERROR] Order failed for {symbol}: {exc}")

    if new_processed != processed:
        save_state(sorted(new_processed))

def market_open() -> bool:
    clock = api.get_clock()
    return clock.is_open

if __name__ == "__main__":
    print(" …")
    while True:
        if market_open():
            replicate()
        else:
            print("[INFO] Market closed — sleeping.")
        time.sleep(60 * 30)  # every 30 minutes
