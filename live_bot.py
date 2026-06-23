import ccxt
import time
import pandas as pd
import ta
from datetime import datetime
import os                          # ← ADD THIS
from dotenv import load_dotenv     # ← ADD THIS

load_dotenv()                      # ← ADD THIS (before line 10)
# ============================================================
# YOUR TESTNET KEYS — paste here
# ============================================================
API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# ============================================================
# SETTINGS
# ============================================================
SYMBOL         = "BTC/USDT"
INTERVAL       = "15m"
CANDLES        = 100
RSI_OVERSOLD   = 30
RSI_OVERBOUGHT = 70
TRADE_AMOUNT   = 0.001      # How much BTC per trade
CHECK_EVERY    = 60         # Seconds between each check

# ============================================================
# CONNECT TO BINANCE TESTNET
# ============================================================
exchange = ccxt.binance({
    "apiKey":    API_KEY,
    "secret":    API_SECRET,
    "enableRateLimit": True,
})
exchange.set_sandbox_mode(True)

# ============================================================
# FETCH CANDLES + CALCULATE INDICATORS
# ============================================================
def get_signals():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, INTERVAL, limit=CANDLES)
    df    = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
    df["close"] = df["close"].astype(float)

    df["rsi"]         = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd              = ta.trend.MACD(df["close"])
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["ma20"]        = df["close"].rolling(20).mean()

    last             = df.iloc[-1]
    prev             = df.iloc[-2]
    rsi              = last["rsi"]
    close            = last["close"]
    macd_cross_up    = (last["macd"] > last["macd_signal"]) and (prev["macd"] < prev["macd_signal"])
    macd_cross_down  = (last["macd"] < last["macd_signal"]) and (prev["macd"] > prev["macd_signal"])
    above_ma20       = close > last["ma20"]

    if rsi < RSI_OVERSOLD and macd_cross_up:
        signal = "STRONG_BUY"
    elif rsi < RSI_OVERSOLD and above_ma20:
        signal = "BUY"
    elif rsi > RSI_OVERBOUGHT and macd_cross_down:
        signal = "STRONG_SELL"
    elif rsi > RSI_OVERBOUGHT and not above_ma20:
        signal = "SELL"
    else:
        signal = "HOLD"

    return signal, round(rsi, 2), round(close, 2)

# ============================================================
# GET BALANCE
# ============================================================
def get_balance():
    balance = exchange.fetch_balance()
    usdt    = balance["USDT"]["free"]
    btc     = balance["BTC"]["free"]
    return round(usdt, 2), round(btc, 6)

# ============================================================
# PLACE ORDER
# ============================================================
def place_order(side, amount):
    try:
        order = exchange.create_market_order(SYMBOL, side, amount)
        print(f"  ✅ Order placed: {side} {amount} BTC")
        print(f"  Order ID: {order['id']}")
        return order
    except Exception as e:
        print(f"  ❌ Order failed: {e}")
        return None

# ============================================================
# MAIN LOOP
# ============================================================
def run():
    print("\n🤖 Live Trading Bot Started (Binance Testnet)")
    print("=" * 50)
    print(f"  Symbol       : {SYMBOL}")
    print(f"  Interval     : {INTERVAL}")
    print(f"  Trade Amount : {TRADE_AMOUNT} BTC")
    print(f"  Check Every  : {CHECK_EVERY} seconds")
    print("=" * 50)

    in_position = False  # Track if we hold BTC

    while True:
        try:
            now              = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            signal, rsi, price = get_signals()
            usdt, btc        = get_balance()

            print(f"\n⏰ {now}")
            print(f"  Price  : ${price:,}")
            print(f"  RSI    : {rsi}")
            print(f"  Signal : {signal}")
            print(f"  Balance: ${usdt} USDT | {btc} BTC")

            # ── BUY ──
            if signal in ["BUY", "STRONG_BUY"] and not in_position:
                if usdt >= price * TRADE_AMOUNT:
                    print(f"  🟢 BUYING {TRADE_AMOUNT} BTC at ${price}")
                    order = place_order("buy", TRADE_AMOUNT)
                    if order:
                        in_position = True
                else:
                    print(f"  ⚠️  Not enough USDT to buy")

            # ── SELL ──
            elif signal in ["SELL", "STRONG_SELL"] and in_position:
                if btc >= TRADE_AMOUNT:
                    print(f"  🔴 SELLING {TRADE_AMOUNT} BTC at ${price}")
                    order = place_order("sell", TRADE_AMOUNT)
                    if order:
                        in_position = False
                else:
                    print(f"  ⚠️  Not enough BTC to sell")

            else:
                print(f"  ⏸️  Holding...")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        print(f"  💤 Sleeping {CHECK_EVERY}s until next check...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    run()