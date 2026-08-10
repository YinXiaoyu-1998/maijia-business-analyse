#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs/monthly_report_202607/麦家小馆_2026年7月经营月报.html"
PERF = ROOT / "outputs/monthly_report_202607/performance_2026.json"
STORES = ("常营店", "苏州街", "保利店")


def find_index(rows, text):
    for i, value in enumerate(rows[1]):
        if text in str(value or ""):
            return i
    raise ValueError(text)


def parse_month(rows):
    energy_i = find_index(rows, "能耗占比")
    labor_i = find_index(rows, "人员工资")
    out = {}
    for r in rows[3:]:
        if r and r[0] in STORES:
            out[r[0]] = {
                "revenue": float(r[1]),
                "food_rate": float(r[3]), "food_amount": float(r[8]),
                "energy_rate": float(r[energy_i]), "energy_amount": float(r[energy_i + 1]),
                "labor_rate": float(r[labor_i]), "labor_amount": float(r[labor_i + 1]),
            }
    return out


def weighted(rows, amount):
    return sum(x[amount] for x in rows.values()) / sum(x["revenue"] for x in rows.values())


def spark(values, color, width=520, height=140):
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    pts = []
    for i, value in enumerate(values):
        x = 24 + i * (width - 48) / (len(values) - 1)
        y = 18 + (hi - value) * (height - 48) / span
        pts.append((x, y, value))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/><text x="{x:.1f}" y="{y-9:.1f}" text-anchor="middle" font-size="10" fill="#334155">{v:.1f}%</text>' for x,y,v in pts)
    months = "".join(f'<text x="{x:.1f}" y="{height-5}" text-anchor="middle" font-size="10" fill="#657386">{i+1}月</text>' for i,(x,_,_) in enumerate(pts))
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="1至7月趋势"><polyline points="{poly}" fill="none" stroke="{color}" stroke-width="3"/>{dots}{months}</svg>'


def main():
    perf = json.loads(PERF.read_text(encoding="utf-8"))
    months = [parse_month(perf[f"{i}月"]) for i in range(1, 8)]
    agg = []
    for rows in months:
        rev = sum(x["revenue"] for x in rows.values())
        food = weighted(rows, "food_amount")
        energy = weighted(rows, "energy_amount")
        labor = weighted(rows, "labor_amount")
        agg.append({"revenue": rev, "food": food, "energy": energy, "labor": labor, "cost": food + energy})

    table_rows = "".join(
        f"<tr><td>{i+1}月</td><td>{x['revenue']/10000:.1f}</td><td>{x['food']*100:.1f}%</td><td>{x['food']*10000:,.0f}</td><td>{x['energy']*100:.1f}%</td><td>{x['energy']*10000:,.0f}</td><td>{x['labor']*100:.1f}%</td><td>{x['labor']*10000:,.0f}</td><td>{x['cost']*100:.1f}%</td></tr>"
        for i, x in enumerate(agg)
    )
    store_rows = []
    for store in STORES:
        vals = [m[store] for m in months]
        best = min(range(7), key=lambda i: vals[i]["food_rate"] + vals[i]["energy_rate"])
        jul, jan = vals[-1], vals[0]
        store_rows.append(
            f"<tr><td><b>{store}</b></td><td>{jul['revenue']/10000:.1f}万</td><td>{jul['food_rate']*10000:,.0f}元</td><td>{jul['energy_rate']*10000:,.0f}元</td><td>{jul['labor_rate']*10000:,.0f}元</td><td>{best+1}月</td><td>{(jul['food_rate']+jul['energy_rate']-jan['food_rate']-jan['energy_rate'])*100:+.2f}个百分点</td></tr>"
        )

    section = f"""
    <section class="section" id="annual-cost">
      <div class="section-head"><div><div class="kicker">07 Year-to-date Cost View</div><h2>全年成本视角：1—7月金额、占比与万元销售耗用</h2></div>
      <p class="note">统一可比口径：三店合计；每万元销售耗用=成本金额÷营业收入×10,000。食材、能耗、工资分开呈现。</p></div>
      <div class="grid-2 annual-trends">
        <div class="panel"><div class="panel-head"><h3>食材耗用率趋势</h3><span class="label">三店加权，1—7月</span></div>{spark([x['food']*100 for x in agg], '#006d77')}</div>
        <div class="panel"><div class="panel-head"><h3>能耗率趋势</h3><span class="label">三店加权，1—7月</span></div>{spark([x['energy']*100 for x in agg], '#b85c00')}</div>
        <div class="panel"><div class="panel-head"><h3>工资率趋势</h3><span class="label">三店加权，1—7月</span></div>{spark([x['labor']*100 for x in agg], '#2f5b9f')}</div>
        <div class="panel"><div class="panel-head"><h3>月营业收入趋势</h3><span class="label">三店合计，万元</span></div>{spark([x['revenue']/10000 for x in agg], '#7557a6')}</div>
      </div>
      <div class="table-wrap full-row"><table class="compact-table"><thead><tr><th>月份</th><th>销售额(万元)</th><th>食材率</th><th>每万元食材</th><th>能耗率</th><th>每万元能耗</th><th>工资率</th><th>每万元工资</th><th>食材+能耗</th></tr></thead><tbody>{table_rows}</tbody></table></div>
      <div class="panel full-row"><div class="panel-head"><h3>7月门店万元销售投入</h3><span class="label">元/万元营业收入；用于跨店横向对标</span></div>
        <div class="table-wrap"><table class="compact-table"><thead><tr><th>门店</th><th>7月销售额</th><th>万元食材</th><th>万元能耗</th><th>万元工资</th><th>年内最佳成本月</th><th>食材+能耗较1月</th></tr></thead><tbody>{''.join(store_rows)}</tbody></table></div>
      </div>
      <div class="grid-2 full-row">
        <div class="callout"><b>历史结论：</b>三店食材率在5月降至年内低位，6月反弹，7月重新改善；能耗率则连续抬升，成为成本改善的主要抵消项。销售回升必须同时绑定“每万元耗用”，否则只看营业额会掩盖效率下降。</div>
        <div class="callout"><b>人均口径说明：</b>当前绩效表只有工资金额，没有各月平均在岗人数、总工时和分时段前厅人数，暂不能可靠计算人均销售、人时销售或单人服务客数。本版先用“每万元销售工资投入”作为劳动投入代理指标。</div>
      </div>
    </section>
    """
    css = """
    <style id="annualCostStyle">
      .annual-trends{margin-top:6px}.annual-trends svg{display:block;width:100%;height:auto;min-height:150px}
      #annual-cost .compact-table th,#annual-cost .compact-table td{text-align:right;white-space:nowrap}
      #annual-cost .compact-table th:first-child,#annual-cost .compact-table td:first-child{text-align:left}
    </style>
    """
    doc = REPORT.read_text(encoding="utf-8")
    if 'id="annual-cost"' in doc:
        raise SystemExit("annual cost section already exists")
    doc = doc.replace("</head>", css + "\n</head>")
    doc = doc.replace('<a href="#performance">绩效成本</a>', '<a href="#annual-cost">全年成本</a>\n        <a href="#performance">7月绩效</a>')
    doc = doc.replace('    <section class="section" id="performance">', section + '\n    <section class="section" id="performance">')
    doc = doc.replace('<div class="kicker">07 Performance &amp; Cost</div>', '<div class="kicker">08 Performance &amp; Cost</div>')
    doc = doc.replace('<div class="kicker">08 Daypart Attribution</div>', '<div class="kicker">09 Daypart Attribution</div>')
    doc = doc.replace('<div class="kicker">09 Hourly Revenue</div>', '<div class="kicker">10 Hourly Revenue</div>')
    REPORT.write_text(doc, encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
