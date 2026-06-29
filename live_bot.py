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
MAX_POSITIONS   = 3        # maximum simultaneous open trades

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
def get_best_coins(held_symbols, slots_available):
    """Return up to `slots_available` coins from scanner, skipping already-held ones."""
    results = []
    try:
        r = req.get(f"{DASHBOARD_URL}/api/scan", timeout=15)
        data = r.json()
        if not data.get('success'):
            return results
        for coin in data.get('coins', []):
            if len(results) >= slots_available:
                break
            symbol = coin['symbol']
            score  = coin.get('score', 0)
            if score < MIN_SCORE:
                break  # sorted descending — no point continuing
            ccxt_sym = symbol[:-4] + '/USDT'
            if ccxt_sym in held_symbols:
                continue  # already in a position on this coin
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
            results.append((ccxt_sym, score))
    except Exception as e:
        print(f"  ⚠️  Scanner unavailable: {e}")
    return results

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
def post_trade(coin, entry_price, exit_price, amount, reason):
    try:
        pnl_usdt = round((exit_price - entry_price) * amount, 4)
        pnl_pct  = round((exit_price - entry_price) / entry_price * 100, 2)
        req.post(f"{DASHBOARD_URL}/api/trades", json={
            'coin':        coin,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'amount':      amount,
            'pnl_usdt':    pnl_usdt,
            'pnl_pct':     pnl_pct,
            'reason':      reason,
        }, timeout=3)
        print(f"  📝 Trade logged: {coin} PnL ${pnl_usdt:+.4f} ({pnl_pct:+.2f}%) | {reason}")
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
def push_status(positions, signal, score, rsi, price, usdt):
    try:
        symbols_str = ', '.join(p['symbol'] for p in positions) if positions else '—'
        in_pos      = len(positions) > 0
        req.post(f"{DASHBOARD_URL}/api/bot/update", json={
            'symbol':       symbols_str,
            'in_position':  in_pos,
            'last_signal':  signal,
            'last_rsi':     rsi,
            'last_price':   price,
            'usdt_balance': usdt,
            'btc_balance':  len(positions),   # reuse field: shows open position count
            'log_entry':    f"{signal} | Score {score}/100 | RSI {rsi} | ${price} | {len(positions)}/{MAX_POSITIONS} slots",
        }, timeout=2)
    except Exception:
        pass

# ============================================================
# MAIN LOOP
# ============================================================
def run():
    print("\n🤖 Live Trading Bot Started — Phase 9 (Multi-Coin)")
    print("=" * 55)
    print(f"  Interval     : {INTERVAL}")
    print(f"  Min Score    : {MIN_SCORE}/100 to enter trade")
    print(f"  RSI Gate     : Buy < {RSI_OVERSOLD} | Sell > {RSI_OVERBOUGHT}")
    print(f"  Check Every  : {CHECK_EVERY}s")
    print(f"  Scan Every   : {SCAN_EVERY}s")
    print("=" * 55)

    # positions = list of dicts: {symbol, entry_price, amount, sl_price, tp_price}
    positions = []

    # ── Startup: resume any existing holdings ──
    print("  🔍 Checking existing balances...")
    usdt_check, full_bal_check = get_balance()

    STABLECOINS = {'USDT','USDC','BUSD','TUSD','DAI','USDP','FDUSD','USD'}

    if isinstance(full_bal_check, dict):
        for currency, bal_info in full_bal_check.items():
            if len(positions) >= MAX_POSITIONS:
                print(f"  📌 Max {MAX_POSITIONS} resume slots filled — ignoring remaining balances")
                break
            if currency in STABLECOINS or currency in ('BNB',):
                continue
            free = round(float(bal_info.get('free', 0)), 6) if isinstance(bal_info, dict) else 0
            if free <= 0:
                continue
            try:
                ticker = req.get(
                    f"https://api.binance.com/api/v3/ticker/price?symbol={currency}USDT",
                    timeout=5
                ).json()
                coin_price = float(ticker.get('price', 0))
                value_usdt = free * coin_price
                if value_usdt < 10.0:          # ignore dust — raised from $1 to $10
                    continue
                ccxt_sym = f"{currency}/USDT"
                try:
                    ohlcv = exchange.fetch_ohlcv(ccxt_sym, INTERVAL, limit=5)
                    if not ohlcv or len(ohlcv) < 2 or float(ohlcv[-1][4]) <= 0:
                        raise ValueError("no data")
                    positions.append({
                        'symbol':      ccxt_sym,
                        'entry_price': 0,
                        'amount':      free,
                        'sl_price':    0,
                        'tp_price':    0,
                    })
                    print(f"  ⚠️  Resumed: {free} {currency} (≈${value_usdt:.2f}) — SL/TP disabled until sold")
                except Exception:
                    print(f"  ⚠️  {ccxt_sym} not fetchable on testnet — skipping (not auto-selling)")
            except Exception:
                continue

    if not positions:
        print("  ✅ No existing positions — starting fresh")
    else:
        print(f"  📌 Resumed {len(positions)} position(s): {[p['symbol'] for p in positions]}")

    last_scan = 0

    while True:
        try:
            now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            usdt, full_bal = get_balance()
            held_symbols   = [p['symbol'] for p in positions]
            slots_free     = MAX_POSITIONS - len(positions)

            # ── Scanner: fill empty slots every SCAN_EVERY seconds ──
            if time.time() - last_scan > SCAN_EVERY:
                if slots_free <= 0:
                    print(f"  📌 All {MAX_POSITIONS} slots filled — skipping scanner")
                else:
                    candidates = get_best_coins(held_symbols, slots_free)
                    if candidates:
                        for ccxt_sym, best_score in candidates:
                            if usdt < TRADE_USDT:
                                print(f"  ⚠️  Not enough USDT for new position (have ${usdt})")
                                break
                            base_cur     = ccxt_sym.split('/')[0]
                            _, cur_price = get_rsi(ccxt_sym)
                            if cur_price <= 0:
                                continue
                            trade_amount = round(TRADE_USDT / cur_price, 6)
                            print(f"\n  🟢 BUYING ${TRADE_USDT} of {base_cur} ({trade_amount}) at ${cur_price} (Score {best_score})")
                            order = place_order("buy", ccxt_sym, trade_amount)
                            if order:
                                sl = round(cur_price * (1 - STOP_LOSS_PCT   / 100), 4)
                                tp = round(cur_price * (1 + TAKE_PROFIT_PCT / 100), 4)
                                positions.append({
                                    'symbol':      ccxt_sym,
                                    'entry_price': cur_price,
                                    'amount':      trade_amount,
                                    'sl_price':    sl,
                                    'tp_price':    tp,
                                })
                                usdt -= TRADE_USDT   # optimistic deduction
                                print(f"  📊 SL: ${sl} | TP: ${tp}")
                    else:
                        print(f"  ⏳ No qualifying coins found (need score ≥ {MIN_SCORE})")
                last_scan = time.time()

            # ── Print header ──
            print(f"\n⏰ {now}")
            print(f"  Slots    : {len(positions)}/{MAX_POSITIONS} open | USDT free: ${usdt}")

            # ── Check each open position ──
            last_score, last_signal, last_rsi, last_price = 0, 'HOLD', 0, 0
            to_close = []   # collect positions to remove after iteration

            for pos in positions:
                sym          = pos['symbol']
                entry        = pos['entry_price']
                amt          = pos['amount']
                sl           = pos['sl_price']
                tp           = pos['tp_price']
                base_cur     = sym.split('/')[0]

                score, sig_signal = get_score(sym)
                rsi, price        = get_rsi(sym)
                base_bal = round(full_bal.get(base_cur, {}).get('free', 0), 6) if isinstance(full_bal, dict) else 0

                last_score, last_signal, last_rsi, last_price = score, sig_signal, rsi, price

                pnl_str = ''
                if entry > 0:
                    pnl_pct = round((price - entry) / entry * 100, 2)
                    pnl_str = f" | P&L: {pnl_pct:+.2f}%"

                print(f"  [{sym}] Score:{score} RSI:{rsi} ${price}{pnl_str}")

                # ── STOP LOSS ──
                if entry > 0 and price > 0 and price <= sl:
                    print(f"    🛑 STOP LOSS — selling {sym} at ${price}")
                    order = place_order("sell", sym, base_bal)
                    if order:
                        post_trade(sym, entry, price, amt, "STOP_LOSS")
                        to_close.append(pos)

                # ── TAKE PROFIT ──
                elif entry > 0 and price > 0 and price >= tp:
                    print(f"    💰 TAKE PROFIT — selling {sym} at ${price}")
                    order = place_order("sell", sym, base_bal)
                    if order:
                        post_trade(sym, entry, price, amt, "TAKE_PROFIT")
                        to_close.append(pos)

                # ── SIGNAL SELL ──
                elif score < 30 or rsi > RSI_OVERBOUGHT:
                    print(f"    🔴 SIGNAL SELL — {sym} score:{score} rsi:{rsi}")
                    order = place_order("sell", sym, base_bal)
                    if order:
                        if entry > 0:
                            post_trade(sym, entry, price, amt, "SIGNAL")
                        else:
                            print(f"    ⚠️  Trade not logged — entry price unknown (resumed position)")
                        to_close.append(pos)

                else:
                    print(f"    ⏸️  Holding {sym}")

            # Remove closed positions
            for pos in to_close:
                positions.remove(pos)

            if not positions:
                print(f"  ⏸️  No open positions — waiting for scanner")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            last_score, last_signal, last_rsi, last_price = 0, 'HOLD', 0, 0

        # ── Push status to dashboard ──
        push_status(positions, last_signal, last_score, last_rsi, last_price, usdt)

        print(f"  💤 Sleeping {CHECK_EVERY}s...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    run()