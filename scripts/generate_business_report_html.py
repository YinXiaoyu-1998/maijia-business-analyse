#!/usr/bin/env python3
"""Generate a self-contained HTML business diagnosis report."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key, value in list(row.items()):
            if value is None:
                continue
            text = value.strip()
            if text == "":
                row[key] = None
                continue
            try:
                row[key] = float(text)
            except ValueError:
                row[key] = text
    return rows


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = (len(values) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def money_wan(value: float | None) -> float:
    return round((value or 0) / 10000, 1)


def pct(value: float | None) -> float:
    return round((value or 0) * 100, 1)


def store_short(name: str) -> str:
    return name.replace("麦家小馆（", "").replace("）", "")


def infer_period(summary: dict[str, Any]) -> str:
    dates = summary.get("dimension_samples", {}).get("营业日期", [])
    if dates:
        return f"{min(dates)}-{max(dates)}"
    filters = str(summary.get("filters") or "")
    if "营业日期" in filters:
        return filters
    return "未识别"


def classify_stores(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    revenues = [float(row["net_revenue"] or 0) for row in stores]
    aovs = [float(row["post_discount_aov"] or 0) for row in stores]
    discounts = [float(row["discount_rate"] or 0) for row in stores]
    p75_revenue = percentile(revenues, 0.75)
    med_revenue = statistics.median(revenues)
    med_aov = statistics.median(aovs)
    med_discount = statistics.median(discounts)

    result = []
    for row in stores:
        revenue = float(row["net_revenue"] or 0)
        aov = float(row["post_discount_aov"] or 0)
        discount = float(row["discount_rate"] or 0)
        if revenue >= p75_revenue and aov >= med_aov:
            segment = "明星店"
            action = "复制高客单与高收入打法"
        elif revenue >= med_revenue:
            segment = "稳定现金流"
            action = "守住收入，压实折扣纪律"
        elif discount > med_discount or aov < med_aov:
            segment = "结构机会店"
            action = "优先治理客单、折扣或渠道结构"
        else:
            segment = "低效待改善"
            action = "用门店辅导拉齐基础盘"
        item = dict(row)
        item["short_name"] = store_short(str(row["门店名称"]))
        item["segment"] = segment
        item["action"] = action
        result.append(item)
    return result


def build_opportunities(stores: list[dict[str, Any]], channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store_discount_median = statistics.median([float(row["discount_rate"] or 0) for row in stores])
    store_aov_median = statistics.median([float(row["post_discount_aov"] or 0) for row in stores])
    member_share_median = statistics.median([float(row["member_revenue_share"] or 0) for row in stores])

    discount_upside = sum(
        max(0, float(row["discount_rate"] or 0) - store_discount_median) * float(row["gross_sales"] or 0)
        for row in stores
    )
    aov_upside = sum(
        max(0, store_aov_median - float(row["post_discount_aov"] or 0)) * float(row["positive_orders"] or 0)
        for row in stores
    )
    member_pool = sum(
        max(0, member_share_median - float(row["member_revenue_share"] or 0)) * float(row["net_revenue"] or 0)
        for row in stores
    )
    delivery_channels = [
        row for row in channels
        if str(row.get("订单分类", "")).find("外卖") >= 0
        or str(row.get("订单来源", "")).find("闪购") >= 0
        or str(row.get("订单来源", "")).find("秒送") >= 0
    ]
    delivery_discount_floor = 0.18
    delivery_discount_upside = sum(
        max(0, float(row["discount_rate"] or 0) - delivery_discount_floor) * float(row["gross_sales"] or 0)
        for row in delivery_channels
    )

    return [
        {
            "name": "折扣纪律",
            "value": money_wan(discount_upside),
            "unit": "万元",
            "confidence": "高",
            "effort": "中",
            "logic": "高折扣门店回到门店中位折扣率",
            "owner": "运营 + 门店督导",
        },
        {
            "name": "低客单修复",
            "value": money_wan(aov_upside),
            "unit": "万元",
            "confidence": "中",
            "effort": "中",
            "logic": "低客单门店追平门店中位折后单均",
            "owner": "菜单 + 门店",
        },
        {
            "name": "外卖折扣治理",
            "value": money_wan(delivery_discount_upside),
            "unit": "万元",
            "confidence": "中",
            "effort": "高",
            "logic": "高折扣外卖渠道回落到 18% 折扣率",
            "owner": "外卖运营",
        },
        {
            "name": "会员渗透补齐",
            "value": money_wan(member_pool),
            "unit": "万元会员收入池",
            "confidence": "中",
            "effort": "中",
            "logic": "低会员占比门店追平门店中位会员收入占比",
            "owner": "会员运营",
        },
    ]


def prepare_payload(input_dir: Path, company: str, source_name: str) -> dict[str, Any]:
    summary = json.loads((input_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    stores = classify_stores(read_csv(input_dir / "store_summary.csv"))
    channels = read_csv(input_dir / "channel_summary.csv")
    monthly = read_csv(input_dir / "monthly_trend.csv")
    dayparts = read_csv(input_dir / "daypart_summary.csv")
    members = read_csv(input_dir / "member_summary.csv")
    store_dayparts = read_csv(input_dir / "store_daypart_summary.csv")

    monthly = sorted(monthly, key=lambda row: str(row["月"]))
    store_segments: dict[str, int] = {}
    for row in stores:
        store_segments[row["segment"]] = store_segments.get(row["segment"], 0) + 1

    top_month = max(monthly, key=lambda row: float(row["net_revenue"] or 0))
    top_store = max(stores, key=lambda row: float(row["net_revenue"] or 0))
    highest_discount_store = max(stores, key=lambda row: float(row["discount_rate"] or 0))
    top_channel = max(channels, key=lambda row: float(row["net_revenue"] or 0))
    top_daypart = max(dayparts, key=lambda row: float(row["net_revenue"] or 0))
    overall = summary["overall_kpis"]
    period = infer_period(summary)
    city_names = summary.get("dimension_samples", {}).get("城市", [])
    city_label = "、".join(city_names[:3]) if city_names else "未识别"

    payload = {
        "meta": {
            "title": f"{company}经营诊断报告",
            "company": company,
            "period": period,
            "generated": date.today().isoformat(),
            "source": source_name,
            "data_rows": summary.get("data_rows_streamed", 0),
            "store_count": overall.get("store_count", 0),
            "city_label": city_label,
            "skipped_summary_rows": summary.get("skipped_summary_rows", 0),
        },
        "overall": overall,
        "insights": [
            {
                "label": "核心判断 1",
                "title": "收入基本盘由店内驱动，外卖是结构性补充",
                "metric": f"{pct(overall['dine_in_revenue_share'])}%",
                "note": f"店内订单收入占比；外卖占比约 {pct(overall['delivery_revenue_share'])}%。",
            },
            {
                "label": "核心判断 2",
                "title": "折扣已经成为第一优先级的收入质量议题",
                "metric": f"{pct(overall['discount_rate'])}%",
                "note": f"优惠金额 {money_wan(float(overall['discount_amount'] or 0))} 万，需分渠道治理。",
            },
            {
                "label": "核心判断 3",
                "title": "门店差异明显，第一梯队具备复制价值",
                "metric": store_short(str(top_store["门店名称"])),
                "note": f"Top 门店订单收入 {money_wan(float(top_store['net_revenue']))} 万。",
            },
            {
                "label": "核心判断 4",
                "title": "晚餐高峰贡献最大，午餐 11 点折扣压力偏高",
                "metric": str(top_daypart["时段"]),
                "note": f"{top_daypart['餐段']} {top_daypart['时段']} 为最高收入时段。",
            },
        ],
        "stores": stores,
        "channels": channels,
        "monthly": monthly,
        "dayparts": dayparts,
        "members": members,
        "store_dayparts": store_dayparts,
        "store_segments": store_segments,
        "opportunities": build_opportunities(stores, channels),
        "benchmarks": {
            "median_store_revenue": money_wan(statistics.median([float(row["net_revenue"] or 0) for row in stores])),
            "median_store_aov": round(statistics.median([float(row["post_discount_aov"] or 0) for row in stores]), 1),
            "median_store_discount": pct(statistics.median([float(row["discount_rate"] or 0) for row in stores])),
            "top_month": str(top_month["月"]),
            "top_channel": f"{top_channel['订单分类']} / {top_channel['订单来源']}",
            "highest_discount_store": store_short(str(highest_discount_store["门店名称"])),
        },
    }
    return payload


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>__REPORT_TITLE__</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --surface: #ffffff;
      --surface-2: #eef3f4;
      --ink: #18212f;
      --muted: #627083;
      --line: #d9e1e7;
      --teal: #006d77;
      --teal-2: #83c5be;
      --blue: #355c9f;
      --amber: #b85c00;
      --orange: #d96b3b;
      --green: #3a7d44;
      --red: #b23a48;
      --violet: #7757a6;
      --shadow: 0 18px 45px rgba(24, 33, 47, 0.08);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font: 14px/1.55 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    a { color: inherit; text-decoration: none; }
    button, select { font: inherit; }
    .shell { min-height: 100vh; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(246, 248, 251, 0.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(14px);
    }
    .topbar-inner {
      max-width: 1360px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 250px;
      font-weight: 760;
    }
    .brand-mark {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: conic-gradient(from 140deg, var(--teal), var(--blue), var(--amber), var(--teal));
      box-shadow: 0 8px 20px rgba(0, 109, 119, 0.18);
    }
    .nav {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 4px;
    }
    .nav a, .pill-button {
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--muted);
      background: transparent;
      cursor: pointer;
    }
    .nav a:hover, .pill-button:hover, .pill-button.active {
      color: var(--ink);
      border-color: var(--line);
      background: var(--surface);
    }
    main { max-width: 1360px; margin: 0 auto; padding: 28px 24px 64px; }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 28px;
      align-items: stretch;
      padding: 28px 0 18px;
    }
    .hero h1 {
      margin: 0 0 12px;
      font-size: 40px;
      line-height: 1.12;
      font-weight: 800;
    }
    .hero-sub {
      max-width: 780px;
      margin: 0;
      color: var(--muted);
      font-size: 16px;
    }
    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 22px;
    }
    .meta-chip {
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface);
      color: var(--muted);
    }
    .score-panel {
      background: var(--ink);
      color: #fff;
      border-radius: var(--radius);
      padding: 22px;
      box-shadow: var(--shadow);
      display: grid;
      gap: 18px;
    }
    .score-label { color: rgba(255,255,255,0.7); font-size: 13px; }
    .score-value { font-size: 34px; font-weight: 820; line-height: 1; margin-top: 6px; }
    .score-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    .score-mini {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 8px;
      padding: 12px;
    }
    .score-mini b { display: block; margin-top: 3px; font-size: 18px; }
    .section {
      padding: 34px 0;
      border-top: 1px solid var(--line);
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: end;
      margin-bottom: 18px;
    }
    .section-kicker {
      color: var(--teal);
      font-size: 13px;
      font-weight: 760;
      text-transform: uppercase;
    }
    .section h2 {
      margin: 3px 0 0;
      font-size: 26px;
      line-height: 1.22;
    }
    .section-note { margin: 0; color: var(--muted); max-width: 600px; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .tile, .panel, .insight {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 28px rgba(24, 33, 47, 0.045);
    }
    .tile { padding: 16px; min-height: 136px; }
    .tile-label { color: var(--muted); font-size: 12px; font-weight: 700; }
    .tile-value { margin-top: 8px; font-size: 28px; font-weight: 820; line-height: 1; }
    .tile-foot { margin-top: 12px; color: var(--muted); font-size: 13px; }
    .insight { padding: 16px; display: grid; gap: 10px; }
    .insight-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .insight-label { color: var(--muted); font-size: 12px; font-weight: 720; }
    .insight-metric { font-size: 24px; font-weight: 820; color: var(--teal); }
    .insight-title { font-size: 16px; font-weight: 760; line-height: 1.35; }
    .insight-note { color: var(--muted); font-size: 13px; }
    .panel { padding: 18px; min-width: 0; }
    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 10px;
    }
    .panel-title { font-size: 16px; font-weight: 780; }
    .panel-caption { margin-top: 2px; color: var(--muted); font-size: 12px; }
    .control-row { display: flex; gap: 6px; flex-wrap: wrap; }
    .chart { width: 100%; min-height: 300px; position: relative; overflow: hidden; }
    .chart svg { width: 100%; height: 100%; min-height: 300px; display: block; overflow: hidden; }
    .legend { display: flex; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-top: 10px; }
    .legend-item { display: inline-flex; align-items: center; gap: 6px; }
    .swatch { width: 10px; height: 10px; border-radius: 2px; }
    .tooltip {
      position: fixed;
      z-index: 50;
      pointer-events: none;
      background: #111827;
      color: #fff;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      box-shadow: var(--shadow);
      opacity: 0;
      transform: translate(-50%, -120%);
      transition: opacity .12s ease;
      max-width: 260px;
    }
    .segment-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .segment {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: var(--surface-2);
    }
    .segment b { display: block; font-size: 22px; margin: 6px 0; }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
    }
    table { width: 100%; border-collapse: collapse; min-width: 780px; }
    th, td { padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
    th { position: sticky; top: 0; background: #f1f5f8; color: var(--muted); font-size: 12px; cursor: pointer; }
    td { font-size: 13px; }
    tr:last-child td { border-bottom: 0; }
    .tag {
      display: inline-flex;
      align-items: center;
      padding: 4px 8px;
      border-radius: 999px;
      background: #edf3f0;
      color: var(--teal);
      font-size: 12px;
      font-weight: 720;
    }
    .matrix {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .opportunity {
      padding: 16px;
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: var(--radius);
    }
    .opportunity .value { font-size: 26px; font-weight: 820; margin: 10px 0 4px; }
    .opportunity .logic { color: var(--muted); min-height: 40px; }
    .owner { margin-top: 12px; font-size: 12px; color: var(--muted); }
    .callout {
      border-left: 4px solid var(--amber);
      background: #fff8ef;
      padding: 14px 16px;
      border-radius: 0 8px 8px 0;
      color: #61420f;
    }
    .footer {
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 18px;
      display: flex;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
    }
    @media (max-width: 980px) {
      .hero, .grid-2, .grid-3 { grid-template-columns: 1fr; }
      .grid-4, .segment-grid, .matrix { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .topbar-inner { align-items: flex-start; flex-direction: column; }
      .nav { justify-content: flex-start; }
    }
    @media (max-width: 620px) {
      main { padding: 18px 14px 48px; }
      .hero h1 { font-size: 30px; }
      .grid-4, .segment-grid, .matrix, .score-row { grid-template-columns: 1fr; }
      .section-head { align-items: start; flex-direction: column; }
      .brand { min-width: 0; }
    }
  </style>
</head>
<body>
  <div class="tooltip" id="tooltip"></div>
  <div class="shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="#top" aria-label="返回顶部">
          <span class="brand-mark" aria-hidden="true"></span>
          <span>__NAV_TITLE__</span>
        </a>
        <nav class="nav" aria-label="报告导航">
          <a href="#summary">结论</a>
          <a href="#baseline">基线</a>
          <a href="#stores">门店</a>
          <a href="#channels">渠道</a>
          <a href="#dayparts">餐段</a>
          <a href="#opportunities">机会</a>
        </nav>
      </div>
    </header>

    <main id="top">
      <section class="hero" aria-labelledby="report-title">
        <div>
          <div class="section-kicker">Management Diagnosis</div>
          <h1 id="report-title">__REPORT_TITLE__</h1>
          <p class="hero-sub">基于营业分组数据形成第一版经营事实底稿，聚焦收入质量、门店组合、渠道结构、餐段机会与可执行经营杠杆。</p>
          <div class="hero-meta">
            <span class="meta-chip">周期：__PERIOD__</span>
            <span class="meta-chip">样本：__DATA_ROWS__ 行</span>
            <span class="meta-chip">门店：__STORE_COUNT__ 家</span>
            <span class="meta-chip">城市：__CITY_LABEL__</span>
          </div>
        </div>
        <aside class="score-panel" aria-label="核心经营规模">
          <div>
            <div class="score-label">订单营业收入</div>
            <div class="score-value" data-format="wan" data-value="__NET_REVENUE__">0</div>
          </div>
          <div class="score-row">
            <div class="score-mini"><span class="score-label">营业额</span><b data-format="wan" data-value="__GROSS_SALES__"></b></div>
            <div class="score-mini"><span class="score-label">折扣率</span><b data-format="pct" data-value="__DISCOUNT_RATE__"></b></div>
            <div class="score-mini"><span class="score-label">折后单均</span><b data-format="yuan" data-value="__POST_DISCOUNT_AOV__"></b></div>
          </div>
        </aside>
      </section>

      <section class="section" id="summary">
        <div class="section-head">
          <div>
            <div class="section-kicker">01 Executive Summary</div>
            <h2>四个判断先看完，再决定追哪条线</h2>
          </div>
          <p class="section-note">每条结论都来自聚合事实表；下一轮可用访谈和成本数据验证根因。</p>
        </div>
        <div class="grid-4" id="insightGrid"></div>
      </section>

      <section class="section" id="baseline">
        <div class="section-head">
          <div>
            <div class="section-kicker">02 Baseline</div>
            <h2>收入基线：店内主导，折扣池需要专项治理</h2>
          </div>
          <div class="control-row" role="group" aria-label="趋势指标">
            <button class="pill-button active" data-month-metric="net_revenue">收入</button>
            <button class="pill-button" data-month-metric="positive_orders">订单</button>
            <button class="pill-button" data-month-metric="discount_rate">折扣率</button>
          </div>
        </div>
        <div class="grid-4">
          <div class="tile"><div class="tile-label">营业额</div><div class="tile-value" data-format="wan" data-value="__GROSS_SALES__"></div><div class="tile-foot">折前口径</div></div>
          <div class="tile"><div class="tile-label">订单营业收入</div><div class="tile-value" data-format="wan" data-value="__NET_REVENUE__"></div><div class="tile-foot">用于经营主线</div></div>
          <div class="tile"><div class="tile-label">优惠金额</div><div class="tile-value" data-format="wan" data-value="__DISCOUNT_AMOUNT__"></div><div class="tile-foot">期间折扣池</div></div>
          <div class="tile"><div class="tile-label">正向订单</div><div class="tile-value" data-format="count" data-value="__POSITIVE_ORDERS__"></div><div class="tile-foot">已结账订单一致</div></div>
        </div>
        <div class="grid-2" style="margin-top:16px;">
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">月度经营趋势</div><div class="panel-caption">支持切换收入、订单、折扣率</div></div>
            </div>
            <div class="chart" id="monthlyChart"></div>
          </div>
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">收入结构</div><div class="panel-caption">店内、外卖、自提按订单营业收入拆分</div></div>
            </div>
            <div class="chart" id="mixChart"></div>
            <div class="legend" id="mixLegend"></div>
          </div>
        </div>
      </section>

      <section class="section" id="stores">
        <div class="section-head">
          <div>
            <div class="section-kicker">03 Store Portfolio</div>
            <h2>门店组合：第一梯队可复制，后排门店先修客单与效率</h2>
          </div>
          <p class="section-note">门店分型基于收入、折后单均、折扣率和收入结构，适合作为经营会的讨论起点。</p>
        </div>
        <div class="grid-2">
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">门店收入排名</div><div class="panel-caption">点击切换收入、折扣率、客单</div></div>
              <div class="control-row">
                <button class="pill-button active" data-store-metric="net_revenue">收入</button>
                <button class="pill-button" data-store-metric="discount_rate">折扣</button>
                <button class="pill-button" data-store-metric="post_discount_aov">客单</button>
              </div>
            </div>
            <div class="chart" id="storeBarChart"></div>
          </div>
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">收入 vs 折后单均</div><div class="panel-caption">气泡越大，折扣率越高</div></div>
            </div>
            <div class="chart" id="storeScatter"></div>
          </div>
        </div>
        <div class="segment-grid" id="segmentGrid" style="margin-top:16px;"></div>
        <div class="table-wrap" style="margin-top:16px;">
          <table id="storeTable">
            <thead>
              <tr>
                <th data-sort="short_name">门店</th>
                <th data-sort="segment">分型</th>
                <th data-sort="net_revenue">收入</th>
                <th data-sort="discount_rate">折扣率</th>
                <th data-sort="post_discount_aov">折后单均</th>
                <th data-sort="delivery_revenue_share">外卖占比</th>
                <th data-sort="member_revenue_share">会员占比</th>
                <th>动作</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <section class="section" id="channels">
        <div class="section-head">
          <div>
            <div class="section-kicker">04 Channel Quality</div>
            <h2>渠道结构：对比收入贡献、客单与折扣强度</h2>
          </div>
          <p class="section-note">渠道诊断优先看三件事：收入贡献、折后单均、折扣率。</p>
        </div>
        <div class="grid-2">
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">渠道收入与折扣率</div><div class="panel-caption">条形为收入，圆点为折扣率</div></div>
            </div>
            <div class="chart" id="channelChart"></div>
          </div>
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">会员与非会员</div><div class="panel-caption">会员客单更高，但收入占比只有约五分之一</div></div>
            </div>
            <div class="chart" id="memberChart"></div>
          </div>
        </div>
      </section>

      <section class="section" id="dayparts">
        <div class="section-head">
          <div>
            <div class="section-kicker">05 Daypart Opportunity</div>
            <h2>餐段机会：用时段热力图定位高峰与折扣压力</h2>
          </div>
          <p class="section-note">热力图按餐段和时段展示订单营业收入，深色表示收入高。</p>
        </div>
        <div class="grid-2">
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">餐段 × 时段收入热力图</div><div class="panel-caption">悬停查看收入、订单、折扣率</div></div>
            </div>
            <div class="chart" id="heatmapChart"></div>
          </div>
          <div class="panel">
            <div class="panel-head">
              <div><div class="panel-title">Top 时段</div><div class="panel-caption">按订单营业收入排序</div></div>
            </div>
            <div class="chart" id="daypartBar"></div>
          </div>
        </div>
      </section>

      <section class="section" id="opportunities">
        <div class="section-head">
          <div>
            <div class="section-kicker">06 Opportunity Pool</div>
            <h2>机会池：先用数据找抓手，再用业务访谈验证根因</h2>
          </div>
          <p class="section-note">这里是机械测算，不是承诺收益。适合用来决定下一轮经营专题。</p>
        </div>
        <div class="matrix" id="opportunityGrid"></div>
        <div class="callout" style="margin-top:18px;">
          建议下一轮补充：菜品毛利、平台佣金、门店面积/座位、排班人效、顾客评价。补齐后才能从「营业诊断」升级到「利润诊断」。
        </div>
      </section>

      <footer class="footer">
        <span>数据源：__SOURCE_NAME__；生成：__GENERATED_DATE__</span>
        <span>口径：跳过 __SKIPPED_SUMMARY_ROWS__ 条导出汇总行，聚合表已完成收入交叉校验。</span>
      </footer>
    </main>
  </div>

  <script id="report-data" type="application/json">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById('report-data').textContent);
    const COLORS = ['#006d77', '#355c9f', '#d96b3b', '#3a7d44', '#b85c00', '#7757a6', '#83c5be', '#b23a48'];
    const tooltip = document.getElementById('tooltip');

    const fmt = {
      wan: v => `${(Number(v || 0) / 10000).toLocaleString('zh-CN', {maximumFractionDigits: 1})}万`,
      yuan: v => `${Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1})}元`,
      pct: v => `${(Number(v || 0) * 100).toFixed(1)}%`,
      count: v => Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 0}),
      plainWan: v => `${Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1})}万`
    };

    function showTip(event, html) {
      tooltip.innerHTML = html;
      tooltip.style.left = `${event.clientX}px`;
      tooltip.style.top = `${event.clientY}px`;
      tooltip.style.opacity = 1;
    }
    function hideTip() { tooltip.style.opacity = 0; }
    function svgEl(name, attrs = {}) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
      return el;
    }
    function clear(id) {
      const node = document.getElementById(id);
      node.innerHTML = '';
      return node;
    }
    function scale(value, min, max, outMin, outMax) {
      if (max === min) return (outMin + outMax) / 2;
      return outMin + (value - min) * (outMax - outMin) / (max - min);
    }
    function metricValue(row, metric) {
      return Number(row[metric] || 0);
    }

    function fillNumbers() {
      document.querySelectorAll('[data-format]').forEach(el => {
        const value = Number(el.dataset.value || 0);
        el.textContent = fmt[el.dataset.format](value);
      });
    }

    function renderInsights() {
      const grid = document.getElementById('insightGrid');
      grid.innerHTML = data.insights.map(item => `
        <article class="insight">
          <div class="insight-top">
            <span class="insight-label">${item.label}</span>
            <span class="insight-metric">${item.metric}</span>
          </div>
          <div class="insight-title">${item.title}</div>
          <div class="insight-note">${item.note}</div>
        </article>
      `).join('');
    }

    function renderMonthly(metric = 'net_revenue') {
      const host = clear('monthlyChart');
      const w = host.clientWidth || 620, h = 320, pad = {t: 18, r: 24, b: 44, l: 58};
      const rows = data.monthly;
      const values = rows.map(r => metricValue(r, metric));
      const max = Math.max(...values) * 1.1;
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img'});
      const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
      for (let i = 0; i <= 4; i++) {
        const y = pad.t + plotH * i / 4;
        svg.appendChild(svgEl('line', {x1: pad.l, y1: y, x2: w - pad.r, y2: y, stroke: '#d9e1e7'}));
      }
      const points = rows.map((r, i) => {
        const x = pad.l + plotW * i / Math.max(1, rows.length - 1);
        const y = pad.t + plotH - scale(metricValue(r, metric), 0, max, 0, plotH);
        return [x, y, r];
      });
      if (metric !== 'discount_rate') {
        const barW = Math.max(10, plotW / rows.length * .52);
        points.forEach(([x, y, r], i) => {
          const val = metricValue(r, metric);
          const bh = scale(val, 0, max, 0, plotH);
          const rect = svgEl('rect', {x: x - barW / 2, y: pad.t + plotH - bh, width: barW, height: bh, rx: 4, fill: COLORS[i % COLORS.length], opacity: .82});
          rect.addEventListener('mousemove', e => showTip(e, `${r['月']}<br>${metric === 'net_revenue' ? '收入' : '订单'}：${metric === 'net_revenue' ? fmt.wan(val) : fmt.count(val)}`));
          rect.addEventListener('mouseleave', hideTip);
          svg.appendChild(rect);
        });
      } else {
        const line = svgEl('polyline', {fill: 'none', stroke: '#b85c00', 'stroke-width': 3, points: points.map(p => `${p[0]},${p[1]}`).join(' ')});
        svg.appendChild(line);
        points.forEach(([x, y, r]) => {
          const dot = svgEl('circle', {cx: x, cy: y, r: 5, fill: '#b85c00'});
          dot.addEventListener('mousemove', e => showTip(e, `${r['月']}<br>折扣率：${fmt.pct(r.discount_rate)}`));
          dot.addEventListener('mouseleave', hideTip);
          svg.appendChild(dot);
        });
      }
      rows.forEach((r, i) => {
        if (i % 2 === 0 || rows.length <= 8) {
          const x = pad.l + plotW * i / Math.max(1, rows.length - 1);
          const text = svgEl('text', {x, y: h - 16, 'text-anchor': 'middle', fill: '#627083', 'font-size': 11});
          text.textContent = String(r['月']).slice(5);
          svg.appendChild(text);
        }
      });
      host.appendChild(svg);
    }

    function renderMix() {
      const host = clear('mixChart');
      const legend = document.getElementById('mixLegend');
      const rows = [
        ['店内', data.overall.dine_in_revenue, COLORS[0]],
        ['外卖', data.overall.delivery_revenue, COLORS[2]],
        ['自提', data.overall.pickup_revenue, COLORS[4]],
      ].filter(r => Number(r[1]) > 0);
      const total = rows.reduce((a, r) => a + Number(r[1]), 0);
      const w = host.clientWidth || 460, h = 320, cx = w / 2, cy = 154, r = 104;
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`});
      let angle = -Math.PI / 2;
      rows.forEach(([name, value, color]) => {
        const slice = Number(value) / total * Math.PI * 2;
        const end = angle + slice;
        const large = slice > Math.PI ? 1 : 0;
        const x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
        const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
        const path = svgEl('path', {d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`, fill: color});
        path.addEventListener('mousemove', e => showTip(e, `${name}<br>${fmt.wan(value)} / ${(value / total * 100).toFixed(1)}%`));
        path.addEventListener('mouseleave', hideTip);
        svg.appendChild(path);
        angle = end;
      });
      svg.appendChild(svgEl('circle', {cx, cy, r: 58, fill: '#fff'}));
      const center = svgEl('text', {x: cx, y: cy - 2, 'text-anchor': 'middle', 'font-size': 24, 'font-weight': 800, fill: '#18212f'});
      center.textContent = fmt.wan(total);
      svg.appendChild(center);
      const label = svgEl('text', {x: cx, y: cy + 20, 'text-anchor': 'middle', 'font-size': 12, fill: '#627083'});
      label.textContent = '订单营业收入';
      svg.appendChild(label);
      host.appendChild(svg);
      legend.innerHTML = rows.map(([name, value, color]) => `<span class="legend-item"><span class="swatch" style="background:${color}"></span>${name} ${(value / total * 100).toFixed(1)}%</span>`).join('');
    }

    function renderHorizontalBars(id, rows, metric, labelFn, options = {}) {
      const host = clear(id);
      const w = host.clientWidth || 620, h = Math.max(300, rows.length * 34 + 56), pad = {t: 16, r: 44, b: 28, l: options.left || 110};
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`});
      const values = rows.map(r => metricValue(r, metric));
      const max = Math.max(...values) * 1.08;
      const plotW = w - pad.l - pad.r;
      rows.forEach((row, i) => {
        const y = pad.t + i * 32;
        const val = metricValue(row, metric);
        const bw = scale(val, 0, max, 0, plotW);
        const color = options.color || COLORS[i % COLORS.length];
        const label = svgEl('text', {x: pad.l - 10, y: y + 18, 'text-anchor': 'end', fill: '#18212f', 'font-size': 12});
        label.textContent = labelFn(row);
        svg.appendChild(label);
        const rect = svgEl('rect', {x: pad.l, y: y + 4, width: bw, height: 20, rx: 5, fill: color, opacity: .88});
        rect.addEventListener('mousemove', e => showTip(e, `${labelFn(row)}<br>${options.tipLabel || metric}：${metric.includes('rate') || metric.includes('share') ? fmt.pct(val) : metric.includes('aov') ? fmt.yuan(val) : fmt.wan(val)}`));
        rect.addEventListener('mouseleave', hideTip);
        svg.appendChild(rect);
        const valueLabel = svgEl('text', {x: pad.l + bw + 8, y: y + 18, fill: '#627083', 'font-size': 12});
        valueLabel.textContent = metric.includes('rate') || metric.includes('share') ? fmt.pct(val) : metric.includes('aov') ? fmt.yuan(val) : fmt.wan(val);
        svg.appendChild(valueLabel);
      });
      host.appendChild(svg);
    }

    function renderStoreBar(metric = 'net_revenue') {
      const rows = [...data.stores].sort((a, b) => metricValue(b, metric) - metricValue(a, metric));
      const labels = {net_revenue: '收入', discount_rate: '折扣率', post_discount_aov: '折后单均'};
      renderHorizontalBars('storeBarChart', rows, metric, r => r.short_name, {tipLabel: labels[metric], left: 92, color: metric === 'discount_rate' ? '#d96b3b' : '#006d77'});
    }

    function renderScatter() {
      const host = clear('storeScatter');
      const w = host.clientWidth || 620, h = 320, pad = {t: 22, r: 30, b: 44, l: 58};
      const rows = data.stores;
      const xs = rows.map(r => metricValue(r, 'post_discount_aov'));
      const ys = rows.map(r => metricValue(r, 'net_revenue'));
      const maxX = Math.max(...xs) * 1.1, minX = Math.min(...xs) * .92;
      const maxY = Math.max(...ys) * 1.08, minY = Math.min(...ys) * .88;
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`});
      const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
      svg.appendChild(svgEl('line', {x1: pad.l, y1: h - pad.b, x2: w - pad.r, y2: h - pad.b, stroke: '#d9e1e7'}));
      svg.appendChild(svgEl('line', {x1: pad.l, y1: pad.t, x2: pad.l, y2: h - pad.b, stroke: '#d9e1e7'}));
      rows.forEach((r, i) => {
        const x = scale(metricValue(r, 'post_discount_aov'), minX, maxX, pad.l, w - pad.r);
        const y = scale(metricValue(r, 'net_revenue'), minY, maxY, h - pad.b, pad.t);
        const radius = scale(metricValue(r, 'discount_rate'), 0.08, 0.15, 7, 18);
        const dot = svgEl('circle', {cx: x, cy: y, r: Math.max(7, radius), fill: COLORS[i % COLORS.length], opacity: .82});
        dot.addEventListener('mousemove', e => showTip(e, `${r.short_name}<br>收入：${fmt.wan(r.net_revenue)}<br>客单：${fmt.yuan(r.post_discount_aov)}<br>折扣：${fmt.pct(r.discount_rate)}`));
        dot.addEventListener('mouseleave', hideTip);
        svg.appendChild(dot);
        const text = svgEl('text', {x: x + 10, y: y + 4, fill: '#18212f', 'font-size': 11});
        text.textContent = r.short_name.slice(0, 4);
        svg.appendChild(text);
      });
      const xLabel = svgEl('text', {x: w / 2, y: h - 10, 'text-anchor': 'middle', fill: '#627083', 'font-size': 12});
      xLabel.textContent = '折后单均';
      svg.appendChild(xLabel);
      const yLabel = svgEl('text', {x: 14, y: 24, fill: '#627083', 'font-size': 12});
      yLabel.textContent = '收入';
      svg.appendChild(yLabel);
      host.appendChild(svg);
    }

    function renderSegments() {
      const order = ['明星店', '稳定现金流', '结构机会店', '低效待改善'];
      const grid = document.getElementById('segmentGrid');
      grid.innerHTML = order.map(name => {
        const count = data.store_segments[name] || 0;
        const stores = data.stores.filter(s => s.segment === name).map(s => s.short_name).join('、') || '暂无';
        return `<div class="segment"><span class="tile-label">${name}</span><b>${count} 家</b><div class="tile-foot">${stores}</div></div>`;
      }).join('');
    }

    let storeSort = {key: 'net_revenue', dir: -1};
    function renderStoreTable() {
      const tbody = document.querySelector('#storeTable tbody');
      const rows = [...data.stores].sort((a, b) => {
        const av = a[storeSort.key], bv = b[storeSort.key];
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * storeSort.dir;
        return String(av).localeCompare(String(bv), 'zh-CN') * storeSort.dir;
      });
      tbody.innerHTML = rows.map(r => `
        <tr>
          <td>${r.short_name}</td>
          <td><span class="tag">${r.segment}</span></td>
          <td>${fmt.wan(r.net_revenue)}</td>
          <td>${fmt.pct(r.discount_rate)}</td>
          <td>${fmt.yuan(r.post_discount_aov)}</td>
          <td>${fmt.pct(r.delivery_revenue_share)}</td>
          <td>${fmt.pct(r.member_revenue_share)}</td>
          <td>${r.action}</td>
        </tr>
      `).join('');
    }

    function renderChannelChart() {
      const rows = [...data.channels].sort((a, b) => metricValue(b, 'net_revenue') - metricValue(a, 'net_revenue'));
      const host = clear('channelChart');
      const w = host.clientWidth || 620, h = Math.max(320, rows.length * 36 + 56), pad = {t: 16, r: 58, b: 28, l: 128};
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`});
      const max = Math.max(...rows.map(r => metricValue(r, 'net_revenue'))) * 1.08;
      const plotW = w - pad.l - pad.r;
      rows.forEach((row, i) => {
        const y = pad.t + i * 34;
        const labelText = `${row['订单分类']}/${row['订单来源']}`;
        const label = svgEl('text', {x: pad.l - 10, y: y + 18, 'text-anchor': 'end', fill: '#18212f', 'font-size': 11});
        label.textContent = labelText.length > 12 ? labelText.slice(0, 12) : labelText;
        svg.appendChild(label);
        const bw = scale(metricValue(row, 'net_revenue'), 0, max, 0, plotW);
        const rect = svgEl('rect', {x: pad.l, y: y + 4, width: bw, height: 20, rx: 5, fill: COLORS[i % COLORS.length], opacity: .86});
        rect.addEventListener('mousemove', e => showTip(e, `${labelText}<br>收入：${fmt.wan(row.net_revenue)}<br>折扣：${fmt.pct(row.discount_rate)}<br>客单：${fmt.yuan(row.post_discount_aov)}`));
        rect.addEventListener('mouseleave', hideTip);
        svg.appendChild(rect);
        const dotX = pad.l + scale(metricValue(row, 'discount_rate'), 0, .36, 0, plotW);
        svg.appendChild(svgEl('circle', {cx: dotX, cy: y + 14, r: 5, fill: '#d96b3b', stroke: '#fff', 'stroke-width': 2}));
      });
      host.appendChild(svg);
    }

    function renderMemberChart() {
      const rows = data.members;
      renderHorizontalBars('memberChart', rows, 'net_revenue', r => r['会员类型'], {tipLabel: '收入', left: 80, color: '#355c9f'});
    }

    function renderHeatmap() {
      const host = clear('heatmapChart');
      host.style.overflowX = 'auto';
      host.style.overflowY = 'hidden';
      host.style.paddingBottom = '4px';
      const rows = data.dayparts.filter(r => r['餐段'] && r['时段']);
      const dayparts = [...new Set(rows.map(r => r['餐段']))];
      const times = [...new Set(rows.map(r => r['时段']))].sort();
      const map = new Map(rows.map(r => [`${r['餐段']}|${r['时段']}`, r]));
      const containerW = host.clientWidth || 640;
      const labelW = containerW < 520 ? 76 : 88;
      const minCellW = containerW < 520 ? 18 : 20;
      const rightPad = 12;
      const fittedCellW = (containerW - labelW - rightPad) / Math.max(1, times.length);
      const cellW = Math.max(minCellW, fittedCellW);
      const w = Math.max(containerW, labelW + times.length * cellW + rightPad);
      const cellH = 32;
      const h = 54 + dayparts.length * cellH;
      const max = Math.max(...rows.map(r => metricValue(r, 'net_revenue')));
      const svg = svgEl('svg', {viewBox: `0 0 ${w} ${h}`});
      svg.style.width = `${w}px`;
      svg.style.height = `${h}px`;
      times.forEach((t, i) => {
        const text = svgEl('text', {x: labelW + i * cellW + cellW / 2, y: 22, 'text-anchor': 'middle', fill: '#627083', 'font-size': 10});
        text.textContent = t.slice(0, 2);
        svg.appendChild(text);
      });
      dayparts.forEach((d, yIdx) => {
        const label = svgEl('text', {x: labelW - 8, y: 48 + yIdx * cellH, 'text-anchor': 'end', fill: '#18212f', 'font-size': 12});
        label.textContent = d.trim() || '未设置';
        svg.appendChild(label);
        times.forEach((t, xIdx) => {
          const row = map.get(`${d}|${t}`);
          const val = row ? metricValue(row, 'net_revenue') : 0;
          const alpha = val ? scale(val, 0, max, .15, 1) : .04;
          const rect = svgEl('rect', {x: labelW + xIdx * cellW, y: 30 + yIdx * cellH, width: Math.max(4, cellW - 3), height: cellH - 4, rx: 4, fill: '#006d77', opacity: alpha});
          rect.addEventListener('mousemove', e => showTip(e, `${d} ${t}<br>收入：${fmt.wan(val)}<br>订单：${fmt.count(row ? row.positive_orders : 0)}<br>折扣：${fmt.pct(row ? row.discount_rate : 0)}`));
          rect.addEventListener('mouseleave', hideTip);
          svg.appendChild(rect);
        });
      });
      host.appendChild(svg);
    }

    function renderDaypartBar() {
      const rows = [...data.dayparts].sort((a, b) => metricValue(b, 'net_revenue') - metricValue(a, 'net_revenue')).slice(0, 12);
      renderHorizontalBars('daypartBar', rows, 'net_revenue', r => `${r['餐段']} ${r['时段']}`, {left: 128, color: '#3a7d44'});
    }

    function renderOpportunities() {
      const grid = document.getElementById('opportunityGrid');
      grid.innerHTML = data.opportunities.map((o, i) => `
        <article class="opportunity">
          <span class="tile-label">${o.name}</span>
          <div class="value">${fmt.plainWan(o.value)}${o.unit}</div>
          <div class="logic">${o.logic}</div>
          <div class="legend">
            <span class="legend-item"><span class="swatch" style="background:${COLORS[i]}"></span>置信度 ${o.confidence}</span>
            <span class="legend-item">执行 ${o.effort}</span>
          </div>
          <div class="owner">责任方向：${o.owner}</div>
        </article>
      `).join('');
    }

    function bindControls() {
      document.querySelectorAll('[data-month-metric]').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('[data-month-metric]').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          renderMonthly(btn.dataset.monthMetric);
        });
      });
      document.querySelectorAll('[data-store-metric]').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('[data-store-metric]').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          renderStoreBar(btn.dataset.storeMetric);
        });
      });
      document.querySelectorAll('#storeTable th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.sort;
          storeSort.dir = storeSort.key === key ? storeSort.dir * -1 : -1;
          storeSort.key = key;
          renderStoreTable();
        });
      });
      window.addEventListener('resize', () => {
        renderMonthly(document.querySelector('[data-month-metric].active').dataset.monthMetric);
        renderMix();
        renderStoreBar(document.querySelector('[data-store-metric].active').dataset.storeMetric);
        renderScatter();
        renderChannelChart();
        renderMemberChart();
        renderHeatmap();
        renderDaypartBar();
      });
    }

    fillNumbers();
    renderInsights();
    renderMonthly();
    renderMix();
    renderStoreBar();
    renderScatter();
    renderSegments();
    renderStoreTable();
    renderChannelChart();
    renderMemberChart();
    renderHeatmap();
    renderDaypartBar();
    renderOpportunities();
    bindControls();
  </script>
</body>
</html>
'''


def generate(input_dir: Path, output: Path, company: str, source_name: str) -> None:
    payload = prepare_payload(input_dir, company, source_name)
    overall = payload["overall"]
    meta = payload["meta"]
    replacements = {
        "__PAYLOAD__": json.dumps(payload, ensure_ascii=False),
        "__REPORT_TITLE__": str(meta["title"]),
        "__NAV_TITLE__": f"{company}经营诊断",
        "__PERIOD__": str(meta["period"]),
        "__DATA_ROWS__": f"{int(meta['data_rows']):,}",
        "__STORE_COUNT__": str(meta["store_count"]),
        "__CITY_LABEL__": str(meta["city_label"]),
        "__SOURCE_NAME__": str(meta["source"]),
        "__GENERATED_DATE__": str(meta["generated"]),
        "__SKIPPED_SUMMARY_ROWS__": str(meta["skipped_summary_rows"]),
        "__GROSS_SALES__": str(overall["gross_sales"]),
        "__NET_REVENUE__": str(overall["net_revenue"]),
        "__DISCOUNT_AMOUNT__": str(overall["discount_amount"]),
        "__DISCOUNT_RATE__": str(overall["discount_rate"]),
        "__POSITIVE_ORDERS__": str(overall["positive_orders"]),
        "__POST_DISCOUNT_AOV__": str(overall["post_discount_aov"]),
    }
    html = HTML_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    parser.add_argument("--source-name", default="business_data.xlsx")
    args = parser.parse_args()
    generate(args.input_dir, args.output, args.company, args.source_name)
    print(args.output)


if __name__ == "__main__":
    main()
