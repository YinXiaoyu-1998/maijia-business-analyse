#!/usr/bin/env python3
"""Generate a self-contained weekly meeting HTML report."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
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


def safe_sum(rows: list[dict[str, Any]], field: str) -> float:
    return round(sum(float(row.get(field) or 0) for row in rows), 2)


def pct_change(current: float, baseline: float) -> float | None:
    if abs(baseline) < 1e-12:
        return None
    return round((current - baseline) / baseline, 4)


def aggregate_dayparts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], float] = {}
    for row in rows:
        key = (str(row.get("period") or ""), str(row.get("餐段") or "未知餐段"), str(row.get("时段") or "未知时段"))
        groups[key] = groups.get(key, 0.0) + float(row.get("net_revenue") or 0)
    return [
        {"period": key[0], "餐段": key[1], "时段": key[2], "net_revenue": round(value, 2)}
        for key, value in sorted(groups.items())
    ]


def parse_report_date(value: Any) -> date | None:
    text = str(value or "").strip().replace("-", "/")
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y/%m/%d").date()
    except ValueError:
        return None


def aggregate_trend(rows: list[dict[str, Any]], max_week_end: date | None) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, float]] = {}
    for row in rows:
        week_end = parse_report_date(row.get("week_end"))
        if max_week_end and week_end and week_end > max_week_end:
            continue
        label = str(row.get("week_label") or "")
        item = groups.setdefault(label, {"net_revenue": 0.0, "dine_in_revenue": 0.0, "delivery_revenue": 0.0})
        item["net_revenue"] += float(row.get("net_revenue") or 0)
        item["dine_in_revenue"] += float(row.get("dine_in_revenue") or 0)
        item["delivery_revenue"] += float(row.get("delivery_revenue") or 0)
    result = []
    for label, values in groups.items():
        result.append({"week_label": label, **{key: round(value, 2) for key, value in values.items()}})
    result.sort(key=lambda row: row["week_label"])
    return result[-16:]


def build_trend_entities(rows: list[dict[str, Any]], max_week_end: date | None) -> list[dict[str, Any]]:
    stores = sorted({str(row.get("门店名称") or "") for row in rows if row.get("门店名称")})
    entities = [
        {"key": "__all__", "label": "全体门店", "rows": aggregate_trend(rows, max_week_end)}
    ]
    for store in stores:
        store_rows = [row for row in rows if row.get("门店名称") == store]
        entities.append({"key": store, "label": store, "rows": aggregate_trend(store_rows, max_week_end)})
    return entities


def build_trend_comparison_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    def build_series(entity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[int, dict[str, Any]] = {}
        for row in entity_rows:
            try:
                window_index = int(float(row.get("window_index") or 0))
            except (TypeError, ValueError):
                continue
            if window_index <= 0:
                continue
            item = groups.setdefault(
                window_index,
                {
                    "window_index": window_index,
                    "week_label": row.get("week_label") or "",
                    "current_net_revenue": None,
                    "prior_net_revenue": None,
                    "current_week_range": "",
                    "prior_week_range": "",
                },
            )
            series_key = str(row.get("series_key") or "")
            revenue = float(row.get("net_revenue") or 0)
            week_range = f"{row.get('week_start')}-{row.get('week_end')}"
            if series_key == "current_year":
                item["current_net_revenue"] = round((item["current_net_revenue"] or 0) + revenue, 2)
                item["current_week_range"] = week_range
            elif series_key == "prior_year":
                item["prior_net_revenue"] = round((item["prior_net_revenue"] or 0) + revenue, 2)
                item["prior_week_range"] = week_range
        return [groups[index] for index in sorted(groups)]

    stores = sorted({str(row.get("门店名称") or "") for row in rows if row.get("门店名称")})
    entities = [{"key": "__all__", "label": "全体门店", "rows": build_series(rows)}]
    for store in stores:
        store_rows = [row for row in rows if row.get("门店名称") == store]
        entities.append({"key": store, "label": store, "rows": build_series(store_rows)})
    return entities


def median(values: list[float]) -> float:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return 0
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def build_payload(input_dir: Path, company: str) -> dict[str, Any]:
    summary = json.loads((input_dir / "weekly_meeting_summary.json").read_text(encoding="utf-8"))
    comparison = read_csv(input_dir / "weekly_store_comparison.csv")
    segments = read_csv(input_dir / "star_problem_stores.csv")
    drivers = read_csv(input_dir / "store_driver_summary.csv")
    channels = read_csv(input_dir / "weekly_store_channel_metrics.csv")
    dayparts = read_csv(input_dir / "weekly_store_daypart_metrics.csv")
    weekly = read_csv(input_dir / "weekly_store_metrics.csv")
    trend_comparison_path = input_dir / "weekly_trend_comparison_metrics.csv"
    trend_comparison = read_csv(trend_comparison_path) if trend_comparison_path.exists() else []

    segment_by_store = {row["门店名称"]: row for row in segments}
    driver_by_store = {
        row["门店名称"]: row
        for row in drivers
        if row.get("basis") == "环比"
    }
    for row in comparison:
        segment = segment_by_store.get(row["门店名称"], {})
        driver = driver_by_store.get(row["门店名称"], {})
        row["segment"] = segment.get("segment", "未分型")
        row["segment_reason"] = segment.get("reason", "")
        row["top_negative_factor"] = driver.get("top_negative_factor", "")
        row["wow_order_volume_contribution"] = driver.get("order_volume_contribution")
        row["wow_aov_contribution"] = driver.get("aov_contribution")
        row["wow_dine_in_delta"] = driver.get("dine_in_delta")
        row["wow_delivery_delta"] = driver.get("delivery_delta")

    comparison.sort(key=lambda row: float(row.get("current_net_revenue") or 0), reverse=True)
    current_revenue = safe_sum(comparison, "current_net_revenue")
    previous_revenue = safe_sum(comparison, "previous_net_revenue")
    yoy_revenue = safe_sum(comparison, "yoy_net_revenue")
    current_customers = safe_sum(comparison, "current_customer_count")
    current_tables = safe_sum(comparison, "current_consumed_tables")
    current_aov = current_revenue / safe_sum(comparison, "current_positive_orders") if safe_sum(comparison, "current_positive_orders") else 0
    star_count = sum(1 for row in comparison if row.get("segment") == "明星门店")
    problem_count = sum(1 for row in comparison if row.get("segment") == "问题门店")
    revenue_threshold = median([float(row.get("current_net_revenue") or 0) for row in comparison])
    current_window_end = parse_report_date(summary["meta"]["target_windows"]["current"]["end"])
    yoy_window_end = parse_report_date(summary["meta"]["target_windows"]["yoy"]["end"])
    current_trend_start = current_window_end.fromordinal(current_window_end.toordinal() - 111) if current_window_end else None
    yoy_trend_start = yoy_window_end.fromordinal(yoy_window_end.toordinal() - 111) if yoy_window_end else None
    trend_note = "完整周口径；实线=本年，虚线=同期，均为最近 16 个自然周窗口。"
    def short_date(value: date) -> str:
        return f"{value.month}/{value.day}"

    if current_window_end and yoy_window_end and current_trend_start and yoy_trend_start:
        trend_note = (
            f"完整周口径；实线={current_window_end:%Y}（{short_date(current_trend_start)}-{short_date(current_window_end)}），"
            f"虚线={yoy_window_end:%Y}同期（{short_date(yoy_trend_start)}-{short_date(yoy_window_end)}）。"
        )

    current_channels = [row for row in channels if row.get("period") == "本周"]
    channel_by_store: dict[str, dict[str, float]] = {}
    for row in current_channels:
        store = str(row.get("门店名称") or "")
        channel = str(row.get("channel") or "")
        channel_by_store.setdefault(store, {})[channel] = float(row.get("net_revenue") or 0)

    return {
        "meta": {
            "title": f"{company}周经营会报",
            "company": company,
            "generated": date.today().isoformat(),
            **summary["meta"],
        },
        "kpis": {
            "current_revenue": current_revenue,
            "wow_pct": pct_change(current_revenue, previous_revenue),
            "yoy_pct": pct_change(current_revenue, yoy_revenue),
            "current_customers": current_customers,
            "current_tables": current_tables,
            "current_aov": round(current_aov, 2),
            "star_count": star_count,
            "problem_count": problem_count,
        },
        "segment_rules": {
            "revenue_threshold": round(revenue_threshold, 2),
            "growth_threshold": 0,
            "items": [
                {
                    "name": "明星门店",
                    "logic": "本周业务收入 >= 门店中位数，且环比增长率 >= 0%",
                    "use": "优先沉淀打法，复盘可复制动作。",
                },
                {
                    "name": "高基盘承压",
                    "logic": "本周业务收入 >= 门店中位数，但环比增长率 < 0%",
                    "use": "收入体量仍大，但要复盘短期下滑原因。",
                },
                {
                    "name": "成长观察",
                    "logic": "本周业务收入 < 门店中位数，但环比增长率 >= 0%",
                    "use": "关注增长是否可持续，寻找放大空间。",
                },
                {
                    "name": "问题门店",
                    "logic": "本周业务收入 < 门店中位数，且环比增长率 < 0%",
                    "use": "优先排查客流、开台、客单和折扣拖累。",
                },
            ],
            "warnings": "同比下滑超过 25%、环比下滑超过 8%、折扣率高于门店中位水平 20% 以上、客单价低于门店中位水平 10% 以上，会作为预警补充到门店原因中。",
        },
        "comparison": comparison,
        "drivers": [row for row in drivers if row.get("basis") == "环比"],
        "segments": segments,
        "channel_by_store": channel_by_store,
        "dayparts": aggregate_dayparts([row for row in dayparts if row.get("period") in {"本周", "环比周"}]),
        "trend": aggregate_trend(weekly, current_window_end),
        "trend_entities": build_trend_comparison_entities(trend_comparison) or build_trend_entities(weekly, current_window_end),
        "trend_note": trend_note,
        "data_gaps": summary.get("data_gaps", []),
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --surface: #fff;
      --ink: #172033;
      --muted: #657386;
      --line: #d9e2ea;
      --teal: #006d77;
      --blue: #2f5b9f;
      --green: #3a7d44;
      --amber: #b85c00;
      --red: #b23a48;
      --violet: #7557a6;
      --shadow: 0 14px 34px rgba(23, 32, 51, .07);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(245, 247, 250, .95);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }
    .topbar-inner {
      max-width: 1360px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
    }
    .brand { font-weight: 820; display: flex; align-items: center; gap: 10px; }
    .mark { width: 30px; height: 30px; border-radius: 8px; background: linear-gradient(135deg, var(--teal), var(--blue)); }
    .nav { display: flex; flex-wrap: wrap; gap: 6px; }
    .nav a {
      color: var(--muted);
      text-decoration: none;
      padding: 7px 10px;
      border-radius: 999px;
    }
    .nav a:hover { background: var(--surface); color: var(--ink); }
    main { max-width: 1360px; margin: 0 auto; padding: 26px 24px 64px; }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(320px, .7fr);
      gap: 22px;
      align-items: stretch;
      padding: 12px 0 24px;
    }
    h1 { font-size: 38px; line-height: 1.12; margin: 8px 0 12px; }
    h2 { font-size: 24px; line-height: 1.24; margin: 0; }
    h3 { font-size: 16px; margin: 0; }
    .kicker { color: var(--teal); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .lede { color: var(--muted); max-width: 780px; font-size: 16px; margin: 0; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
    .chip { border: 1px solid var(--line); background: var(--surface); color: var(--muted); padding: 7px 10px; border-radius: 999px; }
    .summary {
      background: #172033;
      color: #fff;
      border-radius: var(--radius);
      padding: 20px;
      display: grid;
      gap: 12px;
      box-shadow: var(--shadow);
    }
    .summary b { font-size: 28px; display: block; line-height: 1.1; margin-top: 6px; }
    .summary span { color: rgba(255,255,255,.72); }
    .section { border-top: 1px solid var(--line); padding: 30px 0; }
    .section-head { display: flex; justify-content: space-between; align-items: end; gap: 18px; margin-bottom: 16px; }
    .note { color: var(--muted); max-width: 620px; margin: 0; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .full-row { margin-top: 16px; }
    .rule-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    .rule {
      border: 1px dashed var(--line);
      background: var(--surface);
      border-radius: var(--radius);
      padding: 13px;
      min-height: 126px;
    }
    .rule-title { font-weight: 820; display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .rule p { margin: 0; color: var(--muted); font-size: 12px; }
    .rule small { display: block; color: var(--ink); margin-top: 8px; font-size: 12px; }
    .rule-note { color: var(--muted); margin-top: 10px; font-size: 12px; }
    .card, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 24px rgba(23, 32, 51, .045);
    }
    .card { padding: 15px; min-height: 120px; }
    .label { color: var(--muted); font-size: 12px; font-weight: 760; }
    .value { font-size: 28px; font-weight: 840; line-height: 1; margin-top: 8px; }
    .foot { color: var(--muted); font-size: 12px; margin-top: 10px; }
    .panel { padding: 17px; min-width: 0; }
    .panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 8px; }
    .panel-title-row { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .mini-select {
      height: 32px;
      min-width: 150px;
      max-width: 240px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--ink);
      padding: 0 32px 0 10px;
      font: inherit;
      font-weight: 700;
      outline: none;
    }
    .mini-select:focus { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(0, 109, 119, .12); }
    .chart { width: 100%; min-height: 310px; overflow: hidden; position: relative; }
    .chart svg { display: block; width: 100%; min-height: 310px; }
    .chart-tooltip {
      position: absolute;
      display: none;
      pointer-events: none;
      z-index: 4;
      background: #111827;
      color: #fff;
      border-radius: 6px;
      padding: 7px 9px;
      font-size: 12px;
      line-height: 1.35;
      box-shadow: 0 8px 20px rgba(17, 24, 39, .18);
      white-space: nowrap;
    }
    .chart-tooltip strong { display: block; margin-bottom: 2px; color: #fff; }
    .legend { display: flex; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-top: 8px; }
    .swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; margin-right: 5px; }
    .table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
    table { border-collapse: collapse; width: 100%; min-width: 1180px; }
    th, td { padding: 10px 11px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
    th { background: #f0f4f7; color: var(--muted); font-size: 12px; position: sticky; top: 0; cursor: pointer; }
    td { font-size: 13px; }
    .tag { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #edf5f3; color: var(--teal); font-weight: 760; font-size: 12px; }
    .tag.problem { background: #fff0f2; color: var(--red); }
    .tag.star { background: #eef8ef; color: var(--green); }
    .tag.pressure { background: #fff5e8; color: var(--amber); }
    .tag.growth { background: #edf3ff; color: var(--blue); }
    .callout { border-left: 4px solid var(--amber); background: #fff8ef; border-radius: 0 8px 8px 0; padding: 14px 16px; color: #61420f; }
    .heatmap { display: grid; gap: 3px; overflow: auto; padding-bottom: 8px; }
    .heat-row { display: grid; grid-template-columns: 82px repeat(24, minmax(28px, 1fr)); gap: 3px; align-items: center; min-width: 980px; }
    .heat-label { color: var(--muted); font-size: 12px; text-align: right; padding-right: 6px; }
    .heat-cell { height: 24px; border-radius: 4px; background: #eef3f4; position: relative; }
    .heat-cell:hover::after {
      content: attr(data-tip);
      position: absolute;
      left: 50%;
      bottom: 120%;
      transform: translateX(-50%);
      background: #111827;
      color: #fff;
      padding: 6px 8px;
      border-radius: 5px;
      white-space: nowrap;
      z-index: 3;
      font-size: 12px;
    }
    @media (max-width: 980px) {
      .hero, .grid-2, .grid-3 { grid-template-columns: 1fr; }
      .grid-4, .rule-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .section-head { align-items: start; flex-direction: column; }
    }
    @media (max-width: 620px) {
      main { padding: 18px 14px 48px; }
      .topbar-inner { align-items: start; flex-direction: column; }
      .grid-4, .rule-grid { grid-template-columns: 1fr; }
      h1 { font-size: 30px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand"><span class="mark"></span><span>麦家小馆周经营会报</span></div>
      <nav class="nav">
        <a href="#summary">结论</a>
        <a href="#ranking">横向对比</a>
        <a href="#stores">门店明细</a>
        <a href="#channels">堂食外卖</a>
        <a href="#drivers">归因</a>
        <a href="#dayparts">餐段</a>
      </nav>
    </div>
  </header>
  <main>
    <section class="hero">
      <div>
        <div class="kicker">Weekly Operating Review</div>
        <h1>麦家小馆周经营会报</h1>
        <p class="lede">基于美团营业分组表，聚焦每家门店本周经营、同比/环比变化、堂食/外卖结构、客流/开台/客单归因，以及明星与问题门店识别。</p>
        <div class="meta" id="metaChips"></div>
      </div>
      <aside class="summary">
        <div><span>本周业务收入</span><b id="heroRevenue"></b></div>
        <div class="grid-2">
          <div><span>环比</span><b id="heroWow"></b></div>
          <div><span>同比</span><b id="heroYoy"></b></div>
        </div>
      </aside>
    </section>

    <section class="section" id="summary">
      <div class="section-head">
        <div><div class="kicker">01 Executive Summary</div><h2>先看结论：哪些门店值得复制，哪些门店要复盘</h2></div>
        <p class="note">本页所有指标均为聚合后重新计算；网评与档口不在当前营业分组表中，不做推测。</p>
      </div>
      <div class="grid-4" id="kpiCards"></div>
      <div id="segmentRules"></div>
    </section>

    <section class="section" id="ranking">
      <div class="section-head">
        <div><div class="kicker">02 Store Benchmark</div><h2>门店横向对比：收入规模、增长和经营效率一起看</h2></div>
      </div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-head"><h3>本周门店业务收入排名</h3><span class="label">订单营业收入</span></div>
          <div class="chart" id="revenueBar"></div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>明星与问题门店四象限</h3><span class="label">虚线：环比 0% / 收入中位数</span></div>
          <div class="chart" id="scatter"></div>
        </div>
      </div>
      <div class="panel full-row">
        <div class="panel-head"><h3>同比 / 环比增长率</h3><span class="label">绿色=环比，蓝色=同比；正向右，负向左</span></div>
        <div class="chart" id="growthBar"></div>
      </div>
      <div class="panel full-row">
        <div class="panel-head">
          <div class="panel-title-row"><h3>最近 16 周收入趋势</h3><select id="trendStoreSelect" class="mini-select" aria-label="选择门店趋势"></select></div>
          <span class="label" id="trendMetricLabel">完整周，整体业务收入（万元）；实线=本年，虚线=同期</span>
        </div>
        <div class="chart" id="trend"></div>
      </div>
    </section>

    <section class="section" id="stores">
      <div class="section-head">
        <div><div class="kicker">03 Store Detail</div><h2>门店明细：本周值、同比、环比和主要提示</h2></div>
        <p class="note">点击表头可排序。问题门店优先看“主要负向因素”。</p>
      </div>
      <div class="table-wrap">
        <table id="storeTable">
          <thead><tr>
            <th data-key="门店名称">门店</th>
            <th data-key="segment">分型</th>
            <th data-key="current_net_revenue">业务收入</th>
            <th data-key="wow_net_revenue_pct">环比</th>
            <th data-key="yoy_net_revenue_pct">同比</th>
            <th data-key="current_dine_in_revenue">堂食收入</th>
            <th data-key="current_delivery_revenue">外卖收入</th>
            <th data-key="current_customer_count">客流</th>
            <th data-key="current_consumed_tables">开台/桌数</th>
            <th data-key="current_post_discount_aov">客单价</th>
            <th data-key="current_discount_rate">折扣率</th>
            <th data-key="top_negative_factor">主要提示</th>
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="section" id="channels">
      <div class="section-head">
        <div><div class="kicker">04 Dine-in / Delivery</div><h2>堂食与外卖：收入结构和变化贡献</h2></div>
      </div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-head"><h3>本周堂食 / 外卖结构</h3><span class="label">按门店堆叠</span></div>
          <div class="chart" id="mixBar"></div>
          <div class="legend"><span><i class="swatch" style="background:#006d77"></i>堂食</span><span><i class="swatch" style="background:#2f5b9f"></i>外卖</span><span><i class="swatch" style="background:#b85c00"></i>其他</span></div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>外卖平台收入</h3><span class="label">美团 / 饿了么 / 京东</span></div>
          <div class="chart" id="platformBar"></div>
          <div class="legend"><span><i class="swatch" style="background:#3a7d44"></i>美团</span><span><i class="swatch" style="background:#7557a6"></i>饿了么</span><span><i class="swatch" style="background:#d96b3b"></i>京东</span></div>
        </div>
      </div>
    </section>

    <section class="section" id="drivers">
      <div class="section-head">
        <div><div class="kicker">05 Drivers</div><h2>问题归因：客流/订单量与客单价谁在拖动收入</h2></div>
        <p class="note">归因为近似拆解，用于周会定位复盘方向，不替代门店现场判断。</p>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Top 问题门店环比归因</h3><span class="label">量贡献 vs 价贡献</span></div>
        <div class="chart" id="driverBar"></div>
      </div>
      <div class="full-row">
        <div class="panel">
          <div class="panel-head"><h3>经营动作提示</h3><span class="label">按分型汇总</span></div>
          <div id="actionList"></div>
        </div>
      </div>
    </section>

    <section class="section" id="dayparts">
      <div class="section-head">
        <div><div class="kicker">06 Daypart</div><h2>餐段/时段热力：看高峰，也看环比掉点</h2></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>本周餐段 × 时段收入热力图</h3><span class="label">悬停查看收入</span></div>
        <div id="heatmap" class="heatmap"></div>
      </div>
      <div class="callout" style="margin-top:16px;" id="dataGaps"></div>
    </section>
  </main>
  <script id="payload" type="application/json">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById('payload').textContent);
    const stores = data.comparison;
    const fmtWan = v => {
      const raw = Number(v || 0) / 10000;
      const value = Math.abs(raw) < 0.05 ? 0 : raw;
      return `${value.toLocaleString('zh-CN', {maximumFractionDigits: 1})}万`;
    };
    const fmtNum = v => Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 0});
    const fmtYuan = v => `${Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1})}元`;
    const fmtPct = v => v === null || v === undefined || v === '' ? 'N/A' : `${(Number(v) * 100).toFixed(1)}%`;
    const cleanName = s => String(s || '').replace('麦家小馆（', '').replace('）', '');
    const colors = { teal:'#006d77', blue:'#2f5b9f', green:'#3a7d44', amber:'#b85c00', red:'#b23a48', violet:'#7557a6', orange:'#d96b3b' };
    let selectedTrendKey = '__all__';
    const currentTrendYear = String(data.meta?.target_windows?.current?.end || '').slice(0, 4) || '本年';
    const yoyTrendYear = String(data.meta?.target_windows?.yoy?.end || '').slice(0, 4) || '同期';

    function setText(id, value) { document.getElementById(id).textContent = value; }
    function svg(tag, attrs = {}) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
      return el;
    }
    function renderMeta() {
      const meta = data.meta;
      document.getElementById('metaChips').innerHTML = [
        `本周：${meta.target_windows.current.start}-${meta.target_windows.current.end}`,
        `环比：${meta.target_windows.previous.start}-${meta.target_windows.previous.end}`,
        `同比：${meta.target_windows.yoy.start}-${meta.target_windows.yoy.end}`,
        `覆盖：${meta.coverage_start}-${meta.coverage_end}`,
        `门店：${meta.store_count}家`
      ].map(x => `<span class="chip">${x}</span>`).join('');
    }
    function renderKpis() {
      const k = data.kpis;
      setText('heroRevenue', fmtWan(k.current_revenue));
      setText('heroWow', fmtPct(k.wow_pct));
      setText('heroYoy', fmtPct(k.yoy_pct));
      const cards = [
        ['业务收入', fmtWan(k.current_revenue), `环比 ${fmtPct(k.wow_pct)} / 同比 ${fmtPct(k.yoy_pct)}`],
        ['客流量', fmtNum(k.current_customers), '口径：用餐人数'],
        ['开台数', fmtNum(k.current_tables), '口径：消费桌数'],
        ['门店分型', `${k.star_count} 明星 / ${k.problem_count} 问题`, '按收入中位数与环比 0% 划分象限']
      ];
      document.getElementById('kpiCards').innerHTML = cards.map(c => `<div class="card"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="foot">${c[2]}</div></div>`).join('');
    }
    function ruleColor(name) {
      return name === '明星门店' ? colors.green : name === '问题门店' ? colors.red : name === '高基盘承压' ? colors.amber : colors.blue;
    }
    function renderRules() {
      const rules = data.segment_rules;
      document.getElementById('segmentRules').innerHTML = `
        <div class="rule-note">门店分型基准：纵轴使用本周业务收入门店中位数 ${fmtWan(rules.revenue_threshold)}，横轴使用环比增长率 ${fmtPct(rules.growth_threshold)}。四象限只定义经营位置，预警项用于补充复盘优先级。</div>
        <div class="rule-grid">
          ${rules.items.map(item => `<div class="rule">
            <div class="rule-title"><i class="dot" style="background:${ruleColor(item.name)}"></i>${item.name}</div>
            <p>${item.logic}</p>
            <small>${item.use}</small>
          </div>`).join('')}
        </div>
        <div class="rule-note">预警补充：${rules.warnings}</div>`;
    }
    function renderHorizontalBar(id, rows, field, formatter, color) {
      const el = document.getElementById(id);
      const w = 760, h = Math.max(300, rows.length * 32 + 48), left = 150, right = 80;
      const max = Math.max(...rows.map(r => Math.abs(Number(r[field] || 0))), 1);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      rows.forEach((r, i) => {
        const y = 28 + i * 32;
        const val = Number(r[field] || 0);
        const bw = Math.abs(val) / max * (w - left - right);
        root.appendChild(svg('text', {x: left - 8, y: y + 15, 'text-anchor':'end', 'font-size':'12', fill:'#344054'})).textContent = cleanName(r['门店名称']);
        root.appendChild(svg('rect', {x: left, y, width: bw, height: 18, rx: 4, fill: color}));
        root.appendChild(svg('text', {x: left + bw + 8, y: y + 14, 'font-size':'12', fill:'#657386'})).textContent = formatter(val);
      });
      el.innerHTML = '';
      el.appendChild(root);
    }
    function renderGrowthBar() {
      const el = document.getElementById('growthBar');
      const rows = stores.slice().sort((a,b)=>Number(b.wow_net_revenue_pct||0)-Number(a.wow_net_revenue_pct||0));
      const w = 1120, h = Math.max(450, rows.length * 54 + 102), left = 180, mid = 575, right = 120;
      const vals = rows.flatMap(r => [Number(r.wow_net_revenue_pct||0), Number(r.yoy_net_revenue_pct||0)]);
      const max = Math.max(...vals.map(v => Math.abs(v)), .01);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      [[colors.green, '环比'], [colors.blue, '同比']].forEach(([color, label], index) => {
        const x = left + index * 76;
        root.appendChild(svg('rect', {x, y:18, width:12, height:12, rx:2, fill:color}));
        root.appendChild(svg('text', {x:x+18, y:29, 'font-size':'12', fill:'#657386', 'font-weight':'700'})).textContent = label;
      });
      root.appendChild(svg('text', {x: w - right, y: 29, 'text-anchor':'end', 'font-size':'11', fill:'#657386'})).textContent = '0% 为中心线';
      root.appendChild(svg('line', {x1: mid, y1: 46, x2: mid, y2: h - 26, stroke:'#d9e2ea'}));
      rows.forEach((r, i) => {
        const y = 64 + i * 54;
        if (i > 0) {
          root.appendChild(svg('line', {x1: left, y1: y - 12, x2: w - right, y2: y - 12, stroke:'#d9e2ea', 'stroke-dasharray':'5 6'}));
        }
        root.appendChild(svg('text', {x: left - 8, y: y + 15, 'text-anchor':'end', 'font-size':'12', fill:'#344054'})).textContent = cleanName(r['门店名称']);
        [['wow_net_revenue_pct', colors.green, 0], ['yoy_net_revenue_pct', colors.blue, 23]].forEach(([field, color, off]) => {
          const v = Number(r[field] || 0);
          const bw = Math.abs(v) / max * 360;
          const x = v >= 0 ? mid : mid - bw;
          root.appendChild(svg('rect', {x, y:y+off, width:bw, height:16, rx:3, fill:color}));
          root.appendChild(svg('text', {x: v >= 0 ? x + bw + 7 : x - 7, y:y+off+12, 'text-anchor': v >= 0 ? 'start':'end', 'font-size':'12', fill:'#657386'})).textContent = fmtPct(v);
        });
      });
      el.innerHTML = '';
      el.appendChild(root);
    }
    function renderScatter() {
      const el = document.getElementById('scatter');
      const w = 760, h = 330, left = 60, right = 30, top = 30, bottom = 46;
      const xs = stores.map(r => Number(r.wow_net_revenue_pct || 0));
      const ys = stores.map(r => Number(r.current_net_revenue || 0));
      const minX = Math.min(...xs, -0.01), maxX = Math.max(...xs, 0.01), maxY = Math.max(...ys, 1);
      const revenueThreshold = Number(data.segment_rules.revenue_threshold || 0);
      const growthThreshold = Number(data.segment_rules.growth_threshold || 0);
      const xScale = v => left + (v - minX) / (maxX - minX || 1) * (w-left-right);
      const yScale = v => h - bottom - v / maxY * (h-top-bottom);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      root.appendChild(svg('line', {x1:left, y1:h-bottom, x2:w-right, y2:h-bottom, stroke:'#9aa7b5'}));
      root.appendChild(svg('line', {x1:left, y1:top, x2:left, y2:h-bottom, stroke:'#9aa7b5'}));
      root.appendChild(svg('line', {x1:xScale(growthThreshold), y1:top, x2:xScale(growthThreshold), y2:h-bottom, stroke:'#cfd9e3', 'stroke-dasharray':'5 5'}));
      root.appendChild(svg('line', {x1:left, y1:yScale(revenueThreshold), x2:w-right, y2:yScale(revenueThreshold), stroke:'#cfd9e3', 'stroke-dasharray':'5 5'}));
      [
        ['高基盘承压', left + 12, top + 18, colors.amber],
        ['明星门店', Math.min(w - right - 90, xScale(growthThreshold) + 12), top + 18, colors.green],
        ['问题门店', left + 12, h - bottom - 14, colors.red],
        ['成长观察', Math.min(w - right - 90, xScale(growthThreshold) + 12), h - bottom - 14, colors.blue]
      ].forEach(([label, x, y, color]) => {
        root.appendChild(svg('text', {x, y, 'font-size':'11', fill:color, 'font-weight':'800', opacity:.78})).textContent = label;
      });
      const placedLabels = [];
      stores.forEach(r => {
        const seg = r.segment;
        const fill = seg === '明星门店' ? colors.green : seg === '问题门店' ? colors.red : seg === '高基盘承压' ? colors.amber : colors.blue;
        const radius = 7 + Math.min(12, Number(r.current_discount_rate || 0) * 35);
        const cx = xScale(Number(r.wow_net_revenue_pct || 0));
        const cy = yScale(Number(r.current_net_revenue || 0));
        root.appendChild(svg('circle', {cx, cy, r:radius, fill, opacity:.82}));
        let anchor = 'start';
        let lx = cx + radius + 4;
        let ly = cy + 4;
        if (cx > w - right - 90) {
          anchor = 'end';
          lx = cx - radius - 4;
        }
        let guard = 0;
        while (placedLabels.some(p => Math.abs(p.x - lx) < 92 && Math.abs(p.y - ly) < 15) && guard < 8) {
          ly += 15;
          if (ly > h - bottom - 8) ly = cy - 12 - guard * 10;
          guard += 1;
        }
        placedLabels.push({x: lx, y: ly});
        root.appendChild(svg('text', {x:lx, y:ly, 'text-anchor':anchor, 'font-size':'11', fill:'#344054', stroke:'#fff', 'stroke-width':3, 'paint-order':'stroke'})).textContent = cleanName(r['门店名称']);
      });
      root.appendChild(svg('text', {x:w/2, y:h-10, 'text-anchor':'middle', 'font-size':'12', fill:'#657386'})).textContent = '环比增长率';
      root.appendChild(svg('text', {x:16, y:20, 'font-size':'12', fill:'#657386'})).textContent = '业务收入';
      el.innerHTML = '';
      el.appendChild(root);
    }
    function currentTrendEntity() {
      const entities = data.trend_entities || [{key:'__all__', label:'全体门店', rows:data.trend}];
      return entities.find(item => item.key === selectedTrendKey) || entities[0];
    }
    function renderTrendSelector() {
      const select = document.getElementById('trendStoreSelect');
      const entities = data.trend_entities || [{key:'__all__', label:'全体门店', rows:data.trend}];
      select.innerHTML = entities.map(item => `<option value="${item.key}">${cleanName(item.label)}</option>`).join('');
      select.value = selectedTrendKey;
      select.addEventListener('change', () => {
        selectedTrendKey = select.value;
        renderTrend();
      });
    }
    function renderTrend() {
      const el = document.getElementById('trend');
      const entity = currentTrendEntity();
      const rows = entity.rows || [];
      const isAllStores = entity.key === '__all__';
      document.getElementById('trendMetricLabel').textContent = `完整周，${isAllStores ? '整体' : cleanName(entity.label)}业务收入（万元）；实线=${currentTrendYear}，虚线=${yoyTrendYear}同期`;
      const w = 1120, h = 360, left = 82, right = 84, top = 34, bottom = 78;
      const hasComparisonShape = rows.some(r => Object.prototype.hasOwnProperty.call(r, 'current_net_revenue') || Object.prototype.hasOwnProperty.call(r, 'prior_net_revenue'));
      const currentField = hasComparisonShape ? 'current_net_revenue' : 'net_revenue';
      const priorField = 'prior_net_revenue';
      const allValues = rows.flatMap(r => [Number(r[currentField] || 0), Number(r[priorField] || 0)]);
      const max = Math.max(...allValues, 1);
      const yMax = Math.ceil(max / 500000) * 500000;
      const yScale = v => h - bottom - Number(v || 0) / yMax * (h-top-bottom);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      const tip = document.createElement('div');
      tip.className = 'chart-tooltip';
      const showTrendTip = (event, seriesLabel, weekLabel, weekRange, value) => {
        const bounds = el.getBoundingClientRect();
        tip.innerHTML = `<strong>${seriesLabel}</strong>${weekRange || weekLabel}<br>业务收入：${fmtWan(value)}`;
        tip.style.left = `${event.clientX - bounds.left + 12}px`;
        tip.style.top = `${event.clientY - bounds.top - 14}px`;
        tip.style.display = 'block';
      };
      const hideTrendTip = () => { tip.style.display = 'none'; };
      [0, .25, .5, .75, 1].forEach(t => {
        const value = yMax * t;
        const y = yScale(value);
        root.appendChild(svg('line', {x1:left, y1:y, x2:w-right, y2:y, stroke:'#e6edf3'}));
        root.appendChild(svg('text', {x:left-10, y:y+4, 'text-anchor':'end', 'font-size':'11', fill:'#657386'})).textContent = fmtWan(value);
      });
      root.appendChild(svg('line', {x1:left, y1:top, x2:left, y2:h-bottom, stroke:'#9aa7b5'}));
      root.appendChild(svg('line', {x1:left, y1:h-bottom, x2:w-right, y2:h-bottom, stroke:'#9aa7b5'}));

      function trendPoints(field) {
        return rows.map((r,i) => {
          const raw = r[field];
          if (raw === null || raw === undefined || raw === '') return null;
          const x = left + i / Math.max(1, rows.length - 1) * (w-left-right);
          const y = yScale(Number(raw || 0));
          return [x,y,r,Number(raw || 0),i];
        }).filter(Boolean);
      }
      function drawTrendLine(field, color, dash, seriesLabel, rangeField) {
        const points = trendPoints(field);
        if (!points.length) return;
        root.appendChild(svg('polyline', {
          points: points.map(p=>`${p[0]},${p[1]}`).join(' '),
          fill: 'none',
          stroke: color,
          'stroke-width': 3,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          ...(dash ? {'stroke-dasharray': dash} : {})
        }));
        points.forEach(([x,y,r,value], i) => {
          const point = svg('circle', {cx:x, cy:y, r:5, fill:'#fff', stroke:color, 'stroke-width':2, style:'cursor:pointer'});
          const weekLabel = String(r.week_label || '');
          const weekRange = String(r[rangeField] || '');
          const title = svg('title', {});
          title.textContent = `${seriesLabel} ${weekRange || weekLabel} 业务收入：${fmtWan(value)}`;
          point.appendChild(title);
          point.addEventListener('mousemove', event => showTrendTip(event, seriesLabel, weekLabel, weekRange, value));
          point.addEventListener('mouseleave', hideTrendTip);
          point.addEventListener('focus', event => showTrendTip(event, seriesLabel, weekLabel, weekRange, value));
          point.addEventListener('blur', hideTrendTip);
          root.appendChild(point);
          if (i === points.length - 1) {
            const labelY = field === priorField ? y + 19 : y - 9;
            root.appendChild(svg('text', {x:x-7, y:labelY, 'text-anchor':'end', 'font-size':'11', fill:color, 'font-weight':'800'})).textContent = fmtWan(value);
          }
        });
      }
      drawTrendLine(currentField, colors.teal, '', currentTrendYear, hasComparisonShape ? 'current_week_range' : 'week_label');
      if (hasComparisonShape) drawTrendLine(priorField, colors.amber, '7 5', `${yoyTrendYear}同期`, 'prior_week_range');

      rows.forEach((r, i) => {
        const x = left + i / Math.max(1, rows.length - 1) * (w-left-right);
        if (i % 2 === 0 || i === rows.length - 1) {
          const anchor = i === rows.length - 1 ? 'end' : 'middle';
          const tx = i === rows.length - 1 ? x - 4 : x;
          root.appendChild(svg('text', {x:tx, y:h-42, 'text-anchor':anchor, 'font-size':'10', fill:'#657386', transform:`rotate(-32 ${tx} ${h-42})`})).textContent = String(r.week_label).slice(5);
        }
      });
      root.appendChild(svg('line', {x1:left+190, y1:15, x2:left+232, y2:15, stroke:colors.teal, 'stroke-width':3, 'stroke-linecap':'round'}));
      root.appendChild(svg('text', {x:left+240, y:19, 'font-size':'11', fill:'#657386'})).textContent = currentTrendYear;
      if (hasComparisonShape) {
        root.appendChild(svg('line', {x1:left+292, y1:15, x2:left+334, y2:15, stroke:colors.amber, 'stroke-width':3, 'stroke-dasharray':'7 5', 'stroke-linecap':'round'}));
        root.appendChild(svg('text', {x:left+342, y:19, 'font-size':'11', fill:'#657386'})).textContent = `${yoyTrendYear}同期`;
      }
      root.appendChild(svg('text', {x:left, y:18, 'font-size':'12', fill:'#657386', 'font-weight':'700'})).textContent = '业务收入（万元）';
      root.appendChild(svg('text', {x:w-right, y:18, 'text-anchor':'end', 'font-size':'11', fill:'#657386'})).textContent = data.trend_note || '';
      el.innerHTML = '';
      el.appendChild(root);
      el.appendChild(tip);
    }
    function renderMixBars() {
      const rows = stores;
      const el = document.getElementById('mixBar');
      const w = 760, h = Math.max(310, rows.length * 32 + 46), left = 150, right = 70;
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      const max = Math.max(...rows.map(r => Number(r.current_net_revenue || 0)), 1);
      rows.forEach((r,i) => {
        const y = 26 + i * 32;
        const total = Number(r.current_net_revenue || 0);
        const dine = Number(r.current_dine_in_revenue || 0);
        const del = Number(r.current_delivery_revenue || 0);
        const other = Math.max(0, total - dine - del);
        let x = left;
        root.appendChild(svg('text', {x:left-8, y:y+15, 'text-anchor':'end', 'font-size':'12', fill:'#344054'})).textContent = cleanName(r['门店名称']);
        [[dine, colors.teal], [del, colors.blue], [other, colors.amber]].forEach(([v,c]) => {
          const bw = v / max * (w-left-right);
          root.appendChild(svg('rect', {x, y, width:bw, height:18, rx:2, fill:c}));
          x += bw;
        });
        root.appendChild(svg('text', {x:left + total/max*(w-left-right) + 8, y:y+14, 'font-size':'12', fill:'#657386'})).textContent = fmtWan(total);
      });
      el.innerHTML = '';
      el.appendChild(root);
    }
    function renderPlatformBars() {
      const rows = stores;
      const el = document.getElementById('platformBar');
      const w = 760, h = Math.max(310, rows.length * 32 + 46), left = 150, right = 70;
      const max = Math.max(...rows.map(r => Number(r.current_meituan_delivery_revenue||0)+Number(r.current_eleme_delivery_revenue||0)+Number(r.current_jd_delivery_revenue||0)), 1);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      rows.forEach((r,i) => {
        const y = 26 + i * 32;
        const vals = [[Number(r.current_meituan_delivery_revenue||0), colors.green], [Number(r.current_eleme_delivery_revenue||0), colors.violet], [Number(r.current_jd_delivery_revenue||0), colors.orange]];
        let x = left, total = vals.reduce((s,v)=>s+v[0],0);
        root.appendChild(svg('text', {x:left-8, y:y+15, 'text-anchor':'end', 'font-size':'12', fill:'#344054'})).textContent = cleanName(r['门店名称']);
        vals.forEach(([v,c]) => { const bw = v / max * (w-left-right); root.appendChild(svg('rect', {x, y, width:bw, height:18, rx:2, fill:c})); x += bw; });
        root.appendChild(svg('text', {x:left + total/max*(w-left-right) + 8, y:y+14, 'font-size':'12', fill:'#657386'})).textContent = fmtWan(total);
      });
      el.innerHTML = '';
      el.appendChild(root);
    }
    function renderDriverBar() {
      const problemStores = stores.filter(r => r.segment === '问题门店').slice(0, 6);
      const rows = problemStores.length ? problemStores : stores.slice(-6);
      const el = document.getElementById('driverBar');
      const w = 1120, h = Math.max(430, rows.length * 76 + 92), left = 180, mid = 575, right = 120;
      const vals = rows.flatMap(r => [Number(r.wow_order_volume_contribution||0), Number(r.wow_aov_contribution||0), Number(r.wow_dine_in_delta||0), Number(r.wow_delivery_delta||0)]);
      const max = Math.max(...vals.map(v=>Math.abs(v)), 1);
      const root = svg('svg', {viewBox:`0 0 ${w} ${h}`});
      [['量贡献', colors.blue, 0], ['价贡献', colors.teal, 72], ['堂食变化', colors.green, 144], ['外卖变化', colors.amber, 232]].forEach(([label, color, xOff]) => {
        root.appendChild(svg('rect', {x: left + xOff, y: 16, width: 12, height: 12, rx: 2, fill: color}));
        root.appendChild(svg('text', {x: left + xOff + 18, y: 27, 'font-size':'12', fill:'#657386'})).textContent = label;
      });
      root.appendChild(svg('line', {x1:mid, y1:46, x2:mid, y2:h-26, stroke:'#d9e2ea'}));
      rows.forEach((r,i) => {
        const y = 62 + i * 76;
        if (i > 0) {
          root.appendChild(svg('line', {x1: left, y1: y - 14, x2: w - right, y2: y - 14, stroke:'#d9e2ea', 'stroke-dasharray':'5 6'}));
        }
        root.appendChild(svg('text', {x:left-8, y:y+25, 'text-anchor':'end', 'font-size':'12', fill:'#344054'})).textContent = cleanName(r['门店名称']);
        [[Number(r.wow_order_volume_contribution||0), colors.blue, 0], [Number(r.wow_aov_contribution||0), colors.teal, 16], [Number(r.wow_dine_in_delta||0), colors.green, 32], [Number(r.wow_delivery_delta||0), colors.amber, 48]].forEach(([v,c,off]) => {
          const bw = Math.abs(v) / max * 360;
          const x = v >= 0 ? mid : mid - bw;
          root.appendChild(svg('rect', {x, y:y+off, width:bw, height:12, rx:2, fill:c, opacity:.9}));
          root.appendChild(svg('text', {x: v >= 0 ? x + bw + 7 : x - 7, y:y+off+10, 'text-anchor': v >= 0 ? 'start':'end', 'font-size':'11', fill:'#657386'})).textContent = fmtWan(v);
        });
      });
      el.innerHTML = '';
      el.appendChild(root);
    }
    function renderTable() {
      const body = document.querySelector('#storeTable tbody');
      const tagClass = segment => segment === '明星门店' ? 'star' : segment === '问题门店' ? 'problem' : segment === '高基盘承压' ? 'pressure' : segment === '成长观察' ? 'growth' : '';
      const rows = stores.map(r => `<tr>
        <td>${cleanName(r['门店名称'])}</td>
        <td><span class="tag ${tagClass(r.segment)}">${r.segment}</span></td>
        <td>${fmtWan(r.current_net_revenue)}</td>
        <td>${fmtPct(r.wow_net_revenue_pct)}</td>
        <td>${fmtPct(r.yoy_net_revenue_pct)}</td>
        <td>${fmtWan(r.current_dine_in_revenue)}</td>
        <td>${fmtWan(r.current_delivery_revenue)}</td>
        <td>${fmtNum(r.current_customer_count)}</td>
        <td>${fmtNum(r.current_consumed_tables)}</td>
        <td>${fmtYuan(r.current_post_discount_aov)}</td>
        <td>${fmtPct(r.current_discount_rate)}</td>
        <td>${r.top_negative_factor || r.segment_reason || ''}</td>
      </tr>`).join('');
      body.innerHTML = rows;
      document.querySelectorAll('#storeTable th[data-key]').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.key;
          stores.sort((a,b) => {
            const av = a[key], bv = b[key];
            const na = Number(av), nb = Number(bv);
            if (!Number.isNaN(na) && !Number.isNaN(nb)) return nb - na;
            return String(av || '').localeCompare(String(bv || ''), 'zh-CN');
          });
          renderTable();
        });
      });
    }
    function renderActions() {
      const groups = {};
      stores.forEach(r => { groups[r.segment] = groups[r.segment] || []; groups[r.segment].push(cleanName(r['门店名称'])); });
      const hint = k => k === '明星门店' ? '沉淀可复制打法' : k === '问题门店' ? '优先复盘负向因素' : k === '高基盘承压' ? '防止高收入门店继续滑坡' : '验证增长是否可持续';
      document.getElementById('actionList').innerHTML = Object.entries(groups).map(([k, arr]) => `<div class="card" style="margin-bottom:10px; min-height:0;"><div class="label">${k}</div><div style="margin-top:8px;">${arr.join('、')}</div><div class="foot">${hint(k)}</div></div>`).join('');
    }
    function renderHeatmap() {
      const rows = data.dayparts.filter(r => r.period === '本周');
      const periods = [...new Set(rows.map(r => r['餐段']))];
      const hours = Array.from({length:24}, (_,i)=>String(i).padStart(2,'0'));
      const max = Math.max(...rows.map(r => Number(r.net_revenue || 0)), 1);
      const byKey = new Map(rows.map(r => [`${r['餐段']}|${String(r['时段']).slice(0,2)}`, Number(r.net_revenue || 0)]));
      document.getElementById('heatmap').innerHTML = [`<div class="heat-row"><div></div>${hours.map(h=>`<div class="label" style="text-align:center;">${h}</div>`).join('')}</div>`].concat(periods.map(p => `<div class="heat-row"><div class="heat-label">${p}</div>${hours.map(h => {
        const v = byKey.get(`${p}|${h}`) || 0;
        const alpha = .08 + Math.min(.82, v / max * .82);
        return `<div class="heat-cell" data-tip="${p} ${h}:00 ${fmtWan(v)}" style="background:rgba(0,109,119,${alpha})"></div>`;
      }).join('')}</div>`)).join('');
    }
    function renderGaps() {
      document.getElementById('dataGaps').innerHTML = `<b>数据未覆盖：</b>${data.data_gaps.join('；')}`;
    }
    renderMeta();
    renderKpis();
    renderRules();
    renderHorizontalBar('revenueBar', stores, 'current_net_revenue', fmtWan, colors.teal);
    renderGrowthBar();
    renderScatter();
    renderTrendSelector();
    renderTrend();
    renderTable();
    renderMixBars();
    renderPlatformBars();
    renderDriverBar();
    renderActions();
    renderHeatmap();
    renderGaps();
  </script>
</body>
</html>
'''


def generate(input_dir: Path, output: Path, company: str) -> None:
    payload = build_payload(input_dir, company)
    html = HTML_TEMPLATE.replace("__TITLE__", payload["meta"]["title"])
    html = html.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    args = parser.parse_args()
    generate(args.input_dir, args.output, args.company)


if __name__ == "__main__":
    main()
