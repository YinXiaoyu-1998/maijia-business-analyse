#!/usr/bin/env python3
"""Render a self-contained monthly profit and profit-rate HTML report."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key in ("年份", "月份"):
            row[key] = int(row[key])
        for key in ("净利润", "营业额", "利润率"):
            row[key] = float(row[key]) if row.get(key) not in (None, "") else None
    return rows


def build_payload(input_dir: Path, company: str) -> dict[str, Any]:
    summary = json.loads((input_dir / "monthly_profit_summary.json").read_text(encoding="utf-8"))
    rows = read_csv(input_dir / "monthly_profit_metrics.csv")
    stores = summary["stores"]
    years = summary["years"]
    data: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    for store in stores:
        data[store] = {}
        for year in years:
            periods = {row["月份"]: row for row in rows if row["门店"] == store and row["年份"] == year}
            complete = [periods.get(month, {
                "月份": month,
                "净利润": None,
                "营业额": None,
                "利润率": None,
                "利润状态": "无数据／门店尚未开业",
                "利润率状态": "无数据／门店尚未开业",
            }) for month in range(1, 13)]
            data[store][str(year)] = {
                "profit": [{"month": row["月份"], "value": row["净利润"], "status": row["利润状态"]} for row in complete],
                "margin": [{"month": row["月份"], "value": row["利润率"], "status": row["利润率状态"], "revenue": row["营业额"]} for row in complete],
            }
    return {
        "meta": {
            "title": f"{company}月利润与利润率趋势",
            "generated": date.today().isoformat(),
            "profit_source": Path(summary["profit_source"]).name,
            "business_file_count": len(summary["business_sources"]),
            "rate_rule": summary["profit_rate_rule"],
        },
        "stores": stores,
        "years": years,
        "data": data,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root { --ink:#14213d; --muted:#64748b; --line:#dbe4ee; --teal:#087c85; --orange:#c86400; --red:#b42318; --bg:#f6f8fb; --card:#fff; }
    * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }
    main { max-width:1540px; margin:0 auto; padding:30px 28px 52px; } .eyebrow { color:var(--teal); font-size:12px; font-weight:800; letter-spacing:.08em; } h1 { margin:6px 0 8px; font-size:28px; } .intro { color:var(--muted); margin:0; line-height:1.65; }
    .method { margin:20px 0 30px; padding:13px 16px; background:#eaf6f7; color:#20515b; border-left:4px solid var(--teal); border-radius:6px; font-size:13px; }
    section { margin-top:36px; } .section-head { display:flex; justify-content:space-between; gap:20px; align-items:flex-end; margin-bottom:16px; } h2 { font-size:20px; margin:0; } .section-head p { margin:0; color:var(--muted); font-size:13px; text-align:right; }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; } .card { background:var(--card); border:1px solid #e7edf4; border-radius:12px; box-shadow:0 5px 20px rgba(15,23,42,.045); overflow:hidden; }
    .card-head { padding:16px 16px 0; display:flex; justify-content:space-between; align-items:center; gap:12px; } h3 { margin:0; font-size:16px; } select { color:var(--ink); font:inherit; font-size:13px; font-weight:650; padding:7px 32px 7px 10px; border:1px solid #8ab9bf; border-radius:7px; background:#f8ffff; }
    .chart-wrap { position:relative; padding:4px 10px 12px; } svg { display:block; width:100%; height:auto; overflow:visible; } .axis { font-size:10px; fill:var(--muted); } .grid-line { stroke:var(--line); stroke-width:1; } .zero { stroke:#93a6b8; stroke-width:1.25; } .trend { fill:none; stroke:var(--teal); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; } .dot { fill:#fff; stroke:var(--teal); stroke-width:2.5; } .negative-dot { stroke:var(--red); } .month-hit { fill:transparent; cursor:help; } .empty { fill:#94a3b8; font-size:13px; font-weight:650; }
    .tooltip { position:fixed; z-index:10; pointer-events:none; display:none; max-width:245px; padding:9px 11px; border-radius:7px; background:rgba(15,23,42,.94); color:#fff; font-size:12px; line-height:1.5; box-shadow:0 5px 18px rgba(15,23,42,.2); } .tooltip b { display:block; font-size:13px; }
    footer { margin-top:32px; color:var(--muted); font-size:12px; }
    @media (max-width:1050px) { .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } } @media (max-width:690px) { main { padding:22px 14px 35px; } .grid { grid-template-columns:1fr; } .section-head { align-items:flex-start; flex-direction:column; } .section-head p { text-align:left; } }
  </style>
</head>
<body><main>
  <div class="eyebrow">经营利润专题</div><h1>__TITLE__</h1>
  <p class="intro">三家门店按自然月展示净利润与利润率；悬浮月份位置可查看具体值或无数据原因。</p>
  <div class="method" id="method"></div>
  <section><div class="section-head"><div><h2>月利润趋势</h2></div><p>单位：元；负数表示亏损。空值不补零、不连线。</p></div><div class="grid" id="profitGrid"></div></section>
  <section><div class="section-head"><div><h2>月利润率趋势</h2></div><p>利润率 = 净利润 ÷ 当月营业额汇总；纵轴为百分比。</p></div><div class="grid" id="marginGrid"></div></section>
  <footer id="footer"></footer>
</main><div class="tooltip" id="tooltip"></div>
<script>const REPORT=__PAYLOAD__;
const M=[1,2,3,4,5,6,7,8,9,10,11,12]; const tip=document.getElementById('tooltip');
const money=v=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY',minimumFractionDigits:2,maximumFractionDigits:2}).format(v);
const percent=v=>`${(v*100).toFixed(2)}%`; const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ticks(min,max){ if(min===max){min-=1;max+=1;} const pad=(max-min)*.14||1; min-=pad;max+=pad; if(min<0&&max>0){min=Math.min(min,0);max=Math.max(max,0);} return Array.from({length:5},(_,i)=>min+(max-min)*i/4); }
function createChart(store,type){ const card=document.createElement('article'); card.className='card'; const id=`${type}-${store}`; card.innerHTML=`<div class="card-head"><h3>${esc(store)}</h3><select aria-label="选择年份" id="${id}">${REPORT.years.map(y=>`<option value="${y}">${y} 年</option>`).join('')}</select></div><div class="chart-wrap" id="${id}-chart"></div>`; const select=card.querySelector('select'); select.value=REPORT.years.at(-1); const draw=()=>renderLine(card.querySelector('.chart-wrap'),store,type,Number(select.value)); select.addEventListener('change',draw); draw(); return card; }
function renderLine(host,store,type,year){ const rows=REPORT.data[store][String(year)][type]; const w=450,h=260,l=52,r=16,t=20,b=43,pw=w-l-r,ph=h-t-b; const vals=rows.filter(x=>x.value!==null).map(x=>x.value); const scaleTicks=vals.length?ticks(Math.min(...vals),Math.max(...vals)):[]; const y=v=>t+(scaleTicks.at(-1)-v)/(scaleTicks.at(-1)-scaleTicks[0])*ph; const x=m=>l+(m-1)*pw/11; const formatter=type==='profit'?money:percent; const label=type==='profit'?'净利润':'利润率'; let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${store}${year}年${label}折线图">`;
 if(!vals.length){svg+=`<text x="${w/2}" y="${h/2}" text-anchor="middle" class="empty">该年度暂无可展示数据</text>`;} else {scaleTicks.forEach((v,i)=>{const yy=t+ph-i*ph/4;svg+=`<line x1="${l}" x2="${w-r}" y1="${yy}" y2="${yy}" class="${Math.abs(v)<1e-9?'zero':'grid-line'}"/><text x="${l-7}" y="${yy+4}" text-anchor="end" class="axis">${type==='profit'?(Math.abs(v)>=10000?(v/10000).toFixed(1)+'万':Math.round(v)):percent(v)}</text>`;}); const segments=[];let current=[];rows.forEach(p=>{if(p.value===null){if(current.length){segments.push(current);current=[];}}else current.push(p);});if(current.length)segments.push(current);segments.forEach(seg=>svg+=`<path class="trend" d="${seg.map((p,i)=>`${i?'L':'M'}${x(p.month).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')}"/>`); rows.filter(p=>p.value!==null).forEach(p=>svg+=`<circle class="dot ${p.value<0?'negative-dot':''}" cx="${x(p.month)}" cy="${y(p.value)}" r="4.4"/>`); }
 M.forEach(m=>{const p=rows.find(x=>x.month===m);const xx=x(m);svg+=`<text x="${xx}" y="${h-16}" text-anchor="middle" class="axis">${m}月</text><rect class="month-hit" data-month="${m}" x="${xx-pw/23}" y="${t}" width="${pw/11}" height="${ph}"/>`;}); svg+='</svg>'; host.innerHTML=svg; host.querySelectorAll('.month-hit').forEach(hit=>{const p=rows.find(x=>x.month===Number(hit.dataset.month)); const detail=p.value===null?`<b>${year} 年 ${p.month} 月</b>${esc(p.status||'无数据')}`:`<b>${year} 年 ${p.month} 月</b>${label}：${formatter(p.value)}${type==='margin'&&p.revenue!==null?`<br>营业额：${money(p.revenue)}`:''}`; hit.addEventListener('mouseenter',e=>{tip.innerHTML=detail;tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';});hit.addEventListener('mousemove',e=>{tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';});hit.addEventListener('mouseleave',()=>tip.style.display='none');}); }
document.getElementById('method').textContent=REPORT.meta.rate_rule; document.getElementById('footer').textContent=`生成日期：${REPORT.meta.generated} ｜ 利润来源：${REPORT.meta.profit_source} ｜ 营业额来源：${REPORT.meta.business_file_count} 个营业分组表导出文件`;
REPORT.stores.forEach(s=>document.getElementById('profitGrid').appendChild(createChart(s,'profit'))); REPORT.stores.forEach(s=>document.getElementById('marginGrid').appendChild(createChart(s,'margin')));
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    args = parser.parse_args()
    payload = build_payload(args.input_dir, args.company)
    html = HTML_TEMPLATE.replace("__TITLE__", payload["meta"]["title"]).replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
