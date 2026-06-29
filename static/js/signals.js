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
    <div class="bot-kv"><span class="bot-kv-key">Open Positions</span><span class="bot-kv-val" style="color:var(--accent)">${d.btc_balance||'0'} / 3</span></div>
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

// ── Bot Controls ─────────────────────────────────────
let _botRunning = false;

function toggleBot() {
  const btn      = document.getElementById('botToggleBtn');
  const endpoint = _botRunning ? '/api/bot/stop' : '/api/bot/start';
  btn.disabled   = true;
  btn.textContent = '⏳ Please wait...';
  fetch(endpoint, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        _botRunning = !_botRunning;
        updateBotBtn();
        document.getElementById('ctrlStatus').textContent =
          _botRunning ? '✅ Bot started' : '🛑 Bot stopped';
      } else {
        document.getElementById('ctrlStatus').textContent = '❌ ' + (data.error || 'Failed');
      }
    })
    .catch(() => {
      document.getElementById('ctrlStatus').textContent = '❌ Could not reach server';
    })
    .finally(() => { btn.disabled = false; });
}

function updateBotBtn() {
  const btn = document.getElementById('botToggleBtn');
  if (_botRunning) {
    btn.textContent  = '⏹ Stop Bot';
    btn.style.background = 'var(--red)';
  } else {
    btn.textContent  = '▶ Start Bot';
    btn.style.background = '';
  }
}

function setSlots(n) {
  fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({max_positions: n})
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      [1,2,3].forEach(i => {
        document.getElementById('slot' + i).classList.toggle('active', i === n);
      });
      document.getElementById('ctrlStatus').textContent = `✅ Max positions set to ${n}`;
    }
  });
}

function saveTradeAmt() {
  const val = parseFloat(document.getElementById('tradeAmtInput').value);
  if (isNaN(val) || val < 10) {
    document.getElementById('ctrlStatus').textContent = '❌ Minimum $10';
    return;
  }
  fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({trade_usdt: val})
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      document.getElementById('ctrlStatus').textContent = `✅ Trade amount set to $${val}`;
    }
  });
}

// Load current settings into controls on page load
fetch('/api/settings')
  .then(r => r.json())
  .then(data => {
    if (!data.success) return;
    const s = data.settings;
    document.getElementById('tradeAmtInput').value = s.trade_usdt || 15;
    const slots = s.max_positions || 3;
    [1,2,3].forEach(i => {
      document.getElementById('slot' + i).classList.toggle('active', i === slots);
    });
  });

// Sync bot running state with status polls
const _origRenderBotStatus = renderBotStatus;
renderBotStatus = function(d) {
  _origRenderBotStatus(d);
  _botRunning = d.running;
  updateBotBtn();
};

// ── Trade History ─────────────────────────────────────
function loadTradeHistory() {
  fetch('/api/trades')
    .then(r => r.json())
    .then(data => {
      const summary = data.summary || {};

      document.getElementById('trTotalTrades').textContent =
        summary.total_trades != null ? summary.total_trades : '—';

      const wrEl = document.getElementById('trWinRate');
      wrEl.textContent = summary.win_rate != null
        ? summary.win_rate.toFixed(1) + '%' : '—';

      const pnlEl = document.getElementById('trTotalPnl');
      const pnl   = summary.total_pnl_usdt;
      if (pnl != null) {
        pnlEl.textContent  = (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + ' $';
        pnlEl.style.color  = pnl >= 0 ? 'var(--green)' : 'var(--red)';
      } else {
        pnlEl.textContent = '—';
        pnlEl.style.color = '';
      }

      const tbody  = document.getElementById('tradeHistoryBody');
      const trades = data.trades || [];
      if (!trades.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px;">No trades yet</td></tr>';
        return;
      }
      tbody.innerHTML = trades.map(t => {
        const win      = t.pnl_usdt >= 0;
        const rowClass = 'trade-row ' + (win ? 'trade-win' : 'trade-loss');
        const col      = win ? 'var(--green)' : 'var(--red)';
        const ts       = t.timestamp
          ? new Date(t.timestamp).toLocaleString([], {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})
          : '—';
        return `<tr class="${rowClass}">
          <td>${ts}</td>
          <td style="color:var(--accent);font-weight:600;">${t.coin}</td>
          <td>${Number(t.entry_price).toFixed(4)}</td>
          <td>${Number(t.exit_price).toFixed(4)}</td>
          <td>${Number(t.amount).toFixed(4)}</td>
          <td style="color:${col}">${(t.pnl_usdt >= 0 ? '+' : '') + Number(t.pnl_usdt).toFixed(3)}</td>
          <td style="color:${col}">${(t.pnl_pct >= 0 ? '+' : '') + Number(t.pnl_pct).toFixed(2)}%</td>
          <td style="color:var(--muted);font-size:10px;">${t.reason || '—'}</td>
        </tr>`;
      }).join('');
    })
    .catch(err => console.error('Trade history fetch error:', err));
}

loadTradeHistory();
setInterval(loadTradeHistory, 30000);
