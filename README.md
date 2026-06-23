# 🤖 CryptoBot — Automated Technical Trading Bot

A Python-based automated crypto trading bot that scans markets, generates signals using technical indicators, and executes trades on Binance Testnet. Built to eventually evolve into a smart multi-coin hunter with ML-based predictions.

---

## 📁 Project Structure

```
trading_bot/
├── bot.py               ← GUI dashboard (Flask web app)
├── live_bot.py          ← Live trading bot (Binance Testnet)
├── templates/
│   └── index.html       ← Frontend dashboard UI
├── README.md            ← You are here
└── NEXT_STEPS.docx      ← Roadmap document for collaborators
```

---

## ✅ What Is Built So Far

### 1. GUI Dashboard (`bot.py` + `index.html`)
- Fetches real BTC/USDT data from Binance public API (no account needed)
- Calculates RSI, MACD, Bollinger Bands, MA20, MA50
- Generates BUY / SELL / HOLD signals
- Runs a backtest on historical data
- Displays interactive charts: Price, RSI, MACD, Volume, Equity Curve
- Shows trade log with profit/loss per trade
- Live price ticker refreshes every 10 seconds

### 2. Live Trading Bot (`live_bot.py`)
- Connected to **Binance Spot Testnet** (fake money, real market)
- Fetches live candle data every 60 seconds
- Calculates RSI + MACD signals in real time
- Automatically places BUY and SELL market orders
- Tracks position state (in position / not in position)
- Displays live balance (USDT + BTC)

---

## 🧠 Why We Chose This Approach

### Why Technical Analysis First?
- Technical signals are based on pure price/volume math
- No external data sources needed (no news APIs, no sentiment feeds)
- Faster to build and test
- Well-established, proven logic used by professional traders
- Foundation layer — everything else builds on top of this

### Why Binance Testnet?
- Zero real money risk
- Real market prices (not simulated)
- Real API connection (same as live trading)
- Free fake balance ($10,000 USDT + 1 BTC)
- Perfect for validating bot logic before going live

### Why Not Use Binance's Built-in Tools?
- Binance can only monitor 1 coin at a time manually
- Our bot will scan 50+ coins simultaneously
- Our bot will auto-rank and pick the best opportunity
- Our bot will rotate between coins automatically
- No human intervention needed once running

### Why Flask for the Dashboard?
- Lightweight Python web server
- Runs locally — no deployment needed
- Easy to extend with new charts and features
- Chart.js frontend gives professional interactive visuals

### What We Eliminated and Why

| Approach | Why Eliminated |
|----------|---------------|
| Pure ML from start | Needs large dataset + data science expertise first |
| News sentiment bot | Requires NLP pipeline — Phase 2 plan |
| Real account trading | Too risky before strategy is validated |
| Desktop GUI (Tkinter) | Web-based is more flexible and shareable |
| Single coin focus | Multi-coin scanner adds much more value |

---

## ⚙️ Setup Instructions

### Requirements
- Python 3.11+
- VS Code (or any terminal)
- GitHub account (for Binance Testnet login)

### Install Dependencies
```bash
pip install requests pandas numpy ta flask matplotlib ccxt
```

### Run the Dashboard
```bash
python bot.py
```
Then open: `http://localhost:5000`

### Run the Live Bot
```bash
python live_bot.py
```

### Binance Testnet API Keys
1. Go to: https://testnet.binance.vision
2. Login with GitHub
3. Generate HMAC_SHA256 Key
4. Paste API Key and Secret into `live_bot.py`:
```python
API_KEY    = "your_api_key_here"
API_SECRET = "your_secret_here"
```

---

## 📊 Current Signals Used

| Signal | Category | Purpose |
|--------|----------|---------|
| RSI (14) | Momentum | Oversold / Overbought detection |
| MACD | Trend | Momentum crossover signals |
| MA20 / MA50 | Trend | Price trend direction |
| Bollinger Bands | Volatility | Price range and squeeze detection |
| Volume MA | Volume | Confirms strength of moves |

---

## 🗺️ Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 — Data & Signals | ✅ Done | Fetch data, calculate indicators, generate signals |
| Phase 2 — GUI Dashboard | ✅ Done | Interactive web dashboard with charts |
| Phase 3 — Live Bot | ✅ Done | Connected to Binance Testnet, placing real orders |
| Phase 4 — Multi-Coin Scanner | 🔲 Next | Scan 50 coins, score each, pick best |
| Phase 5 — Smart Scoring | 🔲 Next | 7-signal scoring system (0-100 per coin) |
| Phase 6 — Telegram Alerts | 🔲 Next | Phone notifications on every trade |
| Phase 7 — ML Layer | 🔲 Future | Train model on historical data to improve scores |
| Phase 8 — News Sentiment | 🔲 Future | Add real-world events awareness |

---

## ⚠️ Important Notes

- **Never share your API keys** — keep them out of GitHub
- **Add a `.gitignore`** to exclude keys (see below)
- This bot uses **Testnet only** — no real money at risk
- Past backtest results do not guarantee future performance

### .gitignore (create this file)
```
*.env
config.py
__pycache__/
*.pyc
```

---

## 👥 Collaborators

- Store your own API keys locally — never commit them
- Read `NEXT_STEPS.docx` for the full development roadmap
- Each phase in the roadmap is broken into clear tasks

---

## 📄 License
Private project — not for public distribution.
