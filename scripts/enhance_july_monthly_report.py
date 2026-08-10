#!/usr/bin/env python3
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs/monthly_report_202607/麦家小馆_2026年7月经营月报.html"
PERF = ROOT / "outputs/monthly_report_202607/performance_2026.json"
SUMMARY = ROOT / "outputs/monthly_report_202607/analysis/monthly_meeting_summary.json"


def pct(v):
    return f"{v * 100:.1f}%"


def pp(v):
    return f"{v * 100:+.2f}个百分点"


def money(v):
    return f"{v / 10000:.1f}万"


def perf_rows(data, month):
    wanted = {"常营店", "苏州街", "保利店"}
    rows = {}
    for r in data[month]:
        if r and r[0] in wanted:
            rows[r[0]] = {
                "revenue": float(r[1]), "perf_cost": float(r[2]),
                "food": float(r[3]), "food_amount": float(r[8]),
                "energy": float(r[9]), "energy_amount": float(r[10]),
                "labor": float(r[11]), "labor_amount": float(r[12]),
            }
    return rows


def weighted(rows, key_amount):
    return sum(r[key_amount] for r in rows.values()) / sum(r["revenue"] for r in rows.values())


def main():
    perf = json.loads(PERF.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    current, previous = perf_rows(perf, "7月"), perf_rows(perf, "6月")
    by_store = {r["门店名称"]: r for r in summary["comparison"]}

    cur_rev = sum(x["revenue"] for x in current.values())
    pre_rev = sum(x["revenue"] for x in previous.values())
    rev_growth = cur_rev / pre_rev - 1
    food_cur, food_pre = weighted(current, "food_amount"), weighted(previous, "food_amount")
    energy_cur, energy_pre = weighted(current, "energy_amount"), weighted(previous, "energy_amount")
    labor_cur, labor_pre = weighted(current, "labor_amount"), weighted(previous, "labor_amount")
    cost_cur, cost_pre = food_cur + energy_cur, food_pre + energy_pre

    labels = {"常营店": "常营店", "苏州街": "苏州街店", "保利店": "通州保利店"}
    diagnoses = {
        "常营店": "收入与客流同步回升，食材率改善1.49个百分点，是三店中质量最好的增长；但外卖环比下降4.2%，客均收入下降，增长更多来自人次。",
        "苏州街": "收入增长主要由堂食和客单拉动，但食材率、能耗率、工资率同时上升，增长没有转化成成本质量，是8月首要复盘店。",
        "保利店": "收入环比增幅三店最高，食材率和工资率均改善；能耗率上升0.92个百分点，几乎抵消前两项改善，需核查设备、空调和分时用电。",
    }
    actions = {
        "常营店": "8月每周复盘外卖曝光—进店—下单漏斗；月底前将外卖收入恢复至≥11.4万元，同时将食材率稳定在≤34.1%，店长每周一提交复盘。",
        "苏州街": "8月7日前完成高耗用菜品、报损和员工工时三张清单；8月31日前将食材率降至≤33.5%、工资率降至≤19.5%，且营业收入不低于70万元。",
        "保利店": "8月10日前完成空调、后厨设备及夜间闭店能耗点检；按日记录电气表，8月31日前将能耗率降至≤4.8%，收入维持≥61万元。",
    }

    rows_html = []
    action_html = []
    bar_html = []
    for key in ("常营店", "苏州街", "保利店"):
        c, p = current[key], previous[key]
        metric = by_store[next(n for n in by_store if labels[key].replace("店", "") in n or key.replace("店", "") in n)]
        changes = {
            "food": c["food"] - p["food"], "energy": c["energy"] - p["energy"],
            "labor": c["labor"] - p["labor"], "cost": c["perf_cost"] - p["perf_cost"],
        }
        risk = changes["cost"] > 0.005 or changes["labor"] > 0.005
        badge = '<span class="perf-badge risk">需改善</span>' if risk else '<span class="perf-badge good">质量改善</span>'
        rows_html.append(f"""
          <tr><td><b>{labels[key]}</b><br>{badge}</td><td>{money(c['revenue'])}<br><small>{metric['wow_net_revenue_pct']*100:+.1f}% 环比</small></td>
          <td>{pct(c['food'])}<br><small>{pp(changes['food'])}</small></td><td>{pct(c['energy'])}<br><small>{pp(changes['energy'])}</small></td>
          <td>{pct(c['labor'])}<br><small>{pp(changes['labor'])}</small></td><td>{pct(c['perf_cost'])}<br><small>{pp(changes['cost'])}</small></td>
          <td class="perf-diagnosis">{diagnoses[key]}</td></tr>""")
        action_html.append(f"<div class='perf-action'><b>{labels[key]}</b><p>{actions[key]}</p></div>")
        bars = [("食材", c["food"], "#006d77"), ("能耗", c["energy"], "#b85c00"), ("工资", c["labor"], "#2f5b9f")]
        bar_html.append("<div class='perf-storebar'><b>" + labels[key] + "</b>" + "".join(
            f"<div class='perf-barrow'><span>{name}</span><i><em style='width:{min(value*180,100):.1f}%;background:{color}'></em></i><strong>{pct(value)}</strong></div>" for name,value,color in bars
        ) + "</div>")

    section = f"""
    <section class="section" id="performance">
      <div class="section-head"><div><div class="kicker">07 Performance &amp; Cost</div><h2>绩效与成本：增长能否转化为经营质量</h2></div>
      <p class="note">数据来源：2026年绩效.xlsx；绩效成本率=食材实际耗用率+能耗率，工资率单列，不等同完整利润率。</p></div>
      <div class="grid-4">
        <div class="metric"><span>三店营业收入</span><b>{money(cur_rev)}</b><small>环比 {rev_growth*100:+.1f}%</small></div>
        <div class="metric"><span>食材耗用率</span><b>{pct(food_cur)}</b><small>环比 {pp(food_cur-food_pre)}</small></div>
        <div class="metric"><span>能耗率</span><b>{pct(energy_cur)}</b><small>环比 {pp(energy_cur-energy_pre)}</small></div>
        <div class="metric"><span>工资率</span><b>{pct(labor_cur)}</b><small>环比 {pp(labor_cur-labor_pre)}</small></div>
      </div>
      <div class="grid-2 perf-grid">
        <div class="panel"><div class="panel-head"><h3>三店成本结构</h3><span class="label">7月占营业收入比例</span></div><div class="perf-bars">{''.join(bar_html)}</div></div>
        <div class="panel"><div class="panel-head"><h3>公司层判断</h3><span class="label">从现象到经营本质</span></div>
          <div class="callout"><b>现象：</b>收入环比增长{rev_growth*100:.1f}%，食材率改善{abs((food_cur-food_pre)*100):.2f}个百分点，但能耗率上升{(energy_cur-energy_pre)*100:.2f}个百分点。</div>
          <div class="callout perf-callout"><b>本质：</b>销售恢复快于成本效率改善，综合绩效成本率由{pct(cost_pre)}升至{pct(cost_cur)}。其中苏州街成本与工资双升、保利能耗上升，是8月现场改善重点。</div>
        </div>
      </div>
      <div class="table-wrap full-row"><table class="compact-table"><thead><tr><th>门店</th><th>收入</th><th>食材率</th><th>能耗率</th><th>工资率</th><th>绩效成本率</th><th>经营解读</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>
      <div class="panel full-row"><div class="panel-head"><h3>8月SMART行动计划</h3><span class="label">明确责任、截止时间与结果指标</span></div><div class="perf-actions">{''.join(action_html)}</div></div>
    </section>
    """

    css = """
    <style id="performanceStyle">
      .metric small,.compact-table small{display:block;margin-top:6px;color:var(--muted)}
      .perf-grid{margin-top:16px}.perf-bars{display:grid;gap:18px}.perf-storebar>b{display:block;margin-bottom:7px}
      .perf-barrow{display:grid;grid-template-columns:44px 1fr 54px;gap:8px;align-items:center;margin:6px 0;font-size:12px;color:var(--muted)}
      .perf-barrow i{height:10px;background:#eef2f3;border-radius:999px;overflow:hidden}.perf-barrow em{height:100%;display:block;border-radius:999px}.perf-barrow strong{text-align:right;color:var(--ink)}
      .perf-callout{margin-top:12px}.perf-diagnosis{min-width:260px;line-height:1.65}.perf-badge{display:inline-block;margin-top:5px;padding:2px 7px;border-radius:999px;font-size:11px}
      .perf-badge.good{background:#e5f5ef;color:#176b52}.perf-badge.risk{background:#fff0e2;color:#9a4d00}
      .perf-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.perf-action{padding:16px;border:1px solid var(--line);border-radius:12px;background:#fbfcfc}.perf-action p{margin:8px 0 0;line-height:1.65;color:var(--muted)}
      @media(max-width:900px){.perf-actions{grid-template-columns:1fr}}
    </style>
    """
    doc = REPORT.read_text(encoding="utf-8")
    if 'id="performance"' in doc:
        raise SystemExit("performance section already exists")
    doc = doc.replace("</head>", css + "\n</head>")
    doc = doc.replace('<a href="#daypart-drivers">时段归因</a>', '<a href="#performance">绩效成本</a>\n        <a href="#daypart-drivers">时段归因</a>')
    doc = doc.replace('    <section class="section" id="daypart-drivers">', section + '\n    <section class="section" id="daypart-drivers">')
    doc = doc.replace('<div class="kicker">07 Daypart Attribution</div>', '<div class="kicker">08 Daypart Attribution</div>')
    doc = doc.replace('<div class="kicker">08 Hourly Revenue</div>', '<div class="kicker">09 Hourly Revenue</div>')
    REPORT.write_text(doc, encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
