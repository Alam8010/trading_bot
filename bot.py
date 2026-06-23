import requests
import pandas as pd
import numpy as np
import ta
import json
from flask import Flask, render_template, jsonify, request
from datetime import datetime

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
TESTNET_API_KEY    = "EX57iqp7n2eTE91jKsYZEw6hHQ5CXkcPCUlI9dzbRscFjPGwRO4Xo4Io6cpCs1KN"
TESTNET_API_SECRET = "0YCoFypbtuAHnKFbxodVriTMRGKkizwd7WIOp1SLYXIRxurD7hHqj8ugdBpFbc1h"
DEFAULT_CONFIG = {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "limit": 500,
    "initial_capital": 1000,
    "risk_per_trade": 0.02,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
}

# ============================================================
# FETCH DATA
# ============================================================
def fetch_data(symbol, interval, limit):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df

# ============================================================
# CALCULATE INDICATORS
# ============================================================
def calculate_indicators(df, rsi_period=14):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=rsi_period).rsi()

    macd = ta.trend.MACD(df["close"])
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()

    df["ma20"]  = df["close"].rolling(window=20).mean()
    df["ma50"]  = df["close"].rolling(window=50).mean()
    df["ma200"] = df["close"].rolling(window=200).mean()

    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()

    df["volume_ma"] = df["volume"].rolling(window=20).mean()
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

        rsi_os       = rsi < rsi_oversold
        rsi_ob       = rsi > rsi_overbought
        macd_up      = (macd > macd_signal) and (macd_prev < sig_prev)
        macd_down    = (macd < macd_signal) and (macd_prev > sig_prev)
        above_ma20   = close > ma20
        below_ma20   = close < ma20
        high_vol     = volume > volume_ma if not pd.isna(volume_ma) else False

        if rsi_os and macd_up and high_vol:
            df.loc[df.index[i], "signal"] = "STRONG_BUY"
        elif rsi_os and above_ma20:
            df.loc[df.index[i], "signal"] = "BUY"
        elif rsi_ob and macd_down:
            df.loc[df.index[i], "signal"] = "STRONG_SELL"
        elif rsi_ob and below_ma20:
            df.loc[df.index[i], "signal"] = "SELL"

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

        if signal in ["BUY", "STRONG_BUY"] and position == 0:
            position    = (capital * risk_per_trade) / price
            entry_price = price
            trades.append({
                "type": "BUY",
                "price": round(price, 2),
                "time": str(time),
                "capital": round(capital, 2),
                "profit": 0
            })

        elif signal in ["SELL", "STRONG_SELL"] and position > 0:
            sell_value = position * price
            profit     = sell_value - (position * entry_price)
            capital   += profit
            trades.append({
                "type": "SELL",
                "price": round(price, 2),
                "time": str(time),
                "capital": round(capital, 2),
                "profit": round(profit, 2)
            })
            position = 0

        equity_curve.append(round(capital, 2))

    sell_trades  = [t for t in trades if t["type"] == "SELL"]
    winning      = [t for t in sell_trades if t["profit"] > 0]
    losing       = [t for t in sell_trades if t["profit"] <= 0]
    total_profit = round(capital - initial_capital, 2)
    win_rate     = round(len(winning) / len(sell_trades) * 100, 1) if sell_trades else 0

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
# API ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/run", methods=["POST"])
def run_bot():
    try:
        cfg = request.json or {}
        symbol         = cfg.get("symbol", "BTCUSDT").upper()
        interval       = cfg.get("interval", "15m")
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

        # Prepare chart data
        chart_data = {
            "timestamps": df["timestamp"].astype(str).tolist(),
            "close":      df["close"].tolist(),
            "ma20":       df["ma20"].fillna("null").tolist(),
            "ma50":       df["ma50"].fillna("null").tolist(),
            "bb_upper":   df["bb_upper"].fillna("null").tolist(),
            "bb_lower":   df["bb_lower"].fillna("null").tolist(),
            "rsi":        df["rsi"].fillna("null").tolist(),
            "macd":       df["macd"].fillna("null").tolist(),
            "macd_signal":df["macd_signal"].fillna("null").tolist(),
            "macd_hist":  df["macd_hist"].fillna("null").tolist(),
            "volume":     df["volume"].tolist(),
            "volume_ma":  df["volume_ma"].fillna("null").tolist(),
            "signals":    df["signal"].tolist(),
        }

        buy_signals  = df[df["signal"].isin(["BUY","STRONG_BUY"])]
        sell_signals = df[df["signal"].isin(["SELL","STRONG_SELL"])]

        chart_data["buy_times"]   = buy_signals["timestamp"].astype(str).tolist()
        chart_data["buy_prices"]  = buy_signals["close"].tolist()
        chart_data["sell_times"]  = sell_signals["timestamp"].astype(str).tolist()
        chart_data["sell_prices"] = sell_signals["close"].tolist()

        # Current market info
        current = {
            "price": df["close"].iloc[-1],
            "rsi":   round(df["rsi"].iloc[-1], 2) if not pd.isna(df["rsi"].iloc[-1]) else 0,
            "macd":  round(df["macd"].iloc[-1], 2) if not pd.isna(df["macd"].iloc[-1]) else 0,
            "signal": df["signal"].iloc[-1],
            "change": round(((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]) * 100, 3),
        }

        return jsonify({
            "success":     True,
            "chart_data":  chart_data,
            "trades":      trades[-20:],
            "equity":      equity_curve,
            "stats":       stats,
            "current":     current,
            "symbol":      symbol,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/price/<symbol>")
def get_price(symbol):
    try:
        url  = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
        data = requests.get(url, timeout=5).json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("\n🤖 Trading Bot GUI Starting...")
    print("=" * 45)
    print("  Open your browser and go to:")
    print("  👉  http://localhost:5000")
    print("=" * 45)
    app.run(debug=False, port=5000)
