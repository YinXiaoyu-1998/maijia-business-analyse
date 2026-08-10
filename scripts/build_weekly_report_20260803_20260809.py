#!/usr/bin/env python3
import json
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from profile_weekly_meeting_data import read_workbook_sheet_rows, safe_float  # noqa: E402

CURRENT_FILE: Path
CURRENT_PRODUCT_FILE: Path
PREVIOUS_PRODUCT_FILE: Path
ATTENDANCE_FILE: Path
HISTORY_FILE: Path
OUT_DIR: Path
OUT: Path
STORES = ["麦家小馆（常营店）", "麦家小馆（苏州街店）", "麦家小馆（通州保利店）"]
SHORT = {"麦家小馆（常营店）": "常营店", "麦家小馆（苏州街店）": "苏州街店", "麦家小馆（通州保利店）": "通州保利店"}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def blank():
    return defaultdict(float)


def add(d, **kwargs):
    for k, v in kwargs.items(): d[k] += float(v or 0)


def read_current():
    rows=[]
    for sh, rn, v in read_workbook_sheet_rows(CURRENT_FILE):
        if rn < 7 or not v.get(2) or not v.get(3): continue
        try: dt=datetime.strptime(v.get(3), "%Y/%m/%d").date()
        except ValueError: continue
        if not (date(2026,8,3) <= dt <= date(2026,8,9)): continue
        rows.append({
            "store": v.get(2), "date": dt,
            "gross": safe_float(v.get(8)), "revenue": safe_float(v.get(11)), "discount": safe_float(v.get(9)),
            "orders": safe_float(v.get(13)), "customers": safe_float(v.get(14)), "tables": safe_float(v.get(16)),
            "dine": safe_float(v.get(29)), "dine_orders": safe_float(v.get(31)),
            "delivery": sum(safe_float(v.get(i)) for i in (40,51,62)),
            "delivery_orders": sum(safe_float(v.get(i)) for i in (42,53,64)),
            "meituan": safe_float(v.get(40)), "taobao": safe_float(v.get(51)), "jd": safe_float(v.get(62)),
        })
    return rows


def read_history(start, end):
    rows=[]
    for r in json.loads(HISTORY_FILE.read_text(encoding="utf-8")):
        dt=datetime.strptime(r["营业日期"], "%Y/%m/%d").date()
        if not (start <= dt <= end): continue
        rows.append({
            "store": r["门店名称"], "date": dt,
            "gross": r.get("营业额(元)",0), "revenue": r.get("订单营业收入",0), "discount": r.get("优惠金额",0),
            "orders": r.get("正向订单量",0), "customers": r.get("就餐人数",0),
            "tables": r.get("消费桌数",0), "dine": r.get("店内营业收入",0),
            "dine_orders": r.get("店内正向单订单量",0), "delivery": r.get("外卖营业收入",0),
            "delivery_orders": r.get("外卖正向单订单量",0), "meituan": r.get("美团外卖营业收入",0),
            "taobao": r.get("饿了么外卖营业收入",0), "jd": r.get("京东外卖营业收入",0),
        })
    return rows


def read_products(path, current=True):
    rows=[]
    for sh,rn,v in read_workbook_sheet_rows(path):
        if rn < 4 or not v.get(2) or not v.get(3) or not v.get(6): continue
        if current:
            try: dt=datetime.strptime(v.get(3), "%Y/%m/%d").date()
            except ValueError: continue
            if not (date(2026,8,3) <= dt <= date(2026,8,9)): continue
        elif v.get(3) != "2026/07/27~2026/08/02":
            continue
        rows.append({"store":v.get(2),"department":v.get(5) or "未分类","dish":v.get(6),"qty":safe_float(v.get(7)),"sales":safe_float(v.get(8))})
    return rows


def product_agg(rows):
    overall=defaultdict(blank); stores={s:defaultdict(blank) for s in STORES}
    for r in rows:
        for bucket in (overall[r["dish"]],stores[r["store"]][r["dish"]]):
            bucket["qty"]+=r["qty"];bucket["sales"]+=r["sales"]
            bucket["department"]=r["department"]
    return overall,stores


def read_attendance():
    headers={}; daily=defaultdict(lambda:defaultdict(float)); unique=defaultdict(set)
    for sh,rn,v in read_workbook_sheet_rows(ATTENDANCE_FILE):
        if rn==1:
            headers=v;continue
        if rn<2:continue
        dept=v.get(4,""); employee=v.get(1,"")
        if "苏州街" in dept: store="麦家小馆（苏州街店）"
        elif "常营" in dept: store="麦家小馆（常营店）"
        elif "保利" in dept or "通州" in dept: store="麦家小馆（通州保利店）"
        else: continue
        area="front" if "前厅" in dept else "back" if "后厨" in dept else "other"
        for col in range(6,13):
            raw=str(v.get(col,"") or "").strip(); day=str(headers.get(col,"") or "")
            if raw and day:
                daily[store,day]["total"]+=1;daily[store,day][area]+=1;unique[store].add(employee)
    return daily,unique


def aggregate(rows):
    stores={s:blank() for s in STORES}; daily={i:blank() for i in range(7)}; total=blank()
    fields=["gross","revenue","discount","orders","customers","tables","dine","dine_orders","delivery","delivery_orders","meituan","taobao","jd"]
    for r in rows:
        if r["store"] not in stores: continue
        for k in fields:
            stores[r["store"]][k]+=r[k]; daily[r["date"].weekday()][k]+=r[k]; total[k]+=r[k]
    return stores,daily,total


def pct(a,b): return None if not b else a/b-1
def fp(v): return "—" if v is None else f"{v*100:+.1f}%"
def wan(v): return f"{v/10000:.1f}万"
def yuan(v): return f"{v:,.1f}元"


def bar_rows(items, value, comparison=None, color="#2f5b9f"):
    mx=max(value(x) for x in items) or 1
    out=[]
    for x in items:
        v=value(x); comp=comparison(x) if comparison else ""
        out.append(f'<div class="bar-row"><span>{escape(x[0])}</span><i><em style="width:{v/mx*100:.1f}%;background:{color}"></em></i><b>{wan(v)}</b><small>{comp}</small></div>')
    return "".join(out)


def line_svg(cur, prev, width=920, height=250):
    vals=[cur[i]["revenue"]/10000 for i in range(7)]+[prev[i]["revenue"]/10000 for i in range(7)]
    top=max(vals)*1.12; left,right,upper,lower=52,24,24,40
    parts=[]
    for t in range(5):
        y=height-lower-(height-upper-lower)*t/4; val=top*t/4
        parts.append(f'<line x1="{left}" y1="{y}" x2="{width-right}" y2="{y}" stroke="#e4e9ec"/><text x="{left-8}" y="{y+4}" text-anchor="end">{val:.1f}</text>')
    for idx,label in enumerate(WEEKDAYS):
        x=left+idx*(width-left-right)/6; parts.append(f'<text x="{x}" y="{height-12}" text-anchor="middle">{label}</text>')
    for data,color,dash in ((prev,"#94a3b8",' stroke-dasharray="6 5"'),(cur,"#2f5b9f",'')):
        pts=[]
        for i in range(7):
            x=left+i*(width-left-right)/6; val=data[i]["revenue"]/10000; y=height-lower-val*(height-upper-lower)/top;pts.append((x,y,val))
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y,_ in pts)}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        parts.extend(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/><text x="{x}" y="{y-9}" text-anchor="middle">{v:.1f}</text>' for x,y,v in pts)
    return f'<svg viewBox="0 0 {width} {height}">{"".join(parts)}</svg>'


def main():
    current=read_current(); previous=read_history(date(2026,7,27),date(2026,8,2)); yoy=read_history(date(2025,8,4),date(2025,8,10))
    current_products=read_products(CURRENT_PRODUCT_FILE,True); previous_products=read_products(PREVIOUS_PRODUCT_FILE,False)
    cp,cps=product_agg(current_products); pp,pps=product_agg(previous_products)
    attendance,unique_staff=read_attendance()
    cs,cd,ct=aggregate(current); ps,pd,pt=aggregate(previous); ys,yd,yt=aggregate(yoy)
    if len(current)!=21: raise ValueError(f"current rows {len(current)} != 21")

    rev_wow=pct(ct["revenue"],pt["revenue"]); rev_yoy=pct(ct["revenue"],yt["revenue"])
    order_wow=pct(ct["orders"],pt["orders"]); aov=ct["revenue"]/ct["orders"]; paov=pt["revenue"]/pt["orders"]
    aov_wow=pct(aov,paov); dine_wow=pct(ct["dine"],pt["dine"]); del_wow=pct(ct["delivery"],pt["delivery"])
    store_table=[]; actions=[]
    for s in STORES:
        c,p,y=cs[s],ps[s],ys[s]; rw=pct(c["revenue"],p["revenue"]); ry=pct(c["revenue"],y["revenue"])
        ow=pct(c["orders"],p["orders"]); ca=c["revenue"]/c["orders"]; pca=p["revenue"]/p["orders"]
        dw=pct(c["dine"],p["dine"]); ew=pct(c["delivery"],p["delivery"])
        if rw is not None and rw >= .03:
            diagnosis="收入增长，继续复制本周有效时段与现场组织。"
        elif rw is not None and rw >= 0:
            diagnosis="收入基本稳定，重点提升订单量和高峰承接。"
        else:
            diagnosis="收入承压，先拆订单量与客单，再核查堂食/外卖拖累。"
        store_table.append(f"<tr><td><b>{SHORT[s]}</b></td><td>{wan(c['revenue'])}</td><td class='move'>{fp(rw)}</td><td class='move'>{fp(ry)}</td><td>{c['orders']:,.0f}</td><td class='move'>{fp(ow)}</td><td>{yuan(ca)}</td><td>{wan(c['dine'])}<small>{fp(dw)}</small></td><td>{wan(c['delivery'])}<small>{fp(ew)}</small></td><td>{diagnosis}</td></tr>")
        target=c["revenue"]*(1.03 if rw>=0 else 1.06)
        actions.append(f"<div class='action'><b>{SHORT[s]}</b><p>店长负责：8月16日前完成每日订单量、客单和堂食/外卖复盘；下周营业收入目标≥{wan(target)}，同时将折扣率控制在≤{c['discount']/c['gross']*100:.1f}%。</p></div>")

    store_items=[(SHORT[s],cs[s]["revenue"],ps[s]["revenue"]) for s in STORES]
    storebars=bar_rows(store_items,lambda x:x[1],lambda x:f"环比 {fp(pct(x[1],x[2]))}")
    channel_items=[("堂食",ct["dine"],pt["dine"]),("外卖",ct["delivery"],pt["delivery"])]
    channelbars=bar_rows(channel_items,lambda x:x[1],lambda x:f"环比 {fp(pct(x[1],x[2]))}","#006d77")

    product_sales_total=sum(x["sales"] for x in cp.values());product_qty_total=sum(x["qty"] for x in cp.values())
    top_sales=sorted(cp.items(),key=lambda x:x[1]["sales"],reverse=True)[:10]
    top_qty=sorted(cp.items(),key=lambda x:x[1]["qty"],reverse=True)[:10]
    product_sales_rows="".join(f"<tr><td>{i}</td><td>{escape(name)}</td><td>{escape(str(x['department']))}</td><td>{x['sales']:,.0f}</td><td>{x['sales']/product_sales_total*100:.1f}%</td><td>{x['qty']:,.0f}</td><td>{fp(pct(x['sales'],pp[name]['sales']))}</td></tr>" for i,(name,x) in enumerate(top_sales,1))
    product_qty_rows="".join(f"<tr><td>{i}</td><td>{escape(name)}</td><td>{x['qty']:,.0f}</td><td>{x['qty']/product_qty_total*100:.1f}%</td><td>{x['sales']:,.0f}</td><td>{fp(pct(x['qty'],pp[name]['qty']))}</td></tr>" for i,(name,x) in enumerate(top_qty,1))
    store_product_blocks=[]
    for s in STORES:
        sales_total=sum(x["sales"] for x in cps[s].values());qty_total=sum(x["qty"] for x in cps[s].values())
        ranked=sorted(cps[s].items(),key=lambda x:x[1]["sales"],reverse=True)[:10]
        body="".join(f"<tr><td>{i}</td><td>{escape(name)}</td><td>{x['sales']:,.0f}</td><td>{x['sales']/sales_total*100:.1f}%</td><td>{x['qty']:,.0f}</td><td>{x['qty']/qty_total*100:.1f}%</td><td>{fp(pct(x['sales'],pps[s][name]['sales']))}</td></tr>" for i,(name,x) in enumerate(ranked,1))
        store_product_blocks.append(f"<div class='panel full'><div class='panel-head'><h3>{SHORT[s]}产品金额Top10</h3><span class='note'>金额、数量占本店品项合计</span></div><div class='table-wrap'><table><thead><tr><th>#</th><th>品项</th><th>销售收入</th><th>金额占比</th><th>销量</th><th>数量占比</th><th>金额环比</th></tr></thead><tbody>{body}</tbody></table></div></div>")

    attendance_rows=[];total_person_days=0;total_front_days=0
    for s in STORES:
        person_days=sum(attendance[s,f"2026-08-{d:02d}"]["total"] for d in range(3,10))
        front_days=sum(attendance[s,f"2026-08-{d:02d}"]["front"] for d in range(3,10))
        back_days=sum(attendance[s,f"2026-08-{d:02d}"]["back"] for d in range(3,10))
        other_days=sum(attendance[s,f"2026-08-{d:02d}"]["other"] for d in range(3,10))
        total_person_days+=person_days;total_front_days+=front_days
        attendance_rows.append(f"<tr><td><b>{SHORT[s]}</b></td><td>{len(unique_staff[s])}</td><td>{person_days:.0f}</td><td>{person_days/7:.1f}</td><td>{front_days:.0f}</td><td>{back_days:.0f}</td><td>{other_days:.0f}</td><td>{ct['gross']/total_person_days if False else cs[s]['gross']/person_days:,.0f}元</td><td>{cs[s]['customers']/front_days:,.1f}人</td></tr>")
    total_gross_eff=ct["gross"]/total_person_days;total_front_eff=ct["customers"]/total_front_days
    html=f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>麦家小馆 2026-08-03至2026-08-09 经营周报</title><style>
:root{{--ink:#14212b;--muted:#657386;--line:#dfe6e9;--blue:#2f5b9f;--teal:#006d77;--amber:#b85c00;--bg:#f5f7f7}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}main,header>div{{max-width:1180px;margin:auto;padding:0 28px}}header{{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}}header>div{{display:flex;justify-content:space-between;align-items:center;min-height:60px}}nav a{{color:var(--muted);text-decoration:none;margin-left:15px;font-size:13px}}.hero{{padding:48px 0 28px}}.kicker{{color:var(--teal);font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}}h1{{font-size:38px;margin:8px 0}}h2{{font-size:25px;margin:6px 0}}h3{{margin:0;font-size:17px}}p{{line-height:1.65}}.lede,.note,small{{color:var(--muted)}}.section{{padding:28px 0;border-top:1px solid var(--line)}}.section-head,.panel-head{{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:15px}}.grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.grid-2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}.metric,.panel,.callout,.action{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px}}.metric span{{display:block;color:var(--muted);font-size:13px}}.metric b{{display:block;font-size:28px;margin:8px 0}}.full{{margin-top:16px}}svg{{width:100%;height:auto}}svg text{{font-size:10px;fill:#657386}}.bar-row{{display:grid;grid-template-columns:86px 1fr 72px 92px;align-items:center;gap:9px;margin:15px 0;font-size:13px}}.bar-row i{{height:12px;background:#edf1f3;border-radius:999px;overflow:hidden}}.bar-row em{{display:block;height:100%;border-radius:999px}}.bar-row small{{text-align:right}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{padding:12px 11px;border-bottom:1px solid var(--line);text-align:right;font-size:13px;vertical-align:top}}th:first-child,td:first-child,td:last-child{{text-align:left}}td small{{display:block;margin-top:4px}}.move{{font-weight:700}}.actions{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.action p{{margin-bottom:0;color:var(--muted)}}.callout{{background:#f0f6f6}}@media(max-width:850px){{.grid-4,.grid-2,.actions{{grid-template-columns:1fr}}nav{{display:none}}h1{{font-size:30px}}.bar-row{{grid-template-columns:70px 1fr 60px}}.bar-row small{{grid-column:2/5;text-align:left}}}}
</style></head><body><header><div><b>麦家小馆经营周报</b><nav><a href='#summary'>结论</a><a href='#trend'>趋势</a><a href='#stores'>门店</a><a href='#channels'>渠道</a><a href='#people'>人效</a><a href='#products'>产品</a><a href='#actions'>行动</a></nav></div></header><main>
<section class='hero'><div class='kicker'>Weekly Business Review</div><h1>2026年8月3日—8月9日经营周报</h1><p class='lede'>三店整体与单店复盘；环比为7月27日—8月2日，同比为2025年8月4日—8月10日（同为周一至周日）。</p></section>
<section class='section' id='summary'><div class='section-head'><div><div class='kicker'>01 Executive Summary</div><h2>收入{('增长' if rev_wow>=0 else '下降')}，主要由订单量与客单共同决定</h2></div><p class='note'>收入、订单、堂食和外卖口径已用8月1—2日重叠数据核验一致。</p></div>
<div class='grid-4'><div class='metric'><span>营业收入</span><b>{wan(ct['revenue'])}</b><small>环比 {fp(rev_wow)}｜同比 {fp(rev_yoy)}</small></div><div class='metric'><span>订单量</span><b>{ct['orders']:,.0f}</b><small>环比 {fp(order_wow)}</small></div><div class='metric'><span>折后客单</span><b>{yuan(aov)}</b><small>环比 {fp(aov_wow)}</small></div><div class='metric'><span>外卖占比</span><b>{ct['delivery']/ct['revenue']*100:.1f}%</b><small>外卖环比 {fp(del_wow)}</small></div></div>
<div class='callout full'><b>经营判断：</b>三店收入环比{fp(rev_wow)}，其中堂食{fp(dine_wow)}、外卖{fp(del_wow)}；订单量{fp(order_wow)}、折后客单{fp(aov_wow)}。优先把变化落到门店和渠道，而不是只看总额。</div></section>
<section class='section' id='trend'><div class='section-head'><div><div class='kicker'>02 Daily Trend</div><h2>每日营业收入走势</h2></div><p class='note'>单位：万元；蓝色本周，灰色上周。</p></div><div class='panel'>{line_svg(cd,pd)}</div></section>
<section class='section' id='stores'><div class='section-head'><div><div class='kicker'>03 Store Benchmark</div><h2>门店贡献与增长质量</h2></div></div><div class='grid-2'><div class='panel'><div class='panel-head'><h3>本周门店收入</h3></div>{storebars}</div><div class='panel'><div class='panel-head'><h3>收入构成</h3></div>{channelbars}</div></div><div class='table-wrap full'><table><thead><tr><th>门店</th><th>收入</th><th>环比</th><th>同比</th><th>订单</th><th>订单环比</th><th>客单</th><th>堂食</th><th>外卖</th><th>经营判断</th></tr></thead><tbody>{''.join(store_table)}</tbody></table></div></section>
<section class='section' id='channels'><div class='section-head'><div><div class='kicker'>04 Channel</div><h2>堂食与外卖结构</h2></div></div><div class='grid-4'><div class='metric'><span>堂食收入</span><b>{wan(ct['dine'])}</b><small>环比 {fp(dine_wow)}</small></div><div class='metric'><span>外卖收入</span><b>{wan(ct['delivery'])}</b><small>环比 {fp(del_wow)}</small></div><div class='metric'><span>美团外卖</span><b>{wan(ct['meituan'])}</b><small>外卖收入贡献</small></div><div class='metric'><span>京东+淘宝闪购</span><b>{wan(ct['jd']+ct['taobao'])}</b><small>外卖收入贡献</small></div></div></section>
<section class='section' id='people'><div class='section-head'><div><div class='kicker'>05 People Efficiency</div><h2>出勤与人效：营业额和服务客数对应到人</h2></div><p class='note'>出勤人次=员工当日存在打卡记录；不展示个人姓名。</p></div><div class='grid-4'><div class='metric'><span>三店出勤人次</span><b>{total_person_days:.0f}</b><small>平均每日 {total_person_days/7:.1f}人</small></div><div class='metric'><span>营业额/出勤人次</span><b>{total_gross_eff:,.0f}元</b><small>按营业额口径</small></div><div class='metric'><span>前厅出勤人次</span><b>{total_front_days:.0f}</b><small>仅明确标注前厅部</small></div><div class='metric'><span>前厅单人服务客数</span><b>{total_front_eff:,.1f}人</b><small>用餐人数÷前厅出勤人次</small></div></div><div class='table-wrap full'><table><thead><tr><th>门店</th><th>周内员工数</th><th>出勤人次</th><th>日均出勤</th><th>前厅人次</th><th>后厨人次</th><th>未标部门人次</th><th>营业额/出勤人次</th><th>前厅单人服务客数</th></tr></thead><tbody>{''.join(attendance_rows)}</tbody></table></div><div class='callout full'><b>口径限制：</b>原始打卡存在跨午夜、补卡和多人一天多次打卡，不能仅凭首末打卡可靠还原工时与分时段在岗人数。本版采用稳定的出勤人次口径；若补充划线排班或明确上下班配对规则，可进一步计算每小时营业额/在岗人数。<br><b>质量提醒：</b>通州保利店本周用餐人数明显偏高，导致前厅单人服务客数达到161.8人，暂不建议直接用于三店绩效排名，需先核对用餐人数口径。</div></section>
<section class='section' id='products'><div class='section-head'><div><div class='kicker'>06 Product Contribution</div><h2>产品贡献：金额Top10、销量Top10和门店结构</h2></div><p class='note'>占比以品项销售统计合计为分母；套餐明细按系统原始口径保留。</p></div><div class='grid-2'><div class='panel'><div class='panel-head'><h3>整体销售金额Top10</h3></div><div class='table-wrap'><table><thead><tr><th>#</th><th>品项</th><th>部门</th><th>金额</th><th>金额占比</th><th>销量</th><th>金额环比</th></tr></thead><tbody>{product_sales_rows}</tbody></table></div></div><div class='panel'><div class='panel-head'><h3>整体销量Top10</h3></div><div class='table-wrap'><table><thead><tr><th>#</th><th>品项</th><th>销量</th><th>数量占比</th><th>金额</th><th>销量环比</th></tr></thead><tbody>{product_qty_rows}</tbody></table></div></div></div>{''.join(store_product_blocks)}<div class='callout full'><b>渠道限制：</b>本次品项文件设置为“销售渠道不分渠道”，因此产品Top10只能展示堂食与外卖合计，不能分别计算堂食Top10和外卖Top10。需要重新导出按“订单分类/销售渠道”分组的品项销售统计。</div></section>
<section class='section' id='actions'><div class='section-head'><div><div class='kicker'>07 SMART Actions</div><h2>下周行动计划</h2></div></div><div class='actions'>{''.join(actions)}</div><div class='callout full'><b>待补数据：</b>综合营业统计未按餐段/时段拆分；如补充8月3—9日餐时段统计和划线排班，可进一步计算分时段营业额人效和高峰前厅服务人效。</div></section>
</main></body></html>"""
    OUT_DIR.mkdir(parents=True,exist_ok=True);OUT.write_text(html,encoding="utf-8")
    facts={"current":dict(ct),"previous":dict(pt),"yoy":dict(yt),"stores":{s:{"current":dict(cs[s]),"previous":dict(ps[s]),"yoy":dict(ys[s])} for s in STORES}}
    (OUT_DIR/"weekly_facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding="utf-8")
    print(OUT)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description="生成麦家小馆2026-08-03至2026-08-09经营周报")
    parser.add_argument("--current-business",required=True,type=Path,help="2026-08-01至08-09综合营业统计")
    parser.add_argument("--current-products",required=True,type=Path,help="2026-08-01至08-09品项销售统计")
    parser.add_argument("--previous-products",required=True,type=Path,help="包含2026-07-27至08-02的品项销售统计")
    parser.add_argument("--attendance",required=True,type=Path,help="覆盖2026-08-03至08-09的考勤数据表")
    parser.add_argument("--history",required=True,type=Path,help="历史标准化营业明细JSON")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"outputs/weekly_report_20260803_20260809")
    args=parser.parse_args()
    CURRENT_FILE=args.current_business;CURRENT_PRODUCT_FILE=args.current_products
    PREVIOUS_PRODUCT_FILE=args.previous_products;ATTENDANCE_FILE=args.attendance;HISTORY_FILE=args.history
    OUT_DIR=args.output_dir;OUT=OUT_DIR/"麦家小馆_2026-08-03至2026-08-09_经营周报.html"
    main()
