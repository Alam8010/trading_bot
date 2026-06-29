import os
import requests
import pandas as pd
import numpy as np
import ta
from flask import Flask, render_template, jsonify, request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
TESTNET_API_KEY    = os.getenv("API_KEY")
TESTNET_API_SECRET = os.getenv("API_SECRET")

# ============================================================
# SCANNER CONSTANTS
# ============================================================
STABLECOINS      = {'USDC','BUSD','DAI','TUSD','USDP','FDUSD','PYUSD','UST','USDD','FRAX'}
BLOCKED_PATTERNS = ['UP','DOWN','BULL','BEAR','3L','3S','2L','2S']
_scan_cache      = {'data': None, 'meta': None, 'ts': None}
CACHE_SECONDS    = 300

# ============================================================
# FETCH DATA
# ============================================================
def fetch_data(symbol, interval, limit):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=10)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        "timestamp","open","high","low","close","volume",
        "close_time","quote_volume","trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    return df

# ============================================================
# CALCULATE INDICATORS
# ============================================================
def calculate_indicators(df, rsi_period=14):
    df["rsi"]       = ta.momentum.RSIIndicator(df["close"], window=rsi_period).rsi()
    macd            = ta.trend.MACD(df["close"])
    df["macd"]      = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    df["ma20"]      = df["close"].rolling(window=20).mean()
    df["ma50"]      = df["close"].rolling(window=50).mean()
    df["ma200"]     = df["close"].rolling(window=200).mean()
    bb              = ta.volatility.BollingerBands(df["close"])
    df["bb_upper"]  = bb.bollinger_hband()
    df["bb_lower"]  = bb.bollinger_lband()
    df["bb_mid"]    = bb.bollinger_mavg()
    df["volume_ma"] = df["volume"].rolling(window=20).mean()

    # Phase 5 indicators
    df["mfi"]            = ta.volume.MFIIndicator(
                               df["high"], df["low"], df["close"], df["volume"], window=14
                           ).money_flow_index()
    adx_ind              = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx"]            = adx_ind.adx()
    df["obv"]            = ta.volume.OnBalanceVolumeIndicator(
                               df["close"], df["volume"]
                           ).on_balance_volume()
    df["obv_ma"]         = df["obv"].rolling(window=5).mean()
    df["vwap"]           = ta.volume.VolumeWeightedAveragePrice(
                               df["high"], df["low"], df["close"], df["volume"], window=14
                           ).volume_weighted_average_price()
    df["supertrend_dir"] = _supertrend_direction(df)
    return df

# ============================================================
# GENERATE SIGNALS
# ============================================================
def generate_signals(df, rsi_oversold=30, rsi_overbought=70):
    df["signal"] = "HOLD"
    for i in range(1, len(df)):
        rsi         = df["rsi"].iloc[i]
        macd        = df["macd"].iloc[i]
        macd_signal = df["macd_signal"].iloc[i]
        macd_prev   = df["macd"].iloc[i-1]
        sig_prev    = df["macd_signal"].iloc[i-1]
        close       = df["close"].iloc[i]
        ma20        = df["ma20"].iloc[i]
        volume      = df["volume"].iloc[i]
        volume_ma   = df["volume_ma"].iloc[i]
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(ma20):
            continue
        rsi_os    = rsi < rsi_oversold
        rsi_ob    = rsi > rsi_overbought
        macd_up   = (macd > macd_signal) and (macd_prev < sig_prev)
        macd_down = (macd < macd_signal) and (macd_prev > sig_prev)
        above_ma20 = close > ma20
        below_ma20 = close < ma20
        high_vol  = volume > volume_ma if not pd.isna(volume_ma) else False
        if   rsi_os and macd_up and high_vol: df.loc[df.index[i], "signal"] = "STRONG_BUY"
        elif rsi_os and above_ma20:           df.loc[df.index[i], "signal"] = "BUY"
        elif rsi_ob and macd_down:            df.loc[df.index[i], "signal"] = "STRONG_SELL"
        elif rsi_ob and below_ma20:           df.loc[df.index[i], "signal"] = "SELL"
    return df

# ============================================================
# BACKTEST
# ============================================================
def backtest(df, initial_capital=1000, risk_per_trade=0.02):
    capital      = initial_capital
    position     = 0
    entry_price  = 0
    trades       = []
    equity_curve = [capital]
    for i in range(len(df)):
        signal = df["signal"].iloc[i]
        price  = df["close"].iloc[i]
        time   = df["timestamp"].iloc[i]
        if signal in ["BUY","STRONG_BUY"] and position == 0:
            position    = (capital * risk_per_trade) / price
            entry_price = price
            trades.append({"type":"BUY","price":round(price,2),"time":str(time),"capital":round(capital,2),"profit":0})
        elif signal in ["SELL","STRONG_SELL"] and position > 0:
            profit   = position * price - position * entry_price
            capital += profit
            trades.append({"type":"SELL","price":round(price,2),"time":str(time),"capital":round(capital,2),"profit":round(profit,2)})
            position = 0
        equity_curve.append(round(capital, 2))
    sell_trades  = [t for t in trades if t["type"] == "SELL"]
    winning      = [t for t in sell_trades if t["profit"] > 0]
    losing       = [t for t in sell_trades if t["profit"] <= 0]
    total_profit = round(capital - initial_capital, 2)
    win_rate     = round(len(winning)/len(sell_trades)*100, 1) if sell_trades else 0
    stats = {
        "initial_capital": initial_capital,
        "final_capital":   round(capital, 2),
        "total_profit":    total_profit,
        "total_trades":    len(sell_trades),
        "winning_trades":  len(winning),
        "losing_trades":   len(losing),
        "win_rate":        win_rate,
        "profit_pct":      round((total_profit / initial_capital) * 100, 2)
    }
    return trades, equity_curve, stats

# ============================================================
# SUPERTREND HELPER
# ============================================================
def _supertrend_direction(df, period=10, multiplier=3):
    """Returns Series: 1 = uptrend (BUY), -1 = downtrend (SELL)"""
    try:
        hl2   = (df['high'] + df['low']) / 2.0
        atr   = ta.volatility.AverageTrueRange(
                    df['high'], df['low'], df['close'], window=period
                ).average_true_range()
        ub    = (hl2 + multiplier * atr).values.copy()
        lb    = (hl2 - multiplier * atr).values.copy()
        close = df['close'].values
        n     = len(close)
        direction = np.ones(n)

        for i in range(1, n):
            if close[i-1] <= ub[i-1]:
                ub[i] = min(ub[i], ub[i-1])
            if close[i-1] >= lb[i-1]:
                lb[i] = max(lb[i], lb[i-1])
            if direction[i-1] == 1:
                direction[i] = 1 if close[i] >= lb[i] else -1
            else:
                direction[i] = -1 if close[i] <= ub[i] else 1

        return pd.Series(direction, index=df.index)
    except Exception:
        return pd.Series(0, index=df.index)

# ============================================================
# SCANNER FUNCTIONS
# ============================================================
def get_all_tickers():
    r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=15)
    data = r.json()
    if isinstance(data, dict):
        raise Exception(f"Binance error: {data.get('msg','Unknown')}")
    return data

def filter_coins(tickers):
    out = []
    for t in tickers:
        sym = t.get('symbol','')
        if not sym.endswith('USDT'):
            continue
        base = sym[:-4]
        if base in STABLECOINS or any(p in base for p in BLOCKED_PATTERNS):
            continue
        try:
            vol = float(t.get('quoteVolume', 0))
            chg = float(t.get('priceChangePercent', 0))
        except (ValueError, TypeError):
            continue
        if vol < 10_000_000 or abs(chg) < 0.5:
            continue
        out.append({
            'symbol':   sym,
            'price':    float(t.get('lastPrice', 0)),
            'change':   round(chg, 2),
            'volume_m': round(vol / 1_000_000, 1),
        })
    return sorted(out, key=lambda x: x['volume_m'], reverse=True)

def score_coin(df):
    if df is None or len(df) < 55:
        return 0, []
    score, tags = 0, []

    def safe(val, default=0):
        try:
            v = float(val)
            return default if pd.isna(v) else v
        except:
            return default

    r  = df.iloc[-1]
    p  = df.iloc[-2]

    rsi      = safe(r['rsi'],            50)
    mfi      = safe(r.get('mfi',   np.nan), 50)
    adx      = safe(r.get('adx',   np.nan),  0)
    obv      = safe(r.get('obv',   np.nan),  0)
    obv_ma   = safe(r.get('obv_ma',np.nan),  0)
    vwap     = safe(r.get('vwap',  np.nan),  0)
    st_dir   = safe(r.get('supertrend_dir', np.nan), 0)
    close    = safe(r['close'], 0)
    macd     = safe(r['macd'], 0)
    macd_sig = safe(r['macd_signal'], 0)
    macd_p   = safe(p['macd'], 0)
    sig_p    = safe(p['macd_signal'], 0)
    bb_low   = safe(r['bb_lower'], 0)
    bb_high  = safe(r['bb_upper'], 0)

    # 1. MFI — 15 pts
    if   mfi < 20: score += 15; tags.append('MFI Oversold 💰')
    elif mfi < 40: score += 10; tags.append('MFI Low')
    elif mfi > 80: score -= 10

    # 2. ADX — 15 pts
    if   adx > 40: score += 15; tags.append('Strong Trend ↗')
    elif adx > 25: score += 10; tags.append('ADX Trending')

    # 3. Supertrend — 15 pts
    if   st_dir == 1:  score += 15; tags.append('Supertrend ✅')
    elif st_dir == -1: score -= 10

    # 4. OBV — 15 pts
    if obv > obv_ma: score += 15; tags.append('OBV Rising 📈')
    else:            score -= 5

    # 5. BB Position — 15 pts
    bb_range = bb_high - bb_low
    if bb_range > 0:
        pos = (close - bb_low) / bb_range
        if   pos < 0.2:  score += 15; tags.append('Near BB Low 🎯')
        elif pos > 0.85: score -= 5

    # 6. VWAP — 15 pts
    if   vwap > 0 and close > vwap: score += 15; tags.append('Above VWAP')
    elif vwap > 0:                  score -= 5

    # 7. RSI — 10 pts
    if   rsi < 30: score += 10; tags.append('RSI Oversold')
    elif rsi < 45: score += 6;  tags.append('RSI Low')
    elif rsi > 70: score -= 5

    return max(0, min(100, score)), tags
    macd     = safe(r['macd'], 0)
    macd_sig = safe(r['macd_signal'], 0)
    macd_p   = safe(p['macd'], 0)
    sig_p    = safe(p['macd_signal'], 0)
    close    = safe(r['close'], 0)
    ma20     = safe(r['ma20'], close)
    vol      = safe(r['volume'], 0)
    vol_ma   = safe(r['volume_ma'], vol)
    bb_low   = safe(r['bb_lower'], 0)
    bb_high  = safe(r['bb_upper'], 0)

    # RSI (25 pts)
    if   rsi < 30: score += 25; tags.append('RSI Oversold')
    elif rsi < 45: score += 15; tags.append('RSI Low')
    elif rsi < 50: score += 8
    elif rsi > 70: score -= 10

    # MACD (30 pts)
    if   macd > macd_sig and macd_p <= sig_p: score += 30; tags.append('MACD Cross ⚡')
    elif macd > macd_sig:                     score += 15; tags.append('MACD Bullish')
    elif macd < macd_sig and macd_p >= sig_p: score -= 15

    # MA20 (20 pts)
    if close > ma20: score += 20; tags.append('Above MA20')

    # Volume (15 pts)
    if vol_ma > 0:
        ratio = vol / vol_ma
        if   ratio > 2.0: score += 15; tags.append('Vol Surge 🔥')
        elif ratio > 1.3: score += 8;  tags.append('High Vol')

    # Bollinger (10 pts)
    bb_range = bb_high - bb_low
    if bb_range > 0:
        pos = (close - bb_low) / bb_range
        if   pos < 0.2:  score += 10; tags.append('Near BB Low')
        elif pos > 0.85: score -= 5

    return max(0, min(100, score)), tags

def analyse_coin(coin, interval, limit):
    try:
        df = fetch_data(coin['symbol'], interval, limit)
        df = calculate_indicators(df)
        df = generate_signals(df)
        sc, tags = score_coin(df)
        r       = df.iloc[-1]
        rsi_val = r['rsi']
        return {
            'symbol':   coin['symbol'],
            'price':    coin['price'],
            'change':   coin['change'],
            'volume_m': coin['volume_m'],
            'score':    sc,
            'signal':   r['signal'],
            'rsi':      round(float(rsi_val), 1) if not pd.isna(rsi_val) else 0,
            'tags':     tags[:3],
        }
    except Exception:
        return None

def run_scan(interval='15m', limit=100, max_coins=50):
    tickers    = get_all_tickers()
    total_usdt = sum(1 for t in tickers if t.get('symbol','').endswith('USDT'))
    filtered   = filter_coins(tickers)
    total_q    = len(filtered)
    results    = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(analyse_coin, c, interval, limit): c for c in filtered[:max_coins]}
        for f in as_completed(futs):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                pass
    results.sort(key=lambda x: x['score'], reverse=True)
    return results, total_usdt, total_q

# ============================================================
# API ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/run", methods=["POST"])
def run_bot():
    try:
        cfg            = request.json or {}
        symbol         = cfg.get("symbol","BTCUSDT").upper()
        interval       = cfg.get("interval","15m")
        limit          = int(cfg.get("limit", 500))
        initial_cap    = float(cfg.get("initial_capital", 1000))
        risk           = float(cfg.get("risk_per_trade", 0.02))
        rsi_period     = int(cfg.get("rsi_period", 14))
        rsi_oversold   = float(cfg.get("rsi_oversold", 30))
        rsi_overbought = float(cfg.get("rsi_overbought", 70))

        df = fetch_data(symbol, interval, limit)
        df = calculate_indicators(df, rsi_period)
        df = generate_signals(df, rsi_oversold, rsi_overbought)
        trades, equity_curve, stats = backtest(df, initial_cap, risk)

        chart_data = {
            "timestamps":  df["timestamp"].astype(str).tolist(),
            "close":       df["close"].tolist(),
            "ma20":        df["ma20"].fillna("null").tolist(),
            "ma50":        df["ma50"].fillna("null").tolist(),
            "bb_upper":    df["bb_upper"].fillna("null").tolist(),
            "bb_lower":    df["bb_lower"].fillna("null").tolist(),
            "rsi":         df["rsi"].fillna("null").tolist(),
            "macd":        df["macd"].fillna("null").tolist(),
            "macd_signal": df["macd_signal"].fillna("null").tolist(),
            "macd_hist":   df["macd_hist"].fillna("null").tolist(),
            "volume":      df["volume"].tolist(),
            "volume_ma":   df["volume_ma"].fillna("null").tolist(),
            "signals":     df["signal"].tolist(),
        }
        buy_signals  = df[df["signal"].isin(["BUY","STRONG_BUY"])]
        sell_signals = df[df["signal"].isin(["SELL","STRONG_SELL"])]
        chart_data["buy_times"]   = buy_signals["timestamp"].astype(str).tolist()
        chart_data["buy_prices"]  = buy_signals["close"].tolist()
        chart_data["sell_times"]  = sell_signals["timestamp"].astype(str).tolist()
        chart_data["sell_prices"] = sell_signals["close"].tolist()

        current = {
            "price":  df["close"].iloc[-1],
            "rsi":    round(df["rsi"].iloc[-1], 2)  if not pd.isna(df["rsi"].iloc[-1])  else 0,
            "macd":   round(df["macd"].iloc[-1], 2) if not pd.isna(df["macd"].iloc[-1]) else 0,
            "signal": df["signal"].iloc[-1],
            "change": round(((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]) * 100, 3),
        }
        return jsonify({"success":True,"chart_data":chart_data,"trades":trades[-20:],"equity":equity_curve,"stats":stats,"current":current,"symbol":symbol})
    except Exception as e:
        return jsonify({"success":False,"error":str(e)}), 500

@app.route("/api/price/<symbol>")
def get_price(symbol):
    try:
        url  = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
        data = requests.get(url, timeout=5).json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route('/api/scan')
def api_scan():
    global _scan_cache
    try:
        now      = datetime.now()
        interval = request.args.get('interval','15m')
        force    = request.args.get('force','false') == 'true'

        if not force and _scan_cache['data'] and _scan_cache['ts']:
            age = (now - _scan_cache['ts']).seconds
            if age < CACHE_SECONDS:
                return jsonify({'success':True,'cached':True,'age':age,**_scan_cache['meta'],
                                'count':len(_scan_cache['data']),'coins':_scan_cache['data'],
                                'timestamp':str(_scan_cache['ts'])})

        results, total_usdt, total_q = run_scan(interval=interval)
        meta = {'total_usdt':total_usdt,'total_qualified':total_q}
        _scan_cache = {'data':results,'meta':meta,'ts':now}
        return jsonify({'success':True,'cached':False,'count':len(results),
                        'total_usdt':total_usdt,'total_qualified':total_q,
                        'coins':results,'timestamp':str(now)})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success':False,'error':str(e)}), 500

@app.route('/api/top')
def api_top():
    global _scan_cache
    try:
        if _scan_cache['data']:
            return jsonify({'success':True,'coin':_scan_cache['data'][0]})
        results, total_usdt, total_q = run_scan(max_coins=30)
        _scan_cache = {'data':results,'meta':{'total_usdt':total_usdt,'total_qualified':total_q},'ts':datetime.now()}
        return jsonify({'success':True,'coin':results[0] if results else None})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)}), 500

@app.route('/api/signals/<symbol>')
def api_signals(symbol):
    try:
        interval = request.args.get('interval', '15m')
        limit    = int(request.args.get('limit', 100))
        df = fetch_data(symbol.upper(), interval, limit)
        df = calculate_indicators(df)
        r  = df.iloc[-1]
        p  = df.iloc[-2]

        def safe(val, default=0):
            try:
                v = float(val)
                return default if pd.isna(v) else v
            except:
                return default

        rsi     = safe(r['rsi'], 50)
        mfi     = safe(r.get('mfi',   np.nan), 50)
        adx     = safe(r.get('adx',   np.nan), 0)
        obv     = safe(r.get('obv',   np.nan), 0)
        obv_ma  = safe(r.get('obv_ma',np.nan), 0)
        vwap    = safe(r.get('vwap',  np.nan), 0)
        st_dir  = safe(r.get('supertrend_dir', np.nan), 0)
        close   = safe(r['close'], 0)
        bb_low  = safe(r['bb_lower'], 0)
        bb_high = safe(r['bb_upper'], 0)
        macd    = safe(r['macd'], 0)
        macd_s  = safe(r['macd_signal'], 0)
        ma20    = safe(r['ma20'], close)
        volume  = safe(r['volume'], 0)
        vol_ma  = safe(r['volume_ma'], volume)

        bb_range = bb_high - bb_low
        bb_pos   = round((close - bb_low) / bb_range, 3) if bb_range > 0 else 0.5

        signals = [
            {
                'name':     'RSI',
                'category': 'Momentum',
                'value':    round(rsi, 1),
                'unit':     '',
                'score':    10 if rsi < 30 else (6 if rsi < 45 else (-5 if rsi > 70 else 0)),
                'max':      10,
                'status':   'oversold' if rsi < 30 else ('overbought' if rsi > 70 else 'neutral'),
                'label':    'Oversold 🔥' if rsi < 30 else ('Overbought ⚠️' if rsi > 70 else 'Neutral'),
            },
            {
                'name':     'MFI',
                'category': 'Momentum + Volume',
                'value':    round(mfi, 1),
                'unit':     '',
                'score':    15 if mfi < 20 else (10 if mfi < 40 else (-10 if mfi > 80 else 0)),
                'max':      15,
                'status':   'oversold' if mfi < 20 else ('overbought' if mfi > 80 else 'neutral'),
                'label':    'Money Oversold 💰' if mfi < 20 else ('Overbought' if mfi > 80 else 'Neutral'),
            },
            {
                'name':     'ADX',
                'category': 'Trend Strength',
                'value':    round(adx, 1),
                'unit':     '',
                'score':    15 if adx > 40 else (10 if adx > 25 else 0),
                'max':      15,
                'status':   'strong' if adx > 40 else ('trending' if adx > 25 else 'weak'),
                'label':    'Strong Trend ↗' if adx > 40 else ('Trending' if adx > 25 else 'No Trend'),
            },
            {
                'name':     'Supertrend',
                'category': 'Trend Direction',
                'value':    int(st_dir),
                'unit':     '',
                'score':    15 if st_dir == 1 else (-10 if st_dir == -1 else 0),
                'max':      15,
                'status':   'bullish' if st_dir == 1 else ('bearish' if st_dir == -1 else 'neutral'),
                'label':    'Uptrend ✅' if st_dir == 1 else ('Downtrend ❌' if st_dir == -1 else 'Neutral'),
            },
            {
                'name':     'OBV',
                'category': 'Volume Flow',
                'value':    round(obv, 0),
                'unit':     '',
                'score':    15 if obv > obv_ma else -5,
                'max':      15,
                'status':   'bullish' if obv > obv_ma else 'bearish',
                'label':    'Money Flowing In 📈' if obv > obv_ma else 'Money Flowing Out 📉',
            },
            {
                'name':     'BB Position',
                'category': 'Volatility',
                'value':    round(bb_pos * 100, 1),
                'unit':     '%',
                'score':    15 if bb_pos < 0.2 else (-5 if bb_pos > 0.85 else 0),
                'max':      15,
                'status':   'oversold' if bb_pos < 0.2 else ('overbought' if bb_pos > 0.85 else 'neutral'),
                'label':    'Near Band Bottom 🎯' if bb_pos < 0.2 else ('Near Band Top' if bb_pos > 0.85 else f'{round(bb_pos*100)}% of Band'),
            },
            {
                'name':     'VWAP',
                'category': 'Price Level',
                'value':    round(vwap, 4) if vwap > 0 else 0,
                'unit':     '',
                'score':    15 if (vwap > 0 and close > vwap) else (-5 if vwap > 0 else 0),
                'max':      15,
                'status':   'bullish' if (vwap > 0 and close > vwap) else 'bearish',
                'label':    'Price Above VWAP ✅' if (vwap > 0 and close > vwap) else 'Price Below VWAP ⚠️',
            },
        ]

        total_score = max(0, min(100, sum(s['score'] for s in signals)))

        overall = 'STRONG_BUY' if total_score >= 70 else \
                  'BUY'        if total_score >= 50 else \
                  'SELL'       if total_score <= 20 else \
                  'STRONG_SELL'if total_score <= 10 else 'HOLD'

        return jsonify({
            'success': True,
            'symbol':  symbol.upper(),
            'price':   round(close, 6),
            'score':   total_score,
            'signal':  overall,
            'signals': signals,
            'macd':    round(macd, 4),
            'macd_signal': round(macd_s, 4),
            'ma20':    round(ma20, 4),
            'volume':  round(volume, 0),
            'vol_ma':  round(vol_ma, 0),
            'timestamp': str(df['timestamp'].iloc[-1]),
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# TRADE HISTORY — saved to trades.json
# ============================================================
import json
from pathlib import Path

TRADES_FILE = Path("trades.json")

def _load_trades():
    if TRADES_FILE.exists():
        try:
            return json.loads(TRADES_FILE.read_text())
        except Exception:
            return []
    return []

def _save_trades(trades):
    TRADES_FILE.write_text(json.dumps(trades, indent=2))

@app.route('/api/trades', methods=['GET'])
def api_get_trades():
    try:
        trades = _load_trades()
        wins   = [t for t in trades if t.get('pnl_usdt', 0) > 0]
        losses = [t for t in trades if t.get('pnl_usdt', 0) <= 0]
        total_pnl = round(sum(t.get('pnl_usdt', 0) for t in trades), 4)
        win_rate  = round(len(wins) / len(trades) * 100, 1) if trades else 0
        return jsonify({
            'success': True,
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'trades': trades[-20:][::-1],   # last 20, newest first
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/trades', methods=['POST'])
def api_post_trade():
    try:
        data = request.json or {}
        required = {'coin', 'entry_price', 'exit_price', 'amount', 'pnl_usdt', 'pnl_pct', 'reason'}
        if not required.issubset(data):
            return jsonify({'success': False, 'error': 'Missing fields'}), 400
        trades = _load_trades()
        trade = {
            'id': len(trades) + 1,
            'coin': data['coin'],
            'entry_price': round(float(data['entry_price']), 6),
            'exit_price':  round(float(data['exit_price']),  6),
            'amount':      round(float(data['amount']),       6),
            'pnl_usdt':    round(float(data['pnl_usdt']),    4),
            'pnl_pct':     round(float(data['pnl_pct']),     2),
            'reason':      data['reason'],
            'timestamp':   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        trades.append(trade)
        _save_trades(trades)
        return jsonify({'success': True, 'trade': trade})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── Bot status shared state (written by live_bot, read by dashboard) ──
_bot_status = {
    'running':      False,
    'symbol':       'BTC/USDT',
    'in_position':  False,
    'last_signal':  'N/A',
    'last_rsi':     0,
    'last_price':   0,
    'usdt_balance': 0,
    'btc_balance':  0,
    'last_check':   None,
    'log':          [],   # last 50 entries
}

@app.route('/api/bot/status')
def api_bot_status():
    return jsonify({'success': True, **_bot_status})

@app.route('/api/bot/update', methods=['POST'])
def api_bot_update():
    """live_bot.py calls this every cycle to push its state to the dashboard."""
    global _bot_status
    try:
        data = request.json or {}
        _bot_status.update({k: v for k, v in data.items() if k != 'log'})
        if 'log_entry' in data:
            _bot_status['log'].insert(0, {
                'time':    datetime.now().strftime('%H:%M:%S'),
                'message': data['log_entry'],
            })
            _bot_status['log'] = _bot_status['log'][:50]  # keep last 50
        _bot_status['running']    = True
        _bot_status['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == "__main__":
    print("\n🤖 Trading Bot GUI Starting...")
    print("=" * 45)
    print("  Open your browser and go to:")
    print("  👉  http://localhost:5000")
    print("=" * 45)
    app.run(debug=False, port=5000)
    print("=" * 45)
    print("  Open your browser and go to:")
    print("  👉  http://localhost:5000")
    print("=" * 45)
    app.run(debug=False, port=5000)