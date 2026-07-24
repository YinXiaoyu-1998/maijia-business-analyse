#!/usr/bin/env python3
"""Stream-profile Meituan exports into monthly meeting fact tables."""

from __future__ import annotations

import argparse
import json
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from profile_weekly_meeting_data import (
    METRIC_FIELDS,
    add_to_agg,
    classify_stores,
    compare_store_dayparts,
    date_text,
    diff,
    driver_pair,
    export_group,
    build_dine_in_revenue_map,
    inspect_workbook,
    parse_date,
    profile_dish_sales_mix,
    progress,
    read_workbook_sheet_rows,
    row_dict,
    safe_float,
    short_path,
    store_daypart_driver_rows,
    store_key,
    target_period_for,
    write_csv,
    new_agg,
    DAYPART_DRIVER_SUMMARY_FIELDS,
    PROGRESS_ROW_INTERVAL,
)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def month_label(value: date) -> str:
    return value.strftime("%Y/%m")


def default_target_windows(today: date | None = None) -> dict[str, tuple[str, date, date]]:
    anchor = month_start(today or date.today())
    previous = add_months(anchor, -1)
    yoy = add_months(anchor, -12)
    return {
        "current": ("本月", anchor, month_end(anchor)),
        "previous": ("上月", previous, month_end(previous)),
        "yoy": ("去年同月", yoy, month_end(yoy)),
    }


def build_month_trend_windows(
    target_windows: dict[str, tuple[str, date, date]],
    month_count: int = 6,
) -> list[tuple[str, str, int, date, date]]:
    current_anchor = month_start(target_windows["current"][1])
    prior_anchor = add_months(current_anchor, -12)
    windows: list[tuple[str, str, int, date, date]] = []
    for index in range(month_count):
        current_start = add_months(current_anchor, -(month_count - index - 1))
        prior_start = add_months(prior_anchor, -(month_count - index - 1))
        windows.append(("prior_year", f"{prior_start:%Y}同期", index + 1, prior_start, month_end(prior_start)))
        windows.append(("current_year", f"{current_start:%Y}", index + 1, current_start, month_end(current_start)))
    return windows


def trend_window_for(
    value: date,
    trend_windows: list[tuple[str, str, int, date, date]],
) -> tuple[str, str, int, date, date] | None:
    for series_key, series_label, window_index, start, end in trend_windows:
        if start <= value <= end:
            return series_key, series_label, window_index, start, end
    return None


def profile(
    inputs: list[Path],
    output_dir: Path,
    target_windows: dict[str, tuple[str, date, date]],
    dish_inputs: list[Path] | None = None,
    catalog_path: Path | None = None,
    trend_months: int = 6,
) -> dict[str, Any]:
    progress(f"开始月报 profiling: business_inputs={len(inputs)}, dish_inputs={len(dish_inputs or [])}, trend_months={trend_months}")
    inspections = []
    for index, path in enumerate(inputs, start=1):
        progress(f"检查业务输入 {index}/{len(inputs)}: {short_path(path)}")
        info = inspect_workbook(path)
        inspections.append(info)
        progress(
            f"业务输入 {index}/{len(inputs)} 覆盖: "
            f"{date_text(info['min_date']) if info['min_date'] else '未知'}-"
            f"{date_text(info['max_date']) if info['max_date'] else '未知'}"
        )
    trend_windows = build_month_trend_windows(target_windows, trend_months)
    later_dates: list[set[date]] = []
    union_later: set[date] = set()
    for info in reversed(inspections):
        later_dates.append(set(union_later))
        union_later.update(info["dates"])
    later_dates = list(reversed(later_dates))

    monthly_store: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    monthly_store_channel: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    monthly_store_daypart: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    target_store_period: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    trend_comparison_store: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    processed_dates: set[date] = set()
    skipped_duplicate_rows = 0
    skipped_summary_rows = 0
    processed_rows = 0

    for index, path in enumerate(inputs):
        progress(f"扫描业务输入 {index + 1}/{len(inputs)}: {short_path(path)}")
        excluded_dates = later_dates[index]
        headers: list[str] = []
        current_sheet = ""
        sheet_title = ""
        file_processed_rows = 0
        file_min_date: date | None = None
        file_max_date: date | None = None
        for sheet, row_number, values in read_workbook_sheet_rows(path):
            if sheet["path"] != current_sheet:
                current_sheet = sheet["path"]
                sheet_title = ""
                headers = []
            if row_number == 1:
                sheet_title = values.get(1, "")
                continue
            if sheet_title != "营业分组表":
                continue
            if row_number == 3:
                headers = [values.get(col, "") for col in range(1, max(values) + 1)]
                continue
            if row_number < 4 or not headers or not values:
                continue

            row = row_dict(headers, values)
            parsed_date = parse_date(row.get("营业日期", ""))
            if not parsed_date:
                if str(row.get("营业日期", "")).strip() == "合计":
                    skipped_summary_rows += 1
                continue
            if parsed_date in excluded_dates:
                skipped_duplicate_rows += 1
                continue

            key_store = store_key(row)
            if key_store[0] == "未知门店":
                continue

            start = month_start(parsed_date)
            end = month_end(parsed_date)
            period_key = target_period_for(parsed_date, target_windows)
            trend_window = trend_window_for(parsed_date, trend_windows)
            processed_dates.add(parsed_date)
            processed_rows += 1
            file_processed_rows += 1
            file_min_date = parsed_date if file_min_date is None else min(file_min_date, parsed_date)
            file_max_date = parsed_date if file_max_date is None else max(file_max_date, parsed_date)

            monthly_key = (date_text(start), date_text(end), month_label(start)) + key_store
            add_to_agg(monthly_store[monthly_key], row, parsed_date)

            if period_key:
                period_label = target_windows[period_key][0]
                add_to_agg(target_store_period[(period_key, period_label) + key_store], row, parsed_date)
                for channel_name in ["店内", "外卖", "美团外卖", "饿了么外卖", "京东外卖"]:
                    channel_row = dict(row)
                    if channel_name == "店内":
                        channel_row["营业额(元)"] = row.get("店内营业额", "")
                        channel_row["订单营业收入"] = row.get("店内营业收入", "")
                        channel_row["优惠金额"] = row.get("店内优惠金额", "")
                        channel_row["正向订单量"] = row.get("店内正向单订单量", "")
                    elif channel_name == "外卖":
                        channel_row["营业额(元)"] = row.get("外卖营业额", "")
                        channel_row["订单营业收入"] = row.get("外卖营业收入", "")
                        channel_row["优惠金额"] = row.get("外卖折扣金额", "")
                        channel_row["正向订单量"] = row.get("外卖正向单订单量", "")
                    elif channel_name == "美团外卖":
                        channel_row["营业额(元)"] = row.get("美团外卖营业额", "")
                        channel_row["订单营业收入"] = row.get("美团外卖营业收入", "")
                        channel_row["优惠金额"] = row.get("美团外卖折扣金额", "")
                        channel_row["正向订单量"] = row.get("美团外卖正向单订单量", "")
                    elif channel_name == "饿了么外卖":
                        channel_row["营业额(元)"] = row.get("饿了么外卖营业额", "")
                        channel_row["订单营业收入"] = row.get("饿了么外卖营业收入", "")
                        channel_row["优惠金额"] = row.get("饿了么外卖折扣金额", "")
                        channel_row["正向订单量"] = row.get("饿了么外卖正向单订单量", "")
                    elif channel_name == "京东外卖":
                        channel_row["营业额(元)"] = row.get("京东外卖营业额", "")
                        channel_row["订单营业收入"] = row.get("京东外卖营业收入", "")
                        channel_row["优惠金额"] = row.get("京东外卖折扣金额", "")
                        channel_row["正向订单量"] = row.get("京东外卖正向单订单量", "")
                    if safe_float(channel_row.get("订单营业收入")) or safe_float(channel_row.get("营业额(元)")):
                        add_to_agg(monthly_store_channel[monthly_key + (period_label, channel_name)], channel_row, parsed_date)

                daypart = row.get("餐段", "") or "未知餐段"
                hour = row.get("时段", "") or "未知时段"
                add_to_agg(monthly_store_daypart[monthly_key + (period_label, daypart, hour)], row, parsed_date)

            if trend_window:
                series_key, series_label, window_index, trend_start, trend_end = trend_window
                trend_key = (
                    series_key,
                    series_label,
                    window_index,
                    date_text(trend_start),
                    date_text(trend_end),
                    month_label(trend_start),
                ) + key_store
                add_to_agg(trend_comparison_store[trend_key], row, parsed_date)
            if file_processed_rows % PROGRESS_ROW_INTERVAL == 0:
                progress(
                    f"业务输入 {index + 1}/{len(inputs)} 已纳入 {file_processed_rows:,} 行，"
                    f"累计 {processed_rows:,} 行。"
                )
        progress(
            f"完成业务输入 {index + 1}/{len(inputs)}: 纳入 {file_processed_rows:,} 行，"
            f"日期 {date_text(file_min_date) if file_min_date else '无'}-"
            f"{date_text(file_max_date) if file_max_date else '无'}。"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    progress("导出月级、渠道、时段基础事实表。")
    monthly_rows = export_group(monthly_store, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号"])
    channel_rows = export_group(monthly_store_channel, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号", "period", "channel"])
    daypart_rows = export_group(monthly_store_daypart, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号", "period", "餐段", "时段"])
    target_rows = export_group(target_store_period, ["period_key", "period_label", "门店名称", "城市", "商户号"])
    trend_comparison_rows = export_group(
        trend_comparison_store,
        ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称", "城市", "商户号"],
    )

    by_store_period = {
        (row["门店名称"], row["period_key"]): row
        for row in target_rows
    }
    stores = sorted({row["门店名称"] for row in target_rows})
    progress(f"计算门店对比和经营归因: stores={len(stores)}")
    comparison_rows: list[dict[str, Any]] = []
    driver_rows: list[dict[str, Any]] = []
    for store in stores:
        current = by_store_period.get((store, "current"))
        previous = by_store_period.get((store, "previous"))
        yoy = by_store_period.get((store, "yoy"))
        row: dict[str, Any] = {"门店名称": store}
        for label, source in [("current", current), ("previous", previous), ("yoy", yoy)]:
            for field in METRIC_FIELDS:
                row[f"{label}_{field}"] = source.get(field) if source else None
        for field in [
            "net_revenue",
            "gross_sales",
            "dine_in_revenue",
            "delivery_revenue",
            "customer_count",
            "consumed_tables",
            "table_uses",
            "post_discount_aov",
            "discount_rate",
            "open_rate",
            "turnover_rate",
        ]:
            wow_delta, wow_pct = diff(current, previous, field)
            yoy_delta, yoy_pct = diff(current, yoy, field)
            row[f"wow_{field}_delta"] = wow_delta
            row[f"wow_{field}_pct"] = wow_pct
            row[f"yoy_{field}_delta"] = yoy_delta
            row[f"yoy_{field}_pct"] = yoy_pct
        comparison_rows.append(row)
        driver_rows.append(driver_pair(store, "环比", current, previous))
        driver_rows.append(driver_pair(store, "同比", current, yoy))

    star_rows = classify_stores(comparison_rows)
    for row in star_rows:
        if isinstance(row.get("reason"), str):
            row["reason"] = row["reason"].replace("本周", "本月")
    progress("计算时段归因。")
    daypart_comparison_rows = compare_store_dayparts(daypart_rows, target_windows)
    daypart_driver_rows = store_daypart_driver_rows(daypart_comparison_rows)
    dish_sales_mix_meta = profile_dish_sales_mix(
        dish_inputs,
        output_dir,
        target_windows,
        build_dine_in_revenue_map(target_rows),
        output_prefix="monthly",
    )

    progress("写出月报事实表 CSV。")
    write_csv(output_dir / "monthly_store_metrics.csv", monthly_rows, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_channel_metrics.csv", channel_rows, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号", "period", "channel"] + METRIC_FIELDS)
    write_csv(output_dir / "monthly_store_daypart_metrics.csv", daypart_rows, ["month_start", "month_end", "month_label", "门店名称", "城市", "商户号", "period", "餐段", "时段"] + METRIC_FIELDS)
    daypart_comparison_fields = ["门店名称", "餐段", "时段"]
    for prefix in ["current", "previous", "yoy"]:
        daypart_comparison_fields.extend([f"{prefix}_{field}" for field in METRIC_FIELDS])
    for prefix in ["wow", "yoy"]:
        for field in ["net_revenue", "gross_sales", "positive_orders", "customer_count", "dine_in_revenue", "delivery_revenue", "discount_amount"]:
            daypart_comparison_fields.extend([f"{prefix}_{field}_delta", f"{prefix}_{field}_pct"])
    write_csv(output_dir / "monthly_store_daypart_comparison.csv", daypart_comparison_rows, daypart_comparison_fields)
    write_csv(output_dir / "monthly_store_daypart_driver_summary.csv", daypart_driver_rows, DAYPART_DRIVER_SUMMARY_FIELDS)
    write_csv(
        output_dir / "monthly_trend_comparison_metrics.csv",
        trend_comparison_rows,
        ["series_key", "series_label", "window_index", "month_start", "month_end", "month_label", "门店名称", "城市", "商户号"] + METRIC_FIELDS,
    )

    comparison_fields = ["门店名称"]
    for prefix in ["current", "previous", "yoy"]:
        comparison_fields.extend([f"{prefix}_{field}" for field in METRIC_FIELDS])
    for prefix in ["wow", "yoy"]:
        for field in ["net_revenue", "gross_sales", "dine_in_revenue", "delivery_revenue", "customer_count", "consumed_tables", "table_uses", "post_discount_aov", "discount_rate", "open_rate", "turnover_rate"]:
            comparison_fields.extend([f"{prefix}_{field}_delta", f"{prefix}_{field}_pct"])
    write_csv(output_dir / "monthly_store_comparison.csv", comparison_rows, comparison_fields)
    write_csv(output_dir / "store_driver_summary.csv", driver_rows, list(driver_rows[0].keys()) if driver_rows else [])
    write_csv(output_dir / "star_problem_stores.csv", star_rows, list(star_rows[0].keys()) if star_rows else [])

    progress("写出月报 summary JSON。")
    summary = {
        "meta": {
            "report_grain": "month",
            "trend_months": trend_months,
            "inputs": [
                {
                    "path": info["path"],
                    "title": info["title"],
                    "sheet_count": info["sheet_count"],
                    "header_count": info["header_count"],
                    "min_date": date_text(info["min_date"]) if info["min_date"] else None,
                    "max_date": date_text(info["max_date"]) if info["max_date"] else None,
                }
                for info in inspections
            ],
            "coverage_start": date_text(min(processed_dates)) if processed_dates else None,
            "coverage_end": date_text(max(processed_dates)) if processed_dates else None,
            "target_windows": {
                key: {"label": label, "start": date_text(start), "end": date_text(end)}
                for key, (label, start, end) in target_windows.items()
            },
            "processed_rows": processed_rows,
            "skipped_duplicate_rows": skipped_duplicate_rows,
            "skipped_summary_rows": skipped_summary_rows,
            "store_count": len(stores),
            "outputs": [
                "monthly_store_metrics.csv",
                "monthly_store_channel_metrics.csv",
                "monthly_store_daypart_metrics.csv",
                "monthly_store_daypart_comparison.csv",
                "monthly_store_daypart_driver_summary.csv",
                *dish_sales_mix_meta.get("outputs", []),
                "monthly_trend_comparison_metrics.csv",
                "monthly_store_comparison.csv",
                "store_driver_summary.csv",
                "star_problem_stores.csv",
                "monthly_meeting_summary.json",
            ],
            "daypart_attribution": {
                "enabled": True,
                "basis": "营业分组表「时段」字段；按门店、餐段、时段汇总订单营业收入后比较本月、上月、去年同月。",
                "outputs": [
                    "monthly_store_daypart_comparison.csv",
                    "monthly_store_daypart_driver_summary.csv",
                ],
            },
            "dish_sales_mix": dish_sales_mix_meta,
        },
        "comparison": comparison_rows,
        "drivers": driver_rows,
        "store_segments": star_rows,
        "channel_current": [row for row in channel_rows if row.get("period") == "本月"],
        "daypart_current_previous": [row for row in daypart_rows if row.get("period") in {"本月", "上月"}],
        "monthly_trend": monthly_rows,
        "monthly_trend_comparison": trend_comparison_rows,
        "data_gaps": [
            "当前营业分组表没有网评分数、评论文本字段，不能做网评分数和词云分析。",
            "时段归因基于营业分组表「时段」字段，可定位收入变化发生在哪些时段；不直接解释菜品或现场运营原因。",
            *(
                [dish_sales_mix_meta.get("reason", "未提供菜品主题数据，未生成销售额菜品比例。")]
                if not dish_sales_mix_meta.get("enabled") else []
            ),
            *(
                ["已提供菜品库输入，但销售额菜品比例不需要菜品库；菜品库仅用于旧档口归因逻辑，本次已忽略。"]
                if catalog_path else []
            ),
        ],
    }
    (output_dir / "monthly_meeting_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(
        f"月报 profiling 完成: rows={processed_rows:,}, stores={len(stores)}, "
        f"coverage={date_text(min(processed_dates)) if processed_dates else '无'}-"
        f"{date_text(max(processed_dates)) if processed_dates else '无'}"
    )
    return summary


def main() -> None:
    defaults = default_target_windows()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, nargs="+", type=Path)
    parser.add_argument("--dish-input", nargs="+", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--current-start", type=parse_date, default=defaults["current"][1])
    parser.add_argument("--current-end", type=parse_date, default=defaults["current"][2])
    parser.add_argument("--previous-start", type=parse_date, default=defaults["previous"][1])
    parser.add_argument("--previous-end", type=parse_date, default=defaults["previous"][2])
    parser.add_argument("--yoy-start", type=parse_date, default=defaults["yoy"][1])
    parser.add_argument("--yoy-end", type=parse_date, default=defaults["yoy"][2])
    parser.add_argument("--trend-months", type=int, default=6)
    args = parser.parse_args()
    target_windows = {
        "current": ("本月", args.current_start, args.current_end),
        "previous": ("上月", args.previous_start, args.previous_end),
        "yoy": ("去年同月", args.yoy_start, args.yoy_end),
    }
    summary = profile(args.input, args.output_dir, target_windows, args.dish_input, args.catalog, args.trend_months)
    print(json.dumps({
        "coverage_start": summary["meta"]["coverage_start"],
        "coverage_end": summary["meta"]["coverage_end"],
        "processed_rows": summary["meta"]["processed_rows"],
        "skipped_duplicate_rows": summary["meta"]["skipped_duplicate_rows"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
