let _autoRefTimer = null;
let _autoRefOn    = false;

async function runSignals() {
  const btn      = document.getElementById('sigBtn');
  const symbol   = (document.getElementById('sigSymbol').value || 'BTCUSDT').trim().toUpperCase();
  const interval = document.getElementById('sigInterval').value;
  btn.disabled = true; btn.textContent = '⏳ Loading...';
  try {
    const res  = await fetch(`/api/signals/${symbol}?interval=${interval}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    renderSignals(data);
  } catch(e) {
    showToast('Signals error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '⚡ Analyze';
  }
}

function renderSignals(d) {
  const { symbol, price, score, signal, signals, timestamp } = d;
  const posCount = signals.filter(s => s.score > 0).length;

  document.getElementById('sigPrice').textContent    = '$' + parseFloat(price).toLocaleString();
  document.getElementById('sigSymLabel').textContent = symbol;
  document.getElementById('sigScore').textContent    = score + ' / 100';
  document.getElementById('sigScore').style.color    = scoreColor(score);
  document.getElementById('sigPosCount').textContent = posCount + ' of ' + signals.length + ' signals positive';
  document.getElementById('sigOverall').innerHTML    = sigBadge(signal);
  const ts = new Date(timestamp).toLocaleTimeString();
  document.getElementById('sigUpdated').textContent    = 'Updated ' + ts;
  document.getElementById('sigLastUpdate').textContent = 'Last update: ' + ts;

  document.getElementById('sigRowsWrap').innerHTML = signals.map(s => {
    const cls = s.score > 0 ? 'pos' : s.score < 0 ? 'neg' : 'zero';
    const col = s.score > 0 ? '#3fb950' : s.score < 0 ? '#f85149' : '#7d8590';
    const pct = Math.round(Math.abs(s.score) / (s.max || 15) * 100);
    const val = s.name === 'OBV'
      ? (parseFloat(s.value) > 0 ? '↑ rising' : '↓ falling')
      : s.unit ? s.value + s.unit : s.value;
    return `<div class="sig-row-item">
      <div class="sig-indicator">
        <div class="sig-indicator-name">${s.name}</div>
        <div class="sig-indicator-cat">${s.category}</div>
      </div>
      <div class="sig-value">${val}</div>
      <div class="sig-bar-wrap"><div class="sig-bar-fill" style="width:${pct}%;background:${col}"></div></div>
      <div class="sig-score ${cls}">${s.score > 0 ? '+' : ''}${s.score}</div>
      <div class="sig-status-lbl">${s.label}</div>
    </div>`;
  }).join('');

  document.getElementById('sigTotalBarFill').style.width = score + '%';
  document.getElementById('sigTotalNum').textContent     = score + ' / 100';
  document.getElementById('sigTotalNum').style.color     = scoreColor(score);
  document.getElementById('sigTotalSig').innerHTML       = sigBadge(signal);
}

function toggleAutoRefresh() {
  _autoRefOn = !_autoRefOn;
  const btn = document.getElementById('autoRefBtn');
  if (_autoRefOn) {
    btn.textContent = 'Auto-refresh: ON'; btn.classList.add('on');
    runSignals(); fetchBotStatus();
    _autoRefTimer = setInterval(() => { runSignals(); fetchBotStatus(); }, 15000);
  } else {
    btn.textContent = 'Auto-refresh: OFF'; btn.classList.remove('on');
    clearInterval(_autoRefTimer); _autoRefTimer = null;
  }
}

async function fetchBotStatus() {
  try {
    const res  = await fetch('/api/bot/status');
    const data = await res.json();
    if (!data.success) return;
    renderBotStatus(data);
  } catch(e) {}
}

function renderBotStatus(d) {
  const dot   = document.getElementById('botDot');
  const title = document.getElementById('botTitle');

  if (!d.running) {
    dot.classList.add('offline');
    title.textContent = 'Live Bot — Offline';
    document.getElementById('botBody').innerHTML = `
      <div class="offline-hint">
        Run <code>python live_bot.py</code> to start the live trading bot.<br>
        Position, balance and signals appear here automatically every 20s.
      </div>`;
    document.getElementById('botLog').innerHTML = '<div class="log-empty">No entries yet — start live_bot.py to see activity.</div>';
    return;
  }

  dot.classList.remove('offline');
  title.textContent = 'Live Bot — Running';
  const posColor = d.in_position ? 'var(--green)' : 'var(--muted)';
  const posText  = d.in_position ? '🟢 IN POSITION' : '⚪ OUT';

  document.getElementById('botBody').innerHTML = `
    <div class="bot-kv"><span class="bot-kv-key">Watching</span><span class="bot-kv-val">${d.symbol||'—'}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">Position</span><span class="bot-kv-val" style="color:${posColor}">${posText}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">Last Signal</span><span class="bot-kv-val">${sigBadge(d.last_signal||'HOLD')}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">RSI</span><span class="bot-kv-val" style="color:${d.last_rsi<30?'var(--green)':d.last_rsi>70?'var(--red)':'var(--text)'}">${d.last_rsi||'—'}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">Price</span><span class="bot-kv-val">$${parseFloat(d.last_price||0).toLocaleString()}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">USDT Free</span><span class="bot-kv-val">$${d.usdt_balance||'—'}</span></div>
    <div class="bot-kv"><span class="bot-kv-key">BTC Held</span><span class="bot-kv-val">${d.btc_balance||'—'} BTC</span></div>
    <div class="bot-kv"><span class="bot-kv-key">Last Check</span><span class="bot-kv-val" style="color:var(--muted)">${d.last_check||'—'}</span></div>`;

  const log = d.log || [];
  if (!log.length) { document.getElementById('botLog').innerHTML = '<div class="log-empty">No activity yet.</div>'; return; }
  document.getElementById('botLog').innerHTML = log.slice(0,20).map(e => {
    const cls = e.message.includes('BUY') ? 'buy' : e.message.includes('SELL') ? 'sell' : 'hold';
    return `<div class="log-entry"><span class="log-time">${e.time}</span><span class="log-msg ${cls}">${e.message}</span></div>`;
  }).join('');
}

// Passive poll every 20s regardless of active tab
setInterval(fetchBotStatus, 20000);
fetchBotStatus();
