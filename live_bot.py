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
        r = req.get(f"{DASHBOARD_URL}/api/scan", timeout=15)
        data = r.json()
        if not data.get('success'):
            return None, 0
        for coin in data.get('coins', []):
            symbol   = coin['symbol']
            score    = coin.get('score', 0)
            if score < MIN_SCORE:
                break  # list is sorted, no point continuing
            ccxt_sym = symbol[:-4] + '/USDT'
            # verify this coin is actually tradeable on testnet right now
            try:
                ohlcv = exchange.fetch_ohlcv(ccxt_sym, INTERVAL, limit=5)
                if not ohlcv or len(ohlcv) < 2:
                    print(f"  ⚠️  {ccxt_sym} has no candle data — skipping")
                    continue
                last_price = float(ohlcv[-1][4])
                if last_price <= 0:
                    print(f"  ⚠️  {ccxt_sym} price is $0 — skipping")
                    continue
            except Exception as e:
                print(f"  ⚠️  {ccxt_sym} not fetchable: {e} — skipping")
                continue
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
# POST COMPLETED TRADE TO DASHBOARD
# ============================================================
def post_trade(entry_price, exit_price, amount, reason):
    try:
        pnl_usdt = round((exit_price - entry_price) * amount, 4)
        pnl_pct  = round((exit_price - entry_price) / entry_price * 100, 2)
        req.post("http://localhost:5000/api/trades", json={
            'coin':        coin,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'amount':      amount,
            'pnl_usdt':    pnl_usdt,
            'pnl_pct':     pnl_pct,
            'reason':      reason,
        }, timeout=3)
        print(f"  📝 Trade logged: PnL ${pnl_usdt:+.4f} ({pnl_pct:+.2f}%) | {reason}")
    except Exception as e:
        print(f"  ⚠️ Could not log trade: {e}")

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
    # Scan ALL non-USDT balances above $1 value to find any held coin
    print("  🔍 Checking existing balances...")
    usdt_check, full_bal_check = get_balance()
    in_position   = False
    bought_amount = 0
    entry_price   = 0

    if isinstance(full_bal_check, dict):
        for currency, bal_info in full_bal_check.items():
            if currency in ('USDT', 'USD', 'BNB'):
                continue
            free = round(float(bal_info.get('free', 0)), 6) if isinstance(bal_info, dict) else 0
            if free <= 0:
                continue
            # fetch price to check if it's worth more than $1
            try:
                ticker = req.get(
                    f"https://api.binance.com/api/v3/ticker/price?symbol={currency}USDT",
                    timeout=5
                ).json()
                coin_price = float(ticker.get('price', 0))
                value_usdt = free * coin_price
                if value_usdt > 1.0:
                    SYMBOL        = f"{currency}/USDT"
                    in_position   = True
                    bought_amount = free
                    print(f"  ⚠️  Resuming with existing position: {free} {currency} (≈${value_usdt:.2f})")
                    print(f"  ⚠️  Entry price unknown — SL/TP disabled until next fresh buy")
                    break
            except Exception:
                continue

    if not in_position:
        print("  ✅ No existing position found — starting fresh")
    else:
        # Verify the resumed coin is actually fetchable — if not, sell it immediately
        try:
            ohlcv = exchange.fetch_ohlcv(SYMBOL, INTERVAL, limit=5)
            if not ohlcv or len(ohlcv) < 2 or float(ohlcv[-1][4]) <= 0:
                print(f"  ❌ {SYMBOL} is not fetchable on testnet — auto-selling stuck position")
                _, full_bal = get_balance()
                base = SYMBOL.split('/')[0]
                stuck_amt = round(float(full_bal.get(base, {}).get('free', 0)), 6)
                if stuck_amt > 0:
                    order = place_order("sell", SYMBOL, stuck_amt)
                    if order:
                        print(f"  ✅ Auto-sold {stuck_amt} {base} — starting fresh")
                        in_position   = False
                        bought_amount = 0
                        entry_price   = 0
                        SYMBOL        = "BTC/USDT"
                    else:
                        print(f"  ⚠️  Auto-sell failed — bot will hold but can't trade")
        except Exception as e:
            print(f"  ⚠️  Could not verify {SYMBOL}: {e}")
    last_scan = 0

    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ── Scanner: pick best coin every SCAN_EVERY seconds ──
            if time.time() - last_scan > SCAN_EVERY:
                if in_position:
                    print(f"  📌 In position on {SYMBOL} — skipping scanner until sold")
                else:
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
                    post_trade(SYMBOL, entry_price, price, bought_amount, "STOP_LOSS")
                    in_position = False
                    entry_price = 0
                    bought_amount = 0

            # ── TAKE PROFIT ──
            elif in_position and entry_price > 0 and price >= tp_price:
                print(f"  💰 TAKE PROFIT HIT — selling at ${price} (entry ${entry_price}, gain {pnl_pct:+.2f}%)")
                order = place_order("sell", SYMBOL, base_bal)
                if order:
                    post_trade(SYMBOL, entry_price, price, bought_amount, "TAKE_PROFIT")
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
                        post_trade(SYMBOL, entry_price, price, bought_amount, "SIGNAL")
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