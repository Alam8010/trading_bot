let priceChart, rsiChart, macdChart, volumeChart, equityChart;

function destroyAll() {
  [priceChart, rsiChart, macdChart, volumeChart, equityChart]
    .forEach(c => { if (c) c.destroy(); });
}

async function runBot() {
  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  showLoader('Fetching market data from Binance...');

  const payload = {
    symbol:          document.getElementById('symbol').value,
    interval:        document.getElementById('interval').value,
    limit:           document.getElementById('limit').value,
    initial_capital: document.getElementById('capital').value,
    risk_per_trade:  document.getElementById('risk').value / 100,
    rsi_period:      document.getElementById('rsiPeriod').value,
    rsi_oversold:    document.getElementById('rsiOversold').value,
    rsi_overbought:  document.getElementById('rsiOverbought').value,
  };

  try {
    setLoaderText('Calculating RSI, MACD, Bollinger Bands...');
    const res  = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    setLoaderText('Rendering charts...');
    await new Promise(r => setTimeout(r, 80));
    renderAll(data);
  } catch(e) {
    showToast('Error: ' + e.message);
  } finally {
    hideLoader();
    btn.disabled = false;
  }
}

function renderAll(data) {
  const { chart_data: cd, trades, equity, stats, current, symbol } = data;
  const profitColor = stats.total_profit >= 0 ? '#3fb950' : '#f85149';

  document.getElementById('kpiFinal').textContent     = '$' + stats.final_capital.toLocaleString();
  document.getElementById('kpiStart').textContent     = '$' + stats.initial_capital.toLocaleString();
  document.getElementById('kpiProfit').textContent    = (stats.total_profit >= 0 ? '+' : '') + '$' + stats.total_profit.toLocaleString();
  document.getElementById('kpiProfit').style.color    = profitColor;
  document.getElementById('kpiProfitPct').textContent = (stats.profit_pct >= 0 ? '+' : '') + stats.profit_pct + '%';
  document.getElementById('kpiProfitPct').style.color = profitColor;
  document.getElementById('kpiWinRate').textContent   = stats.win_rate + '%';
  document.getElementById('kpiWL').textContent        = stats.winning_trades + 'W / ' + stats.losing_trades + 'L';
  document.getElementById('kpiTrades').textContent    = stats.total_trades;
  document.getElementById('kpiPrice').textContent     = '$' + current.price.toLocaleString();
  const chg = current.change;
  document.getElementById('kpiChange').textContent    = (chg >= 0 ? '+' : '') + chg + '%';
  document.getElementById('kpiChange').style.color    = chg >= 0 ? '#3fb950' : '#f85149';

  document.getElementById('livePrice').textContent    = symbol + ' $' + current.price.toLocaleString();
  document.getElementById('msCurSig').innerHTML       = sigBadge(current.signal);
  document.getElementById('msCurRsi').textContent     = current.rsi;
  document.getElementById('msCurRsi').style.color     = current.rsi < 30 ? '#3fb950' : current.rsi > 70 ? '#f85149' : '#e6edf3';
  document.getElementById('msCurMacd').textContent    = current.macd;
  document.getElementById('msCurMacd').style.color    = current.macd > 0 ? '#3fb950' : '#f85149';
  const c2 = current.change;
  document.getElementById('msCurChange').textContent  = (c2 >= 0 ? '+' : '') + c2 + '%';
  document.getElementById('msCurChange').style.color  = c2 >= 0 ? '#3fb950' : '#f85149';

  destroyAll();
  buildPriceChart(cd);
  buildRsiChart(cd);
  buildMacdChart(cd);
  buildVolumeChart(cd);
  buildEquityChart(equity);
  buildTradesTable(trades);
}

function buildPriceChart(cd) {
  const ctx = document.getElementById('priceChart').getContext('2d');
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: cd.timestamps,
      datasets: [
        { label:'Price',    data:cd.close,    borderColor:'#58a6ff', borderWidth:1.5, pointRadius:0, tension:0.1, fill:false, order:1 },
        { label:'MA20',     data:cd.ma20,     borderColor:'#d29922', borderWidth:1,   pointRadius:0, tension:0.1, fill:false, order:2 },
        { label:'MA50',     data:cd.ma50,     borderColor:'#f0883e', borderWidth:1,   pointRadius:0, tension:0.1, fill:false, order:3 },
        { label:'BB Upper', data:cd.bb_upper, borderColor:'rgba(188,140,255,.4)', borderWidth:1, pointRadius:0, borderDash:[4,4], fill:false, order:4 },
        { label:'BB Lower', data:cd.bb_lower, borderColor:'rgba(188,140,255,.4)', borderWidth:1, pointRadius:0, borderDash:[4,4], fill:'-1', backgroundColor:'rgba(188,140,255,.03)', order:5 },
        { label:'BUY',  type:'scatter', data:cd.buy_times.map((t,i)  => ({x:t, y:cd.buy_prices[i]})),  backgroundColor:'#3fb950', borderColor:'#3fb950', pointRadius:5, pointStyle:'triangle', order:0 },
        { label:'SELL', type:'scatter', data:cd.sell_times.map((t,i) => ({x:t, y:cd.sell_prices[i]})), backgroundColor:'#f85149', borderColor:'#f85149', pointRadius:5, pointStyle:'triangle', rotation:180, order:0 },
      ]
    },
    options: { ...chartOpts(true) }
  });
}

function buildRsiChart(cd) {
  const ctx = document.getElementById('rsiChart').getContext('2d');
  rsiChart = new Chart(ctx, {
    type: 'line',
    data: { labels:cd.timestamps, datasets:[{ label:'RSI', data:cd.rsi, borderColor:'#bc8cff', borderWidth:1.5, pointRadius:0, tension:0.2, fill:false }] },
    options: { ...chartOpts(), scales:{ x:{display:false}, y:{min:0,max:100,grid:{color:GRID_COLOR},ticks:{stepSize:20}} } },
    plugins: [{
      id: 'rsiLines',
      beforeDraw(chart) {
        const {ctx,chartArea:{left,right},scales:{y}} = chart;
        [[70,'rgba(248,81,73,.35)'],[50,'rgba(255,255,255,.07)'],[30,'rgba(63,185,80,.35)']].forEach(([val,color]) => {
          const py = y.getPixelForValue(val);
          ctx.save(); ctx.strokeStyle=color; ctx.lineWidth=1; ctx.setLineDash([4,4]);
          ctx.beginPath(); ctx.moveTo(left,py); ctx.lineTo(right,py); ctx.stroke(); ctx.restore();
        });
      }
    }]
  });
}

function buildMacdChart(cd) {
  const ctx = document.getElementById('macdChart').getContext('2d');
  const histColors = cd.macd_hist.map(v => v >= 0 ? 'rgba(63,185,80,.6)' : 'rgba(248,81,73,.6)');
  macdChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cd.timestamps,
      datasets: [
        { label:'Histogram', data:cd.macd_hist, backgroundColor:histColors, borderWidth:0, order:3 },
        { label:'MACD',   data:cd.macd,         type:'line', borderColor:'#58a6ff', borderWidth:1.5, pointRadius:0, tension:0.2, fill:false, order:1 },
        { label:'Signal', data:cd.macd_signal,  type:'line', borderColor:'#d29922', borderWidth:1.5, pointRadius:0, tension:0.2, fill:false, order:2 },
      ]
    },
    options: chartOpts()
  });
}

function buildVolumeChart(cd) {
  const ctx = document.getElementById('volumeChart').getContext('2d');
  const volColors = cd.volume.map((v,i) => {
    if (i===0) return 'rgba(56,139,253,.4)';
    return cd.close[i] >= cd.close[i-1] ? 'rgba(63,185,80,.5)' : 'rgba(248,81,73,.5)';
  });
  volumeChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cd.timestamps,
      datasets: [
        { label:'Volume',   data:cd.volume,    backgroundColor:volColors, borderWidth:0, order:2 },
        { label:'Vol MA20', data:cd.volume_ma, type:'line', borderColor:'#d29922', borderWidth:1.5, pointRadius:0, tension:0.2, fill:false, order:1 },
      ]
    },
    options: chartOpts()
  });
}

function buildEquityChart(equity) {
  const ctx = document.getElementById('equityChart').getContext('2d');
  const startCap = equity[0];
  equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: equity.map((_,i) => i),
      datasets: [{
        label:'Portfolio', data:equity,
        borderColor:'#3fb950', borderWidth:2, pointRadius:0, tension:0.3,
        fill:{ target:{value:startCap}, above:'rgba(63,185,80,.1)', below:'rgba(248,81,73,.1)' }
      }]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{ legend:{display:false} },
      scales:{ x:{display:false}, y:{ grid:{color:GRID_COLOR}, ticks:{callback:v=>'$'+v.toLocaleString()} } }
    }
  });
}

function buildTradesTable(trades) {
  if (!trades || !trades.length) {
    document.getElementById('tradesWrap').innerHTML = '<div class="empty-state">No trades generated</div>';
    return;
  }
  const rows = [...trades].reverse().map(t => {
    const pnl = t.type === 'SELL'
      ? `<span class="${t.profit>=0?'profit-pos':'profit-neg'}">${t.profit>=0?'+':''}$${t.profit.toFixed(2)}</span>`
      : '—';
    return `<tr>
      <td><span class="${t.type==='BUY'?'buy-tag':'sell-tag'}">${t.type}</span></td>
      <td>$${t.price.toLocaleString()}</td>
      <td>${pnl}</td>
      <td>$${t.capital.toLocaleString()}</td>
      <td style="color:var(--muted);font-size:11px">${t.time.slice(0,16)}</td>
    </tr>`;
  }).join('');
  document.getElementById('tradesWrap').innerHTML = `
    <table>
      <thead><tr><th>Type</th><th>Price</th><th>Profit</th><th>Capital After</th><th>Time</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// Called from scanner's Analyze → button
function analyzeFromScanner(symbol) {
  switchTab('backtest');
  const sel = document.getElementById('symbol');
  for (let o of sel.options) {
    if (o.value === symbol) { sel.value = symbol; runBot(); return; }
  }
  sel.add(new Option(symbol.replace('USDT','/USDT'), symbol, true, true));
  sel.value = symbol;
  runBot();
}
