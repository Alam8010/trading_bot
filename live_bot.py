import ccxt
import time
import pandas as pd
import ta
import requests as req
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# SETTINGS
# ============================================================
API_KEY        = os.getenv("API_KEY")
API_SECRET     = os.getenv("API_SECRET")

INTERVAL       = "15m"
CANDLES        = 100
TRADE_USDT     = 15      # spend $15 per trade (safely above $10 minimum)
CHECK_EVERY    = 15       # seconds between each trading check
SCAN_EVERY     = 300      # seconds between scanner calls (5 min)
MIN_SCORE       = 40       # minimum 7-signal score to consider buying
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 70
STOP_LOSS_PCT   = 5.0      # sell if price drops 5% from entry
TAKE_PROFIT_PCT = 8.0      # sell if price rises 8% from entry
DASHBOARD_URL   = "http://localhost:5000"

# ============================================================
# CONNECT TO BINANCE TESTNET
# ============================================================
exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
})
exchange.set_sandbox_mode(True)

# ============================================================
# GET BEST COIN FROM SCANNER
# ============================================================
def get_best_coin():
    try:
        r = req.get(f"{DASHBOARD_URL}/api/top", timeout=10)
        data = r.json()
        if data.get('success') and data.get('coin'):
            coin = data['coin']
            symbol = coin['symbol']          # e.g. "AAVEUSDT"
            score  = coin.get('score', 0)
            # convert Binance symbol to ccxt format: AAVEUSDT → AAVE/USDT
            ccxt_sym = symbol[:-4] + '/USDT'
            return ccxt_sym, score
    except Exception as e:
        print(f"  ⚠️  Scanner unavailable: {e}")
    return None, 0

# ============================================================
# GET 7-SIGNAL SCORE FOR CURRENT SYMBOL
# ============================================================
def get_score(symbol):
    try:
        # ccxt format AAVE/USDT → Binance format AAVEUSDT
        binance_sym = symbol.replace('/', '')
        r = req.get(f"{DASHBOARD_URL}/api/signals/{binance_sym}?interval={INTERVAL}", timeout=10)
        data = r.json()
        if data.get('success'):
            return data.get('score', 0), data.get('signal', 'HOLD')
    except Exception as e:
        print(f"  ⚠️  Signals unavailable: {e}")
    return 0, 'HOLD'

# ============================================================
# FETCH CANDLES + RSI (for confirmation)
# ============================================================
def get_rsi(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, INTERVAL, limit=CANDLES)
        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
        df["close"] = df["close"].astype(float)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        last = df.iloc[-1]
        return round(last["rsi"], 2), round(last["close"], 2)
    except Exception as e:
        print(f"  ⚠️  RSI fetch error: {e}")
        return 50, 0

# ============================================================
# GET BALANCE
# ============================================================
def get_balance():
    try:
        balance = exchange.fetch_balance()
        usdt = balance["USDT"]["free"]
        # get base currency balance (e.g. AAVE, BTC, ETH)
        return round(usdt, 2), balance
    except Exception as e:
        print(f"  ⚠️  Balance error: {e}")
        return 0, {}

# ============================================================
# PLACE ORDER
# ============================================================
def place_order(side, symbol, amount):
    try:
        order = exchange.create_market_order(symbol, side, amount)
        print(f"  ✅ Order placed: {side} {amount} {symbol}")
        print(f"  Order ID: {order['id']}")
        return order
    except Exception as e:
        print(f"  ❌ Order failed: {e}")
        return None

# ============================================================
# PUSH STATUS TO DASHBOARD
# ============================================================
def push_status(symbol, in_position, signal, score, rsi, price, usdt, base_bal):
    try:
        req.post(f"{DASHBOARD_URL}/api/bot/update", json={
            'symbol':       symbol,
            'in_position':  in_position,
            'last_signal':  signal,
            'last_rsi':     rsi,
            'last_price':   price,
            'usdt_balance': usdt,
            'btc_balance':  base_bal,
            'log_entry':    f"{signal} | Score {score}/100 | RSI {rsi} | ${price:,} | {'IN' if in_position else 'OUT'}",
        }, timeout=2)
    except Exception:
        pass

# ============================================================
# MAIN LOOP
# ============================================================
def run():
    print("\n🤖 Live Trading Bot Started — Phase 7 (Scanner-Driven)")
    print("=" * 55)
    print(f"  Interval     : {INTERVAL}")
    print(f"  Min Score    : {MIN_SCORE}/100 to enter trade")
    print(f"  RSI Gate     : Buy < {RSI_OVERSOLD} | Sell > {RSI_OVERBOUGHT}")
    print(f"  Check Every  : {CHECK_EVERY}s")
    print(f"  Scan Every   : {SCAN_EVERY}s")
    print("=" * 55)

    SYMBOL      = "BTC/USDT"   # default, scanner will override
    # Check if we already hold a position from a previous run
    print("  🔍 Checking existing balances...")
    usdt_check, full_bal_check = get_balance()
    base_check = SYMBOL.split('/')[0]
    held = round(full_bal_check.get(base_check, {}).get('free', 0), 6) if isinstance(full_bal_check, dict) else 0

    if held > 0.001:
        in_position   = True
        bought_amount = held
        entry_price   = 0    # unknown since we restarted — SL/TP won't trigger until next buy
        print(f"  ⚠️  Resuming with existing position: {held} {base_check}")
        print(f"  ⚠️  Entry price unknown — SL/TP disabled until next fresh buy")
    else:
        in_position   = False
        bought_amount = 0
        entry_price   = 0

    last_scan = 0

    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ── Scanner: pick best coin every SCAN_EVERY seconds ──
            if time.time() - last_scan > SCAN_EVERY:
                best_sym, best_score = get_best_coin()
                if best_sym and best_score >= MIN_SCORE:
                    if best_sym != SYMBOL:
                        print(f"\n  🔄 Switching to {best_sym} (score {best_score}/100)")
                        SYMBOL = best_sym
                    else:
                        print(f"  ✅ Staying on {SYMBOL} (score {best_score}/100)")
                else:
                    print(f"  ⏳ No coin above {MIN_SCORE} score — staying on {SYMBOL}")
                last_scan = time.time()

            # ── Get current signal score + RSI ──
            score, sig_signal = get_score(SYMBOL)
            rsi, price        = get_rsi(SYMBOL)
            usdt, full_bal    = get_balance()

            # base currency balance (e.g. AAVE balance if watching AAVE/USDT)
            base_currency = SYMBOL.split('/')[0]
            base_bal      = round(full_bal.get(base_currency, {}).get('free', 0), 6) if isinstance(full_bal, dict) else 0

            print(f"\n⏰ {now}")
            print(f"  Watching : {SYMBOL}")
            print(f"  Score    : {score}/100  →  {sig_signal}")
            print(f"  RSI      : {rsi}   Price: ${price:,}")
            print(f"  Balance  : ${usdt} USDT | {base_bal} {base_currency}")

            # calculate how much coin to buy for $15
            trade_amount = round(TRADE_USDT / price, 6) if price > 0 else 0

            # ── Calculate SL/TP prices ──
            sl_price = round(entry_price * (1 - STOP_LOSS_PCT / 100), 4) if entry_price > 0 else 0
            tp_price = round(entry_price * (1 + TAKE_PROFIT_PCT / 100), 4) if entry_price > 0 else 0

            if in_position and entry_price > 0:
                pnl_pct = round((price - entry_price) / entry_price * 100, 2)
                print(f"  📊 Entry: ${entry_price} | SL: ${sl_price} | TP: ${tp_price} | P&L: {pnl_pct:+.2f}%")

            # ── STOP LOSS ──
            if in_position and entry_price > 0 and price <= sl_price:
                print(f"  🛑 STOP LOSS HIT — selling at ${price} (entry ${entry_price}, loss {pnl_pct:+.2f}%)")
                order = place_order("sell", SYMBOL, base_bal)
                if order:
                    in_position = False
                    entry_price = 0
                    bought_amount = 0

            # ── TAKE PROFIT ──
            elif in_position and entry_price > 0 and price >= tp_price:
                print(f"  💰 TAKE PROFIT HIT — selling at ${price} (entry ${entry_price}, gain {pnl_pct:+.2f}%)")
                order = place_order("sell", SYMBOL, base_bal)
                if order:
                    in_position = False
                    entry_price = 0
                    bought_amount = 0

            # ── BUY logic: score >= MIN_SCORE AND RSI not overbought ──
            elif score >= MIN_SCORE and rsi < RSI_OVERBOUGHT and not in_position:
                if usdt >= TRADE_USDT:
                    print(f"  🟢 BUYING ${TRADE_USDT} of {base_currency} ({trade_amount} coins) at ${price} (Score {score})")
                    order = place_order("buy", SYMBOL, trade_amount)
                    if order:
                        in_position  = True
                        entry_price  = price
                        bought_amount = trade_amount
                else:
                    print(f"  ⚠️  Not enough USDT (need ${TRADE_USDT}, have ${usdt})")

            # ── SIGNAL SELL: score drops below 30 OR RSI overbought ──
            elif in_position and (score < 30 or rsi > RSI_OVERBOUGHT):
                print(f"  🔴 SIGNAL SELL at ${price} (Score {score}, RSI {rsi})")
                if base_bal >= trade_amount * 0.9:
                    order = place_order("sell", SYMBOL, base_bal)
                    if order:
                        in_position  = False
                        entry_price  = 0
                        bought_amount = 0
                else:
                    print(f"  ⚠️  Not enough {base_currency} to sell (have {base_bal})")

            else:
                status = "IN POSITION — holding" if in_position else "OUT — waiting for score ≥ 50"
                print(f"  ⏸️  {status}")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            score, sig_signal, rsi, price, usdt, base_bal = 0, 'HOLD', 0, 0, 0, 0

        # ── Push status to dashboard ──
        pnl_pct = round((price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0
        push_status(SYMBOL, in_position, sig_signal, score, rsi, price, usdt, base_bal)

        print(f"  💤 Sleeping {CHECK_EVERY}s...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    run()