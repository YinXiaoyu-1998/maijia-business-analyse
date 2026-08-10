#!/usr/bin/env python3
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs/monthly_report_202607/麦家小馆_2026年7月经营月报.html"
METRICS = ROOT / "outputs/monthly_report_202607/analysis/monthly_store_metrics.csv"


def f(v):
    try: return float(v or 0)
    except ValueError: return 0.0


def line_svg(series, width=900, height=245):
    months = list(range(1, 13))
    vals = [v for y in series.values() for v in y.values() if v is not None]
    top = max(vals) * 1.12 if vals else 1
    left, right, upper, lower = 55, 25, 25, 38
    colors = {2025: "#94a3b8", 2026: "#2f5b9f", 2024: "#b85c00"}
    parts = []
    for tick in range(5):
        value = top * tick / 4
        y = height - lower - (height-upper-lower)*tick/4
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e5e9ec"/><text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-size="10" fill="#657386">{value:.0f}</text>')
    for month in months:
        x = left + (month-1)*(width-left-right)/11
        parts.append(f'<text x="{x:.1f}" y="{height-10}" text-anchor="middle" font-size="10" fill="#657386">{month}月</text>')
    for year, values in sorted(series.items()):
        pts=[]
        for month in months:
            if month not in values: continue
            x=left+(month-1)*(width-left-right)/11
            y=height-lower-values[month]*(height-upper-lower)/top
            pts.append((x,y,values[month]))
        dash = ' stroke-dasharray="6 5"' if year == 2025 else ''
        path=' '.join(f'{x:.1f},{y:.1f}' for x,y,_ in pts)
        parts.append(f'<polyline points="{path}" fill="none" stroke="{colors[year]}" stroke-width="3"{dash}/>')
        parts.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{colors[year]}"/>' for x,y,_ in pts)
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="2025至2026年月营业收入趋势">{"".join(parts)}</svg>'


def main():
    monthly = defaultdict(lambda: defaultdict(float))
    store_monthly = defaultdict(lambda: defaultdict(float))
    channel = defaultdict(lambda: defaultdict(float))
    with METRICS.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            year, month = map(int, r["month_label"].split("/"))
            if year not in (2025, 2026) or (year == 2026 and month > 7): continue
            key=(year,month)
            monthly[year][month] += f(r["net_revenue"])/10000
            store_monthly[r["门店名称"]][key] += f(r["net_revenue"])
            channel[key]["dine"] += f(r["dine_in_revenue"])
            channel[key]["delivery"] += f(r["delivery_revenue"])

    ytd25=sum(monthly[2025][m] for m in range(1,8))*10000
    ytd26=sum(monthly[2026][m] for m in range(1,8))*10000
    yoy=ytd26/ytd25-1
    dine25=sum(channel[(2025,m)]["dine"] for m in range(1,8)); dine26=sum(channel[(2026,m)]["dine"] for m in range(1,8))
    del25=sum(channel[(2025,m)]["delivery"] for m in range(1,8)); del26=sum(channel[(2026,m)]["delivery"] for m in range(1,8))

    month_rows=[]
    prev=None
    for m in range(1,13):
        v25=monthly[2025].get(m)
        v26=monthly[2026].get(m)
        yoy_m=(v26/v25-1) if v25 and v26 else None
        mom=(v26/prev-1) if v26 and prev else None
        v26_text=f"{v26:.1f}" if v26 is not None else "—"
        yoy_text=f"{yoy_m*100:+.1f}%" if yoy_m is not None else "—"
        mom_text=f"{mom*100:+.1f}%" if mom is not None else "—"
        month_rows.append(f"<tr><td>{m}月</td><td>{v25:.1f}</td><td>{v26_text}</td><td>{yoy_text}</td><td>{mom_text}</td></tr>")
        if v26 is not None: prev=v26

    store_rows=[]
    for store, vals in sorted(store_monthly.items()):
        a=sum(vals[(2025,m)] for m in range(1,8)); b=sum(vals[(2026,m)] for m in range(1,8))
        store_rows.append(f"<tr><td><b>{store.replace('麦家小馆（','').replace('）','')}</b></td><td>{a/10000:.1f}</td><td>{b/10000:.1f}</td><td>{(b/a-1)*100:+.1f}%</td><td>{(b-a)/10000:+.1f}</td></tr>")

    section=f"""
    <section class="section" id="multi-year">
      <div class="section-head"><div><div class="kicker">07 Multi-year Benchmark</div><h2>跨年度经营趋势：2025全年与2026年1—7月同比、环比</h2></div>
      <p class="note">营业收入统一来自营业分组表，三店聚合后重新计算；2026年8—12月尚未发生，不作预测。</p></div>
      <div class="grid-4">
        <div class="metric"><span>2026年1—7月收入</span><b>{ytd26/10000:.1f}万</b><small>同期同比 {yoy*100:+.1f}%</small></div>
        <div class="metric"><span>2025年1—7月收入</span><b>{ytd25/10000:.1f}万</b><small>同比基准期</small></div>
        <div class="metric"><span>堂食累计同比</span><b>{(dine26/dine25-1)*100:+.1f}%</b><small>{dine26/10000:.1f}万 vs {dine25/10000:.1f}万</small></div>
        <div class="metric"><span>外卖累计同比</span><b>{(del26/del25-1)*100:+.1f}%</b><small>{del26/10000:.1f}万 vs {del25/10000:.1f}万</small></div>
      </div>
      <div class="panel full-row"><div class="panel-head"><h3>三店月营业收入趋势</h3><span class="label">万元；2025虚线，2026实线</span></div>{line_svg(monthly)}<div class="legend"><span><i class="swatch" style="background:#94a3b8"></i>2025</span><span><i class="swatch" style="background:#2f5b9f"></i>2026</span></div></div>
      <div class="grid-2 full-row">
        <div class="panel"><div class="panel-head"><h3>月度同比与环比</h3><span class="label">三店合计，万元</span></div><div class="table-wrap"><table class="compact-table"><thead><tr><th>月份</th><th>2025</th><th>2026</th><th>同比</th><th>2026环比</th></tr></thead><tbody>{''.join(month_rows)}</tbody></table></div></div>
        <div class="panel"><div class="panel-head"><h3>门店1—7月累计对比</h3><span class="label">同周期可比</span></div><div class="table-wrap"><table class="compact-table"><thead><tr><th>门店</th><th>2025(万)</th><th>2026(万)</th><th>同比</th><th>增减(万)</th></tr></thead><tbody>{''.join(store_rows)}</tbody></table></div>
        <div class="callout" style="margin-top:12px"><b>2024数据：</b>现有营业明细最早从2025年1月开始，暂不能生成2024同比。补充2024年1月1日至12月31日同口径营业分组表后，可直接扩展为三年趋势。</div></div>
      </div>
    </section>
    """
    css="""<style id="multiYearStyle">#multi-year svg{width:100%;height:auto;display:block}#multi-year .metric small{display:block;margin-top:6px;color:var(--muted)}#multi-year .compact-table th:not(:first-child),#multi-year .compact-table td:not(:first-child){text-align:right}</style>"""
    doc=REPORT.read_text(encoding="utf-8")
    if 'id="multi-year"' in doc: raise SystemExit("multi-year already exists")
    doc=doc.replace("</head>",css+"\n</head>")
    doc=doc.replace('<a href="#annual-cost">全年成本</a>','<a href="#multi-year">跨年趋势</a>\n        <a href="#annual-cost">全年成本</a>')
    doc=doc.replace('    <section class="section" id="annual-cost">',section+'\n    <section class="section" id="annual-cost">')
    doc=doc.replace('<div class="kicker">07 Year-to-date Cost View</div>','<div class="kicker">08 Year-to-date Cost View</div>')
    doc=doc.replace('<div class="kicker">08 Performance &amp; Cost</div>','<div class="kicker">09 Performance &amp; Cost</div>')
    doc=doc.replace('<div class="kicker">09 Daypart Attribution</div>','<div class="kicker">10 Daypart Attribution</div>')
    doc=doc.replace('<div class="kicker">10 Hourly Revenue</div>','<div class="kicker">11 Hourly Revenue</div>')
    REPORT.write_text(doc,encoding="utf-8")
    print(REPORT)


if __name__=='__main__': main()
