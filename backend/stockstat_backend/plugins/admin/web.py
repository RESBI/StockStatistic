"""SPA web UI HTML for admin plugin.

This is a 27KB single-page application with 5 tabs:
- Dashboard (stats, gantt, recent logs)
- Source Browser (directory, search, batch download)
- Local Symbols (K-line chart, range select, preview, delete)
- Config (DB, proxy, cache, disk)
- Logs (ingest history with filtering)

No Node build chain required. Uses vanilla JS + CSS + CDN lightweight-charts.
"""
from __future__ import annotations

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockStat Storage Admin</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1419;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
.sidebar{width:200px;background:#1a2332;border-right:2px solid #2a3f5f;display:flex;flex-direction:column;padding:0}
.sidebar .logo{padding:16px 20px;border-bottom:2px solid #2a3f5f;font-size:16px;color:#4fc3f7;font-weight:700;cursor:pointer}
.nav-item{padding:12px 20px;cursor:pointer;color:#aaa;font-size:14px;border-left:3px solid transparent;transition:all .15s}
.nav-item:hover{background:#243447;color:#e0e0e0}
.nav-item.active{background:#243447;color:#4fc3f7;border-left-color:#4fc3f7}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{background:#1a2332;padding:10px 24px;border-bottom:2px solid #2a3f5f;display:flex;justify-content:space-between;align-items:center}
.topbar .status{font-size:13px}
.ok{color:#66bb6a}.bad{color:#ef5350}.warn{color:#ffa726}
.content{flex:1;overflow-y:auto;padding:24px}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:#1a2332;padding:16px;border-radius:8px;text-align:center;border:1px solid #2a3f5f}
.stat-card .num{font-size:28px;font-weight:bold;color:#4fc3f7}
.stat-card .label{font-size:12px;color:#aaa;margin-top:4px}
.section{background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:20px;margin-bottom:20px}
.section h3{color:#4fc3f7;margin-bottom:12px;font-size:15px}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #2a3f5f;font-size:13px}
th{color:#4fc3f7;font-weight:600}
tr:hover{background:#243447}
.btn{padding:6px 14px;background:#2a6496;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px}
.btn:hover{background:#3a7ab6}
.btn.danger{background:#c0392b}.btn.danger:hover{background:#e74c3c}
.btn.success{background:#27ae60}.btn.success:hover{background:#2ecc71}
.btn.small{padding:3px 10px;font-size:12px}
input,select{padding:6px 10px;background:#0f1419;color:#e0e0e0;border:1px solid #2a3f5f;border-radius:4px;font-size:13px}
.row{display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap}
.row label{min-width:70px;font-size:13px;color:#aaa}
.split{display:flex;gap:16px;height:calc(100vh - 160px)}
.split-left{width:240px;overflow-y:auto;background:#1a2332;border:1px solid #2a3f5f;border-radius:8px}
.split-right{flex:1;overflow-y:auto}
.sym-item{padding:10px 14px;cursor:pointer;border-bottom:1px solid #2a3f5f;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.sym-item:hover{background:#243447}
.sym-item.active{background:#243447;color:#4fc3f7;border-left:3px solid #4fc3f7}
.badge{font-size:11px;padding:2px 6px;border-radius:3px}
.badge.downloaded{background:#1b3a2a;color:#66bb6a}
.badge.missing{background:#3a3520;color:#ffa726}
.chart-container{background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:16px;margin-bottom:16px}
.gantt-row{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px}
.gantt-bar{height:14px;background:#2a6496;border-radius:3px;min-width:2px}
.gantt-label{width:100px;color:#aaa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.progress-bar{height:20px;background:#0f1419;border-radius:4px;overflow:hidden;margin:8px 0}
.progress-fill{height:100%;background:#27ae60;transition:width .3s}
.msg{padding:8px 16px;border-radius:4px;margin:8px 0;font-size:13px}
.msg.ok{background:#1b3a2a;color:#66bb6a}.msg.err{background:#3a1b1b;color:#ef5350}
.pagination{display:flex;gap:4px;align-items:center;justify-content:center;margin-top:12px}
.pagination a{padding:4px 10px;background:#1a2332;border:1px solid #2a3f5f;border-radius:4px;cursor:pointer;font-size:13px}
.pagination a.active{background:#2a6496;color:#fff}
.switch{position:relative;width:40px;height:20px;background:#333;border-radius:10px;cursor:pointer}
.switch.on{background:#27ae60}
.switch::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;background:#fff;border-radius:50%;transition:.2s}
.switch.on::after{left:22px}
.checkbox{width:16px;height:16px;accent-color:#4fc3f7}
.batch-bar{position:sticky;bottom:0;background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:12px;margin-top:12px}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo" onclick="navigate('dashboard')">📈 StockStat</div>
  <div class="nav-item active" data-page="dashboard" onclick="navigate('dashboard')">📊 概览</div>
  <div class="nav-item" data-page="source" onclick="navigate('source')">📁 数据源浏览</div>
  <div class="nav-item" data-page="local" onclick="navigate('local')">💾 本地标的</div>
  <div class="nav-item" data-page="config" onclick="navigate('config')">⚙ 配置</div>
  <div class="nav-item" data-page="logs" onclick="navigate('logs')">📋 日志</div>
</div>
<div class="main">
  <div class="topbar">
    <div id="page-title">概览</div>
    <div class="status" id="hdr-status">Loading...</div>
  </div>
  <div class="content" id="content"></div>
</div>

<script>
const API='/admin/api';
let chartInstance=null;
let currentSymbol=null;
let healthTimer=null;

// ── Utils ──────────────────────────────────────────────────
async function api(path,opts){
  const r=await fetch(API+path,opts);
  if(!r.ok){const e=await r.json().catch(()=>({detail:r.statusText}));throw new Error(e.detail||r.status)}
  return r.json();
}
function fmt(n){return (n||0).toLocaleString()}
function esc(s){return String(s||'').replace(/</g,'&lt;')}
function shortDate(s){return s?s.split('T')[0]:''}

// ── Navigation ─────────────────────────────────────────────
function navigate(page,params={}){
  document.querySelectorAll('.nav-item').forEach(e=>e.classList.remove('active'));
  const el=document.querySelector(`[data-page="${page}"]`);
  if(el)el.classList.add('active');
  const titles={dashboard:'📊 概览',source:'📁 数据源浏览',local:'💾 本地标的',config:'⚙ 配置',logs:'📋 日志'};
  document.getElementById('page-title').textContent=titles[page]||page;
  const pages={dashboard:renderDashboard,source:renderSource,local:renderLocal,config:renderConfig,logs:renderLogs};
  if(pages[page])pages[page](params);
}
function startHealthCheck(){
  if(healthTimer)clearInterval(healthTimer);
  healthTimer=setInterval(async()=>{
    try{const h=await api('/health');
      const cls=h.status==='ok'?'ok':'bad';
      document.getElementById('hdr-status').innerHTML=`<span class="${cls}">● ${h.status.toUpperCase()}</span>`;
    }catch{document.getElementById('hdr-status').innerHTML='<span class="bad">● OFFLINE</span>'}
  },10000);
  (async()=>{try{const h=await api('/health');
    document.getElementById('hdr-status').innerHTML=`<span class="${h.status==='ok'?'ok':'bad'}">● ${h.status.toUpperCase()}</span>`;
  }catch{document.getElementById('hdr-status').innerHTML='<span class="bad">● OFFLINE</span>'}})()
}

// ── Dashboard ──────────────────────────────────────────────
async function renderDashboard(){
  const c=document.getElementById('content');
  c.innerHTML='<div class="stats" id="d-stats"></div><div class="section"><h3>数据覆盖时间轴</h3><div id="d-gantt"></div></div><div class="section"><h3>最近采集记录</h3><div id="d-logs"></div></div>';
  try{
    const[stats,symbols,logs,health,disk]=await Promise.all([
      api('/stats').catch(e=>({total_symbols:0,total_rows:0,symbols_by_source:{},_err:e})),
      api('/symbols').catch(e=>({symbols:[],_err:e})),
      api('/logs?size=5').catch(e=>({logs:[],_err:e})),
      api('/health').catch(e=>({status:'error',_err:e})),
      api('/disk').catch(e=>({total_gb:0,used_gb:0,used_percent:0,db_file_size_mb:0,_err:e}))
    ]);
    document.getElementById('d-stats').innerHTML=`
      <div class="stat-card"><div class="num">${stats.total_symbols}</div><div class="label">已下标的</div></div>
      <div class="stat-card"><div class="num">${fmt(stats.total_rows)}</div><div class="label">总行数</div></div>
      <div class="stat-card"><div class="num">${disk.db_file_size_mb||'-'} MB</div><div class="label">数据库大小</div></div>
      <div class="stat-card"><div class="num">${disk.used_percent||'-'}%</div><div class="label">磁盘使用率</div></div>`;
    let distHtml='<div style="margin-top:8px">';
    for(const[k,v]of Object.entries(stats.symbols_by_source||{}))
      distHtml+=`<div style="margin:4px 0">${k}: ${v} (${Math.round(v/stats.total_symbols*100)}%) ${'█'.repeat(Math.round(v/stats.total_symbols*20))}</div>`;
    distHtml+='</div>';
    document.getElementById('d-stats').innerHTML+=`<div class="stat-card" style="grid-column:span 2"><div class="num" style="font-size:14px;text-align:left">按数据源分布</div>${distHtml}</div>`;
    if(symbols.symbols.length>0){
      const allDates=symbols.symbols.flatMap(s=>[s.earliest,s.latest].filter(Boolean));
      const minD=Math.min(...allDates.map(d=>new Date(d).getTime()));
      const maxD=Math.max(...allDates.map(d=>new Date(d).getTime()));
      const range=maxD-minD||1;
      let ganttHtml='';
      for(const s of symbols.symbols){
        if(!s.earliest||!s.latest)continue;
        const startPct=(new Date(s.earliest).getTime()-minD)/range*100;
        const widthPct=(new Date(s.latest).getTime()-new Date(s.earliest).getTime())/range*100;
        ganttHtml+=`<div class="gantt-row"><div class="gantt-label" title="${s.unified_symbol}">${s.unified_symbol}</div><div style="flex:1;position:relative"><div class="gantt-bar" style="margin-left:${startPct}%;width:${Math.max(widthPct,1)}%" onclick="navigate('local',{symbol:'${s.unified_symbol}'})"></div></div><div style="width:80px;font-size:11px;color:#888">${shortDate(s.earliest)}~${shortDate(s.latest)}</div></div>`;
      }
      document.getElementById('d-gantt').innerHTML=ganttHtml;
    }else{document.getElementById('d-gantt').innerHTML='<p style="color:#888">暂无数据</p>'}
    if(logs.logs&&logs.logs.length>0){
      document.getElementById('d-logs').innerHTML=`<table><thead><tr><th>时间</th><th>标的</th><th>操作</th><th>行数</th><th>状态</th></tr></thead><tbody>${logs.logs.map(l=>`<tr><td>${shortDate(l.timestamp)} ${l.timestamp.split('T')[1]?.split('.')[0]||''}</td><td>${esc(l.symbol)}</td><td>${l.action}</td><td>${l.rows_affected}</td><td>${l.status==='success'?'✅':'❌'}</td></tr>`).join('')}</tbody></table>`;
    }else{document.getElementById('d-logs').innerHTML='<p style="color:#888">暂无记录</p>'}
  }catch(e){c.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}

// ── Source Browser ─────────────────────────────────────────
let srcState={source:'binance',page:1,search:'',selected:new Set()};
async function renderSource(){
  const c=document.getElementById('content');
  c.innerHTML=`
    <div class="row">
      <label>数据源</label><select id="src-select" onchange="srcState.source=this.value;srcState.page=1;loadSourceSymbols()">
        <option value="binance">Binance</option><option value="coinbase">Coinbase</option>
        <option value="yfinance">yfinance</option><option value="synthetic">Synthetic</option>
      </select>
      <label>搜索</label><input id="src-search" placeholder="BTC, ETH..." oninput="srcState.search=this.value;srcState.page=1;loadSourceSymbols()">
    </div>
    <div class="section">
      <table><thead><tr><th><input type="checkbox" class="checkbox" onchange="document.querySelectorAll('.src-check').forEach(c=>{c.checked=this.checked;toggleSelect(c.value,this.checked)})"></th><th>标的</th><th>类型</th><th>已下载</th><th>操作</th></tr></thead>
      <tbody id="src-body"></tbody></table>
      <div id="src-pager"></div>
    </div>
    <div class="batch-bar" id="batch-bar" style="display:none">
      <span id="batch-info"></span>
      <div class="row" style="margin-top:8px">
        <label>开始</label><input type="date" id="batch-start" value="2024-01-01">
        <label>结束</label><input type="date" id="batch-end" value="2024-12-31">
        <label>粒度</label><select id="batch-tf"><option>1d</option><option>1h</option><option>4h</option><option>15m</option><option>5m</option><option>1m</option></select>
        <button class="btn success" onclick="doBatchIngest()">批量下载</button>
      </div>
      <div id="batch-progress"></div>
    </div>`;
  document.getElementById('src-select').value=srcState.source;
  document.getElementById('src-search').value=srcState.search;
  loadSourceSymbols();
}
function toggleSelect(sym,checked){
  if(checked)srcState.selected.add(sym);else srcState.selected.delete(sym);
  updateBatchBar();
}
function updateBatchBar(){
  const bar=document.getElementById('batch-bar');
  if(!bar)return;
  if(srcState.selected.size>0){bar.style.display='block';
    document.getElementById('batch-info').textContent=`已选 ${srcState.selected.size} 个标的`;}
  else bar.style.display='none';
}
async function loadSourceSymbols(){
  const body=document.getElementById('src-body');
  body.innerHTML='<tr><td colspan="5" style="text-align:center;color:#888">加载中...</td></tr>';
  try{
    const params=`?page=${srcState.page}&size=50&search=${encodeURIComponent(srcState.search)}`;
    const data=await api(`/sources/${srcState.source}/symbols${params}`);
    if(data.symbols.length===0){body.innerHTML='<tr><td colspan="5" style="text-align:center;color:#888">无匹配标的</td></tr>';return}
    body.innerHTML=data.symbols.map(s=>`<tr>
      <td><input type="checkbox" class="checkbox src-check" value="${s.unified_symbol}" ${srcState.selected.has(s.unified_symbol)?'checked':''} onchange="toggleSelect(this.value,this.checked)"></td>
      <td>${esc(s.unified_symbol)}</td><td>${s.asset_type||''}</td>
      <td>${s.downloaded?'<span class="badge downloaded">✅ 已下载</span>':'<span class="badge missing">—</span>'}</td>
      <td>${s.downloaded?`<button class="btn small" onclick="quickIngest('${s.unified_symbol}','${srcState.source}')">补全</button> <button class="btn small" onclick="navigate('local',{symbol:'${s.unified_symbol}'})">查看</button>`:`<button class="btn small success" onclick="quickIngest('${s.unified_symbol}','${srcState.source}')">下载</button>`}</td>
    </tr>`).join('');
    const pager=document.getElementById('src-pager');
    if(data.total_pages>1){
      let html='<div class="pagination">';
      for(let i=1;i<=Math.min(data.total_pages,10);i++)
        html+=`<a class="${i===srcState.page?'active':''}" onclick="srcState.page=${i};loadSourceSymbols()">${i}</a>`;
      if(data.total_pages>10)html+=`<span>... ${data.total_pages} pages</span>`;
      html+='</div>';
      pager.innerHTML=html;
    }else pager.innerHTML='';
  }catch(e){body.innerHTML=`<tr><td colspan="5" class="msg err">Error: ${e}</td></tr>`}
}
async function quickIngest(sym,src){
  let info={earliest_available:'2020-01-01',latest_available:'',timeframes:['1d']};
  try{info=await api(`/sources/${src}/info?symbol=${encodeURIComponent(sym)}`)}catch{}
  const today=info.latest_available||new Date().toISOString().split('T')[0];
  const defaultStart=info.local_latest?info.local_latest.split('T')[0]:info.earliest_available;
  const localInfo=info.local_earliest?`\n本地已有: ${info.local_earliest.split('T')[0]} ~ ${info.local_latest.split('T')[0]}`:'\n本地无数据';
  const startInput=prompt(`下载 ${sym} 从 ${src}\n数据源范围: ${info.earliest_available} ~ ${today}${localInfo}\n\n输入开始日期:`,defaultStart);
  if(!startInput)return;
  const endInput=prompt(`结束日期:`,today);
  if(!endInput)return;
  const tfOptions=info.timeframes||['1d'];
  const tfInput=prompt(`时间粒度 (${tfOptions.join('/')}):`,'1d');
  if(!tfInput||!tfOptions.includes(tfInput)){alert(`无效粒度: ${tfInput}\n可用: ${tfOptions.join(', ')}`);return}
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}&source=${src}&start=${startInput}&end=${endInput}&timeframe=${tfInput}`,{method:'POST'});
    alert(`完成: ${r.ingested} 行`);loadSourceSymbols();}
  catch(e){alert(`失败: ${e}`)}
}
async function doBatchIngest(){
  const syms=[...srcState.selected].join(',');
  const start=document.getElementById('batch-start').value;
  const end=document.getElementById('batch-end').value;
  const tf=document.getElementById('batch-tf').value;
  const prog=document.getElementById('batch-progress');
  prog.innerHTML='<div class="msg">提交中...</div>';
  try{
    const r=await api(`/ingest/batch?symbols=${encodeURIComponent(syms)}&start=${start}&end=${end}&timeframe=${tf}`,{method:'POST'});
    const poll=async()=>{
      const p=await api(`/ingest/progress/${r.batch_id}`);
      const pct=Math.round(p.completed/p.total*100);
      prog.innerHTML=`<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div><div style="font-size:13px">${p.completed}/${p.total} — ${p.current} ${p.results.length?p.results[p.results.length-1].status:''}</div>`;
      if(p.status==='completed'){
        prog.innerHTML+=`<div class="msg ok">批量下载完成</div>`;
        srcState.selected.clear();updateBatchBar();loadSourceSymbols();
      }else setTimeout(poll,1000);
    };
    poll();
  }catch(e){prog.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}

// ── Local Symbols ──────────────────────────────────────────
async function renderLocal(params={}){
  if(params.symbol){currentSymbol=params.symbol}
  const c=document.getElementById('content');
  c.innerHTML=`<div class="split">
    <div class="split-left" id="local-list"><div style="padding:12px"><input id="local-search" placeholder="搜索..." oninput="filterLocal(this.value)" style="width:100%"></div><div id="local-items"></div></div>
    <div class="split-right" id="local-detail"><div style="padding:40px;color:#888">选择左侧标的查看详情</div></div>
  </div>`;
  try{
    const data=await api('/symbols');
    window._localSymbols=data.symbols;
    renderLocalList(data.symbols);
    if(currentSymbol)selectSymbol(currentSymbol);
  }catch(e){document.getElementById('local-items').innerHTML=`<div class="msg err">${e}</div>`}
}
function renderLocalList(symbols){
  document.getElementById('local-items').innerHTML=symbols.map(s=>
    `<div class="sym-item ${s.unified_symbol===currentSymbol?'active':''}" onclick="selectSymbol('${s.unified_symbol}')">
      <span>${esc(s.unified_symbol)}</span><span class="badge downloaded">✅</span>
    </div>`).join('');
}
function filterLocal(q){
  const filtered=window._localSymbols.filter(s=>s.unified_symbol.toLowerCase().includes(q.toLowerCase()));
  renderLocalList(filtered);
}
async function selectSymbol(sym){
  currentSymbol=sym;
  document.querySelectorAll('.sym-item').forEach(e=>e.classList.remove('active'));
  renderLocalList(window._localSymbols);
  const detail=document.getElementById('local-detail');
  detail.innerHTML='<div style="padding:20px;color:#888">加载中...</div>';
  try{
    const symInfo=window._localSymbols.find(s=>s.unified_symbol===sym)||{};
    const ohlcv=await fetch(`/api/v1/ohlcv?symbol=${encodeURIComponent(sym)}&limit=200`).then(r=>r.json());
    const rows=ohlcv.data||[];
    detail.innerHTML=`
      <div style="padding:0 0 12px"><strong style="font-size:18px;color:#4fc3f7">${esc(sym)}</strong>
      <span style="color:#888;margin-left:12px">${symInfo.asset_type||''} · ${symInfo.sources?.join(', ')||''} · ${fmt(symInfo.row_count)}行</span>
      <span style="color:#888;margin-left:12px">${shortDate(symInfo.earliest)} ~ ${shortDate(symInfo.latest)}</span></div>
      <div class="chart-container"><div id="chart" style="height:400px"></div></div>
      <div class="row"><span style="color:#888">截选范围:</span><input type="date" id="range-start"><span>~</span><input type="date" id="range-end">
        <button class="btn small" onclick="rangeIngest('${esc(sym)}')">补全此范围</button>
        <button class="btn small" onclick="rangeExport('${esc(sym)}')">导出CSV</button>
      </div>
      <div class="section"><h3>数据预览 (最近 20 行)</h3>
        <table><thead><tr><th>时间</th><th>开</th><th>高</th><th>低</th><th>收</th><th>量</th></tr></thead>
        <tbody>${rows.slice(-20).reverse().map(r=>`<tr><td>${shortDate(r.ts)}</td><td>${r.open.toFixed(2)}</td><td>${r.high.toFixed(2)}</td><td>${r.low.toFixed(2)}</td><td>${r.close.toFixed(2)}</td><td>${fmt(r.volume)}</td></tr>`).join('')}</tbody></table>
      </div>
      <div style="margin-top:16px"><button class="btn danger" onclick="deleteSymbol('${esc(sym)}')">删除此标的数据</button>
      <button class="btn" onclick="redownload('${esc(sym)}')">重新下载</button></div>`;
    if(rows.length>0&&typeof LightweightCharts!=='undefined'){
      const chart=LightweightCharts.createChart(document.getElementById('chart'),{
        width:800,height:400,layout:{background:{color:'#0f1419'},textColor:'#e0e0e0'},
        grid:{vertLines:{color:'#1a2332'},horzLines:{color:'#1a2332'}},
        timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#2a3f5f'},
        rightPriceScale:{borderColor:'#2a3f5f'},
      });
      const candle=chart.addCandlestickSeries({upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350'});
      candle.setData(rows.map(r=>({time:r.ts.split('T')[0],open:r.open,high:r.high,low:r.low,close:r.close})));
      const vol=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'',scaleMargins:{top:0.8,bottom:0}});
      vol.setData(rows.map(r=>({time:r.ts.split('T')[0],value:r.volume,color:r.close>=r.open?'#26a69a80':'#ef535080'})));
      chart.timeScale().fitContent();
      chartInstance=chart;
      document.getElementById('range-start').value=rows[0].ts.split('T')[0];
      document.getElementById('range-end').value=rows[rows.length-1].ts.split('T')[0];
    }
  }catch(e){detail.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}
async function rangeIngest(sym){
  const start=document.getElementById('range-start').value;
  const end=document.getElementById('range-end').value;
  if(!confirm(`补全 ${sym} 从 ${start} 到 ${end}？`))return;
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}&start=${start}&end=${end}`,{method:'POST'});
    alert(`完成: ${r.ingested} 行`);selectSymbol(sym);}
  catch(e){alert(`失败: ${e}`)}
}
function rangeExport(sym){
  const start=document.getElementById('range-start').value;
  const end=document.getElementById('range-end').value;
  window.open(`/api/v1/ohlcv?symbol=${encodeURIComponent(sym)}&start=${start}&end=${end}&format=csv`);
}
async function deleteSymbol(sym){
  if(!confirm(`确认删除 ${sym} 的全部数据？此操作不可撤销！`))return;
  try{const r=await api(`/symbols/${encodeURIComponent(sym)}`,{method:'DELETE'});
    alert(`已删除 ${r.rows_removed} 行`);currentSymbol=null;renderLocal();}
  catch(e){alert(`失败: ${e}`)}
}
async function redownload(sym){
  if(!confirm(`重新下载 ${sym}？`))return;
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}`,{method:'POST'});
    alert(`完成: ${r.ingested} 行`);selectSymbol(sym);}
  catch(e){alert(`失败: ${e}`)}
}

// ── Config ─────────────────────────────────────────────────
async function renderConfig(){
  const c=document.getElementById('content');
  c.innerHTML='<div id="cfg-content">加载中...</div>';
  try{
    const[config,cache,disk]=await Promise.all([
      api('/config').catch(e=>({database_url:'(error)',proxy:{enabled:false,type:'http',url:''},_err:e})),
      api('/cache').catch(e=>({ttl:300,keys:0,_err:e})),
      api('/disk').catch(e=>({total_gb:0,used_gb:0,used_percent:0,db_file_size_mb:0,_err:e}))
    ]);
    document.getElementById('cfg-content').innerHTML=`
      <div class="section"><h3>数据库</h3>
        <div class="row"><label>当前路径</label><code>${esc(config.database_url)}</code></div>
        <div class="row"><label>状态</label><span class="${config.database_url?'ok':'bad'}">● ${config.database_url?'已连接':'未连接'}</span></div>
        <div class="row" style="color:#888;font-size:12px">修改路径需重启服务生效</div>
      </div>
      <div class="section"><h3>代理</h3>
        <div class="row"><label>启用</label><div class="switch ${config.proxy.enabled?'on':''}" id="proxy-switch" onclick="toggleProxy()"></div></div>
        <div class="row"><label>类型</label><select id="proxy-type"><option value="http" ${config.proxy.type==='http'?'selected':''}>HTTP</option><option value="socks5" ${config.proxy.type==='socks5'?'selected':''}>SOCKS5</option></select></div>
        <div class="row"><label>地址</label><input id="proxy-url" value="${esc(config.proxy.url)}" size="40"></div>
        <button class="btn success" onclick="saveProxy()">保存并应用（立即生效）</button>
        <div id="proxy-msg"></div>
      </div>
      <div class="section"><h3>缓存</h3>
        <div class="row"><label>类型</label>InMemoryCache</div>
        <div class="row"><label>TTL</label>${cache.ttl}秒</div>
        <div class="row"><label>当前键数</label>${cache.keys}</div>
        <button class="btn danger" onclick="clearCache()">清空缓存</button>
        <div id="cache-msg"></div>
      </div>
      <div class="section"><h3>磁盘</h3>
        <div class="row"><label>总容量</label>${disk.total_gb} GB</div>
        <div class="row"><label>已用</label>${disk.used_gb} GB (${disk.used_percent}%)</div>
        <div class="row"><label>数据库文件</label>${disk.db_file_size_mb} MB</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${disk.used_percent}%"></div></div>
      </div>`;
  }catch(e){document.getElementById('cfg-content').innerHTML=`<div class="msg err">${e}</div>`}
}
function toggleProxy(){
  const sw=document.getElementById('proxy-switch');
  sw.classList.toggle('on');
}
async function saveProxy(){
  const enabled=document.getElementById('proxy-switch').classList.contains('on');
  const type=document.getElementById('proxy-type').value;
  const url=document.getElementById('proxy-url').value;
  const msg=document.getElementById('proxy-msg');
  msg.innerHTML='<div class="msg">保存中...</div>';
  try{const r=await api(`/proxy?enabled=${enabled}&proxy_type=${type}&url=${encodeURIComponent(url)}`,{method:'PUT'});
    msg.innerHTML='<div class="msg ok">已保存，立即生效</div>';}
  catch(e){msg.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}
async function clearCache(){
  try{const r=await api('/cache',{method:'DELETE'});alert(`已清空 ${r.keys_removed} 个缓存键`);}
  catch(e){alert(`失败: ${e}`)}
}

// ── Logs ───────────────────────────────────────────────────
let logState={page:1,action:'',symbol:''};
async function renderLogs(){
  const c=document.getElementById('content');
  c.innerHTML=`
    <div class="row">
      <label>类型</label><select id="log-action" onchange="logState.action=this.value;logState.page=1;loadLogs()"><option value="">全部</option><option value="ingest">采集</option><option value="batch_ingest">批量采集</option><option value="delete">删除</option><option value="proxy_change">代理变更</option></select>
      <label>标的</label><input id="log-symbol" placeholder="过滤..." oninput="logState.symbol=this.value;logState.page=1;loadLogs()">
      <button class="btn" onclick="loadLogs()">刷新</button>
    </div>
    <div class="section"><table><thead><tr><th>时间</th><th>标的</th><th>操作</th><th>行数</th><th>状态</th><th>数据源</th><th>错误</th></tr></thead><tbody id="log-body"></tbody></table><div id="log-pager"></div></div>`;
  loadLogs();
}
async function loadLogs(){
  const params=`?page=${logState.page}&size=50&action=${logState.action}&symbol=${encodeURIComponent(logState.symbol)}`;
  try{
    const data=await api(`/logs${params}`);
    if(data.logs.length===0){document.getElementById('log-body').innerHTML='<tr><td colspan="7" style="text-align:center;color:#888">无记录</td></tr>';return}
    document.getElementById('log-body').innerHTML=data.logs.map(l=>`<tr>
      <td>${l.timestamp.replace('T',' ').split('.')[0]}</td><td>${esc(l.symbol)}</td><td>${l.action}</td>
      <td>${l.rows_affected||0}</td><td>${l.status==='success'?'✅':'❌'}</td><td>${l.source||'-'}</td>
      <td style="color:#ef5350;font-size:12px">${esc(l.error_message)||''}</td></tr>`).join('');
    const pager=document.getElementById('log-pager');
    if(data.total_pages>1){let h='<div class="pagination">';
      for(let i=1;i<=Math.min(data.total_pages,10);i++)h+=`<a class="${i===logState.page?'active':''}" onclick="logState.page=${i};loadLogs()">${i}</a>`;
      if(data.total_pages>10)h+=`<span>... ${data.total_pages} pages</span>`;
      h+='</div>';pager.innerHTML=h;
    }else pager.innerHTML='';
  }catch(e){document.getElementById('log-body').innerHTML=`<tr><td colspan="7" class="msg err">${e}</td></tr>`}
}

// ── Init ───────────────────────────────────────────────────
startHealthCheck();
renderDashboard();
</script>
</body>
</html>"""
