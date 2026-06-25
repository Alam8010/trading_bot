async function runScan() {
  const btn = document.getElementById('scanBtn');
  btn.disabled = true; btn.textContent = '⏳ Scanning...';
  document.getElementById('scanStatus').textContent = 'Fetching all Binance pairs — this takes ~15-25s...';
  document.getElementById('scanMetaStats').style.display = 'none';

  const interval = document.getElementById('scanInterval').value;
  try {
    const res  = await fetch(`/api/scan?interval=${interval}&force=true`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    renderLeaderboard(data);
  } catch(e) {
    document.getElementById('scanStatus').textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '🔭 Scan Market';
  }
}

function renderLeaderboard(data) {
  const { coins, total_usdt, total_qualified, count, timestamp, cached, age } = data;
  const cacheNote = cached ? ` · Cached (${age}s ago)` : '';
  document.getElementById('scanStatus').textContent   = `Last scan: ${new Date(timestamp).toLocaleTimeString()}${cacheNote}`;
  document.getElementById('smsTotalUsdt').textContent = total_usdt || '—';
  document.getElementById('smsQualified').textContent = total_qualified || count;
  document.getElementById('smsTopScore').textContent  = coins.length ? coins[0].score + '/100' : '—';
  document.getElementById('scanMetaStats').style.display = 'flex';

  if (!coins || !coins.length) {
    document.getElementById('leaderboardContent').innerHTML =
      '<div class="empty-state large"><div class="empty-icon">😕</div><p>No qualifying coins found</p></div>';
    return;
  }

  const rows = coins.map((c, i) => {
    const rankCls = i===0 ? 'gold' : i===1 ? 'silver' : i===2 ? 'bronze' : '';
    const sc      = scoreColor(c.score);
    const chgClr  = c.change >= 0 ? '#3fb950' : '#f85149';
    const rsiClr  = c.rsi < 30 ? '#3fb950' : c.rsi > 70 ? '#f85149' : 'var(--text)';
    const tags    = (c.tags || []).map(t => `<span class="tag">${t}</span>`).join('');
    const base    = c.symbol.replace('USDT','');
    return `<tr>
      <td><span class="rank-num ${rankCls}">#${i+1}</span></td>
      <td><div class="coin-sym">${base}</div><div style="font-size:10px;color:var(--muted)">/USDT</div></td>
      <td>
        <div class="score-bar-wrap">
          <div class="score-bar"><div class="score-bar-fill" style="width:${c.score}%;background:${sc}"></div></div>
          <span class="score-num" style="color:${sc}">${c.score}</span>
        </div>
      </td>
      <td>${sigBadge(c.signal)}</td>
      <td style="font-family:var(--mono)">$${parseFloat(c.price).toLocaleString()}</td>
      <td style="font-family:var(--mono);color:${chgClr}">${c.change>=0?'+':''}${c.change}%</td>
      <td style="font-family:var(--mono);color:var(--muted)">$${c.volume_m}M</td>
      <td style="font-family:var(--mono);color:${rsiClr}">${c.rsi}</td>
      <td><div class="tags-cell">${tags}</div></td>
      <td><button class="analyze-btn" onclick="analyzeFromScanner('${c.symbol}')">Analyze →</button></td>
    </tr>`;
  }).join('');

  document.getElementById('leaderboardContent').innerHTML = `
    <table class="lb-table">
      <thead><tr>
        <th>#</th><th>Coin</th><th>Score</th><th>Signal</th>
        <th>Price</th><th>24h</th><th>Volume</th><th>RSI</th>
        <th>Tags</th><th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}
