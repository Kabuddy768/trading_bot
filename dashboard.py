"""
ICT Bot Dashboard Generator
Run: python dashboard.py
Opens a live dashboard in your browser from trading_bot.db
"""

import sqlite3
import json
import os
import webbrowser
import tempfile
from pathlib import Path

DB_FILE = "trading_bot.db"

def load_trades():
    if not os.path.exists(DB_FILE):
        print(f"❌ Database not found: {DB_FILE}")
        print("   Make sure you run this from C:/Trading/trading_bot/")
        return [], 10000.0

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Load ICT trades
    try:
        cursor.execute("""
            SELECT timestamp, symbol, direction, 
                   round(entry_price, 2) as entry_price,
                   round(sl_price, 2) as sl_price,
                   round(tp_price, 2) as tp_price,
                   round(exit_price, 2) as exit_price,
                   exit_reason, confluence_score, confluences,
                   primary_zone,
                   round(pnl_pips, 1) as pnl_pips,
                   round(net_pnl_usd, 2) as net_pnl_usd,
                   closed_at
            FROM ict_trades
            ORDER BY timestamp ASC
        """)
        trades = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️  Could not load ict_trades: {e}")
        trades = []

    # Load equity
    try:
        cursor.execute("SELECT value FROM bot_state WHERE key = 'paper_equity'")
        row = cursor.fetchone()
        equity = float(json.loads(row[0])) if row else 10000.0
    except:
        equity = 10000.0

    conn.close()
    return trades, equity


def generate_html(trades, equity):
    trades_json = json.dumps(trades)
    starting_equity = 10000.0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ICT Bot Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
  :root {{
    --bg: #0a0a0f; --surface: #111118; --border: #1e1e2e;
    --accent: #00ff9d; --red: #ff4757; --gold: #ffd32a;
    --text: #e0e0f0; --muted: #555570;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Space Mono', monospace; min-height: 100vh; padding: 24px; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 32px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
  h1 {{ font-family: 'Syne', sans-serif; font-weight: 800; font-size: 28px; letter-spacing: -1px; color: var(--accent); }}
  .subtitle {{ color: var(--muted); font-size: 11px; margin-top: 4px; }}
  .live-dot {{ display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--accent); }}
  .live-dot::before {{ content: ''; width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse 1.5s infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity:1;transform:scale(1) }} 50% {{ opacity:0.4;transform:scale(0.8) }} }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
  .card-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); margin-bottom: 8px; }}
  .card-value {{ font-family: 'Syne', sans-serif; font-size: 28px; font-weight: 700; }}
  .card-sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
  .green {{ color: var(--accent); }} .red {{ color: var(--red); }} .gold {{ color: var(--gold); }}
  .section-title {{ font-family: 'Syne', sans-serif; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted); padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #15151f; vertical-align: middle; }}
  tr:hover td {{ background: #13131c; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
  .badge-long {{ background: rgba(0,255,157,0.15); color: var(--accent); }}
  .badge-short {{ background: rgba(255,71,87,0.15); color: var(--red); }}
  .badge-tp {{ background: rgba(0,255,157,0.1); color: var(--accent); border: 1px solid rgba(0,255,157,0.3); }}
  .badge-sl {{ background: rgba(255,71,87,0.1); color: var(--red); border: 1px solid rgba(255,71,87,0.3); }}
  .badge-open {{ background: rgba(255,211,42,0.1); color: var(--gold); border: 1px solid rgba(255,211,42,0.3); }}
  .winrate-bar {{ height: 8px; border-radius: 4px; background: var(--border); overflow: hidden; margin: 8px 0; }}
  .winrate-fill {{ height: 100%; border-radius: 4px; background: linear-gradient(90deg, var(--accent), #00cc7a); }}
  .empty {{ color: var(--muted); font-size: 12px; padding: 24px; text-align: center; }}
  .alert {{ background: rgba(255,211,42,0.08); border: 1px solid rgba(255,211,42,0.3); border-radius: 6px; padding: 12px 16px; font-size: 12px; color: var(--gold); margin-bottom: 24px; line-height: 1.6; }}
  .refresh-btn {{ background: var(--accent); color: #000; border: none; padding: 8px 20px; font-family: 'Space Mono', monospace; font-weight: 700; font-size: 12px; border-radius: 4px; cursor: pointer; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>⬡ ICT BOT DASHBOARD</h1>
    <div class="subtitle">Live data from trading_bot.db — Generated at {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  </div>
  <div style="display:flex;align-items:center;gap:16px;">
    <div class="live-dot">PAPER TRADING</div>
  </div>
</header>

<div id="alertBox"></div>

<div class="grid-4">
  <div class="card">
    <div class="card-label">Paper Equity</div>
    <div class="card-value" id="equity">${equity:,.2f}</div>
    <div class="card-sub" id="equityChange">Loading...</div>
  </div>
  <div class="card">
    <div class="card-label">Total Trades</div>
    <div class="card-value" id="totalTrades">0</div>
    <div class="card-sub" id="openTrades">0 open</div>
  </div>
  <div class="card">
    <div class="card-label">Win Rate</div>
    <div class="card-value" id="winRate">0%</div>
    <div class="winrate-bar"><div class="winrate-fill" id="winFill" style="width:0%"></div></div>
    <div class="card-sub" id="wlCount">0W / 0L</div>
  </div>
  <div class="card">
    <div class="card-label">Total PnL</div>
    <div class="card-value" id="totalPnl">$0.00</div>
    <div class="card-sub" id="avgTrade">Avg: $0.00/trade</div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="section-title">Equity Curve</div>
    <canvas id="equityChart" style="width:100%;height:200px;"></canvas>
  </div>
  <div class="card">
    <div class="section-title">PnL by Symbol</div>
    <canvas id="symbolChart" style="width:100%;height:200px;"></canvas>
  </div>
</div>

<div class="card">
  <div class="section-title">Trade Log ({len(trades)} trades)</div>
  <table>
    <thead>
      <tr>
        <th>Time</th><th>Symbol</th><th>Dir</th>
        <th>Entry</th><th>SL</th><th>TP</th><th>Exit</th>
        <th>Reason</th><th>Zone</th><th>Score</th>
        <th>Pips</th><th>PnL USD</th>
      </tr>
    </thead>
    <tbody id="tradeBody">
      <tr><td colspan="12" class="empty">No trades found.</td></tr>
    </tbody>
  </table>
</div>

<script>
const trades = {trades_json};
const startingEquity = {starting_equity};
const currentEquity = {equity};

function init() {{
  const closed = trades.filter(t => t.exit_reason);
  const open = trades.filter(t => !t.exit_reason);
  const wins = closed.filter(t => t.exit_reason === 'TAKE_PROFIT');
  const losses = closed.filter(t => t.exit_reason === 'STOP_LOSS');
  const totalPnl = closed.reduce((s, t) => s + (t.net_pnl_usd || 0), 0);
  const winRate = closed.length ? Math.round((wins.length / closed.length) * 100) : 0;

  // Stats
  const changeEl = document.getElementById('equityChange');
  const pct = ((currentEquity - startingEquity) / startingEquity * 100).toFixed(2);
  changeEl.textContent = `${{totalPnl >= 0 ? '+' : ''}}${{totalPnl.toFixed(2)}} (${{pct}}%) from $10,000`;
  changeEl.className = 'card-sub ' + (totalPnl >= 0 ? 'green' : 'red');

  document.getElementById('totalTrades').textContent = trades.length;
  document.getElementById('openTrades').textContent = open.length + ' open positions';
  document.getElementById('winRate').textContent = winRate + '%';
  document.getElementById('winRate').className = 'card-value ' + (winRate >= 50 ? 'green' : 'red');
  document.getElementById('winFill').style.width = winRate + '%';
  document.getElementById('wlCount').textContent = `${{wins.length}}W / ${{losses.length}}L`;
  document.getElementById('totalPnl').textContent = (totalPnl >= 0 ? '+' : '') + '$' + totalPnl.toFixed(2);
  document.getElementById('totalPnl').className = 'card-value ' + (totalPnl >= 0 ? 'green' : 'red');
  document.getElementById('avgTrade').textContent = 'Avg: $' + (closed.length ? (totalPnl/closed.length).toFixed(2) : '0.00') + '/trade';

  // Alert if losing
  if (totalPnl < 0 && closed.length > 0) {{
    document.getElementById('alertBox').innerHTML = `
      <div class="alert">
        ⚠️ <strong>Bot is losing money on every trade.</strong><br>
        Fees ($0.40/trade) exceed pip distance. Fix: increase PIP_VALUES in config.py.<br>
        Recommended: BTC/USDT → 50.0, ETH/USDT → 5.0, SOL/USDT → 0.5, BNB/USDT → 1.0
      </div>`;
  }}

  renderTable(closed, open);
  renderEquityCurve(closed);
  renderSymbolChart(closed);
}}

function renderTable(closed, open) {{
  const tbody = document.getElementById('tradeBody');
  const all = [...open.map(t => ({{...t, _open: true}})), ...closed].reverse();
  if (!all.length) return;
  tbody.innerHTML = all.map(t => {{
    const pnl = t.net_pnl_usd || 0;
    const isWin = t.exit_reason === 'TAKE_PROFIT';
    const isOpen = t._open;
    return `<tr>
      <td>${{(t.timestamp||'').slice(5,16)}}</td>
      <td>${{t.symbol}}</td>
      <td><span class="badge ${{t.direction==='LONG'?'badge-long':'badge-short'}}">${{t.direction}}</span></td>
      <td>$${{(t.entry_price||0).toLocaleString()}}</td>
      <td style="color:var(--red)">$${{(t.sl_price||0).toLocaleString()}}</td>
      <td style="color:var(--accent)">$${{(t.tp_price||0).toLocaleString()}}</td>
      <td>${{isOpen ? '<span style="color:var(--gold)">OPEN</span>' : '$$'+((t.exit_price||0).toLocaleString())}}</td>
      <td>${{isOpen ? '<span class="badge badge-open">OPEN</span>' : `<span class="badge ${{isWin?'badge-tp':'badge-sl'}}">${{t.exit_reason}}</span>`}}</td>
      <td style="color:var(--gold);font-size:10px">${{t.primary_zone||'-'}}</td>
      <td style="color:var(--gold)">${{t.confluence_score||'-'}}</td>
      <td style="color:${{(t.pnl_pips||0)>=0?'var(--accent)':'var(--red)'}}">${{isOpen?'-':t.pnl_pips}}</td>
      <td style="color:${{pnl>=0?'var(--accent)':'var(--red)'}};font-weight:700">${{isOpen?'-':(pnl>=0?'+':'')+'$'+pnl.toFixed(2)}}</td>
    </tr>`;
  }}).join('');
}}

function renderEquityCurve(closed) {{
  const canvas = document.getElementById('equityChart');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth * 2;
  canvas.height = 400;
  ctx.scale(2,2);
  const w = canvas.offsetWidth/2, h = 200;
  let eq = startingEquity;
  const points = [{{x:0,y:eq}}];
  closed.forEach((t,i) => {{ eq += (t.net_pnl_usd||0); points.push({{x:i+1,y:eq}}); }});
  const minY = Math.min(...points.map(p=>p.y))-10;
  const maxY = Math.max(...points.map(p=>p.y))+10;
  const rangeY = maxY-minY||1;
  const toX = i => (i/(points.length-1||1))*(w-40)+20;
  const toY = v => h-20-((v-minY)/rangeY)*(h-40);
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='#1e1e2e'; ctx.lineWidth=0.5;
  for(let i=0;i<=4;i++) {{ const y=20+(i/4)*(h-40); ctx.beginPath();ctx.moveTo(20,y);ctx.lineTo(w-20,y);ctx.stroke(); }}
  if(points.length<2) return;
  const grad=ctx.createLinearGradient(0,0,0,h);
  grad.addColorStop(0,'rgba(0,255,157,0.2)'); grad.addColorStop(1,'rgba(0,255,157,0)');
  ctx.beginPath(); ctx.moveTo(toX(0),toY(points[0].y));
  points.forEach((p,i)=>ctx.lineTo(toX(i),toY(p.y)));
  ctx.lineTo(toX(points.length-1),h-20); ctx.lineTo(toX(0),h-20); ctx.closePath();
  ctx.fillStyle=grad; ctx.fill();
  ctx.beginPath(); ctx.moveTo(toX(0),toY(points[0].y));
  points.forEach((p,i)=>ctx.lineTo(toX(i),toY(p.y)));
  ctx.strokeStyle='#00ff9d'; ctx.lineWidth=1.5; ctx.stroke();
  closed.forEach((t,i) => {{
    ctx.beginPath(); ctx.arc(toX(i+1),toY(points[i+1].y),3,0,Math.PI*2);
    ctx.fillStyle=t.exit_reason==='TAKE_PROFIT'?'#00ff9d':'#ff4757'; ctx.fill();
  }});
}}

function renderSymbolChart(closed) {{
  const canvas = document.getElementById('symbolChart');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth * 2; canvas.height = 400;
  ctx.scale(2,2);
  const w=canvas.offsetWidth/2, h=200;
  const bySymbol={{}};
  closed.forEach(t => {{
    if(!bySymbol[t.symbol]) bySymbol[t.symbol]={{pnl:0,count:0}};
    bySymbol[t.symbol].pnl += (t.net_pnl_usd||0);
    bySymbol[t.symbol].count++;
  }});
  const symbols=Object.keys(bySymbol);
  if(!symbols.length) return;
  const barW=(w-40)/symbols.length-10;
  const maxAbs=Math.max(...symbols.map(s=>Math.abs(bySymbol[s].pnl)))||1;
  const midY=h/2;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='#1e1e2e'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(20,midY); ctx.lineTo(w-20,midY); ctx.stroke();
  symbols.forEach((sym,i) => {{
    const val=bySymbol[sym].pnl;
    const barH=(Math.abs(val)/maxAbs)*(midY-30);
    const x=20+i*(barW+10);
    const y=val>=0?midY-barH:midY;
    ctx.fillStyle=val>=0?'rgba(0,255,157,0.7)':'rgba(255,71,87,0.7)';
    ctx.fillRect(x,y,barW,barH);
    ctx.fillStyle='#555570'; ctx.font='9px monospace'; ctx.textAlign='center';
    ctx.fillText(sym.replace('/USDT',''),x+barW/2,h-5);
    ctx.fillStyle=val>=0?'#00ff9d':'#ff4757';
    ctx.fillText((val>=0?'+':'')+'$'+val.toFixed(1),x+barW/2,val>=0?y-4:y+barH+12);
  }});
}}

init();
</script>
</body>
</html>"""
    return html


def main():
    print("📊 ICT Bot Dashboard Generator")
    print(f"   Reading from: {os.path.abspath(DB_FILE)}")

    trades, equity = load_trades()
    print(f"   Found {len(trades)} trades | Equity: ${equity:,.2f}")

    html = generate_html(trades, equity)

    # Write to temp file and open in browser
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        encoding='utf-8', prefix='ict_dashboard_'
    )
    tmp.write(html)
    tmp.close()

    print(f"   Dashboard saved to: {tmp.name}")
    print("   Opening in browser...")
    webbrowser.open(f'file:///{tmp.name}')
    print("✅ Done! Refresh by running python dashboard.py again.")


if __name__ == "__main__":
    main()
