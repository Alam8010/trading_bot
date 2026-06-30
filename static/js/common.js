// Shared chart color
const GRID_COLOR = 'rgba(48,54,61,.5)';

// Chart defaults
Chart.defaults.color = '#7d8590';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 10;

// Tab switching — no scrolling, pure show/hide
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'signals') fetchBotStatus();
  if (name === 'backtest' && _lastBacktestData) {
    destroyAll();
    const { chart_data: cd, equity } = _lastBacktestData;
    buildPriceChart(cd);
    buildRsiChart(cd);
    buildMacdChart(cd);
    buildVolumeChart(cd);
    buildEquityChart(equity);
  }
}

// Signal badge
function sigBadge(sig) {
  return `<span class="sig-badge sig-${sig}">${sig.replace('_',' ')}</span>`;
}

// Score → color
function scoreColor(s) {
  return s >= 70 ? '#3fb950' : s >= 50 ? '#d29922' : s >= 30 ? '#d29922' : '#f85149';
}

// Loader
function showLoader(msg) { document.getElementById('loader').classList.add('active'); setLoaderText(msg); }
function hideLoader()     { document.getElementById('loader').classList.remove('active'); }
function setLoaderText(t) { document.getElementById('loaderText').textContent = t; }

// Toast
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4000);
}

// Default chart options
function chartOpts(showLegend = false) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: showLegend, labels: { boxWidth: 10, padding: 8, font: { size: 10 } } } },
    scales: {
      x: { display: false },
      y: { grid: { color: GRID_COLOR }, ticks: { callback: v => typeof v === 'number' && v > 1000 ? '$' + v.toLocaleString() : v } }
    }
  };
}

// Live price refresh every 10s
async function refreshPrice() {
  const sym = (document.getElementById('symbol') || {}).value || 'BTCUSDT';
  try {
    const res  = await fetch('/api/price/' + sym);
    const data = await res.json();
    if (data.price) {
      document.getElementById('livePrice').textContent = sym + ' $' + parseFloat(data.price).toLocaleString();
    }
  } catch(e) {}
}
setInterval(refreshPrice, 10000);
refreshPrice();
