#!/usr/bin/env python3
"""Stream-profile Meituan exports into weekly meeting fact tables."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from xml.etree.ElementTree import iterparse
from zipfile import ZipFile


CELL_RE = re.compile(r"([A-Z]+)(\d+)")
DATE_RE = re.compile(r"^(\d{4}[/\-]\d{1,2}[/\-]\d{1,2}|\d{8})$")
EXPORT_RANGE_RE = re.compile(r"_(\d{8})_(\d{8})(?:_part\d+)?\.xlsx$")

DEFAULT_TARGET_WINDOWS = {
    "current": ("本周", date(2026, 6, 14), date(2026, 6, 20)),
    "previous": ("环比周", date(2026, 6, 7), date(2026, 6, 13)),
    "yoy": ("同比周", date(2025, 6, 15), date(2025, 6, 21)),
}

REQUIRED_COLUMNS = [
    "营业日期",
    "周",
    "月",
    "门店名称",
    "城市",
    "商户号",
    "订单分类",
    "订单来源",
    "时段",
    "餐段",
    "是否是会员",
    "就餐方式",
    "营业额(元)",
    "订单营业收入",
    "优惠金额",
    "正向订单量",
    "用餐人数",
    "店内营业收入",
    "店内正向单订单量",
    "外卖营业收入",
    "外卖正向单订单量",
    "消费桌数",
    "桌台使用次数",
    "开台率",
    "翻台率",
    "桌台数x营业天数",
]

DISH_REQUIRED_COLUMNS = [
    "营业日",
    "门店",
    "菜品名称",
    "订单分类",
    "菜品销售数量",
    "菜品销售额",
    "菜品收入",
    "菜品关联正向订单量",
]

ADD_FIELDS = {
    "gross_sales": "营业额(元)",
    "net_revenue": "订单营业收入",
    "discount_amount": "优惠金额",
    "valid_orders": "有效订单量",
    "reverse_orders": "逆向订单量",
    "positive_orders": "正向订单量",
    "settled_orders": "已结账订单量",
    "customer_count": "用餐人数",
    "consumed_tables": "消费桌数",
    "table_uses": "桌台使用次数",
    "table_count": "桌台数量",
    "table_days": "桌台数x营业天数",
    "dine_in_gross": "店内营业额",
    "dine_in_revenue": "店内营业收入",
    "dine_in_discount": "店内优惠金额",
    "dine_in_orders": "店内订单量",
    "dine_in_positive_orders": "店内正向单订单量",
    "dine_in_refund": "店内退款金额",
    "delivery_gross": "外卖营业额",
    "delivery_revenue": "外卖营业收入",
    "delivery_discount": "外卖折扣金额",
    "delivery_orders": "外卖订单量",
    "delivery_positive_orders": "外卖正向单订单量",
    "delivery_refund": "外卖退款金额",
    "meituan_delivery_revenue": "美团外卖营业收入",
    "eleme_delivery_revenue": "饿了么外卖营业收入",
    "jd_delivery_revenue": "京东外卖营业收入",
    "member_revenue": "会员订单收入",
}

METRIC_FIELDS = [
    "rows",
    "active_days",
    "gross_sales",
    "net_revenue",
    "discount_amount",
    "discount_rate",
    "positive_orders",
    "valid_orders",
    "settled_orders",
    "reverse_orders",
    "post_discount_aov",
    "customer_count",
    "revenue_per_customer",
    "consumed_tables",
    "table_uses",
    "revenue_per_table",
    "open_rate",
    "turnover_rate",
    "dine_in_revenue",
    "dine_in_positive_orders",
    "dine_in_aov",
    "delivery_revenue",
    "delivery_positive_orders",
    "delivery_aov",
    "delivery_revenue_share",
    "meituan_delivery_revenue",
    "eleme_delivery_revenue",
    "jd_delivery_revenue",
    "member_revenue",
    "member_revenue_share",
]

DISH_ADD_FIELDS = {
    "quantity": "菜品销售数量",
    "sales": "菜品销售额",
    "income": "菜品收入",
    "discount": "菜品优惠",
    "gross_sales": "菜品总销售额",
    "gross_income": "菜品总收入",
    "gross_discount": "菜品总优惠",
    "positive_orders": "菜品关联正向订单量",
    "refund_quantity": "退菜数量",
    "refund_amount": "退菜金额",
    "serving_orders": "出餐订单数",
    "gross_margin_after": "菜品总毛利额（折后）",
}

DISH_METRIC_FIELDS = [
    "rows",
    "active_days",
    "quantity",
    "sales",
    "income",
    "discount",
    "gross_sales",
    "gross_income",
    "gross_discount",
    "positive_orders",
    "refund_quantity",
    "refund_amount",
    "serving_orders",
    "gross_margin_after",
    "avg_income_per_item",
    "refund_rate_by_qty",
]

DISH_DRIVER_SUMMARY_FIELDS = [
    "门店名称",
    "basis",
    "top_negative_stall",
    "top_negative_income_delta",
    "top_negative_income_pct",
    "top_positive_stall",
    "top_positive_income_delta",
    "top_positive_income_pct",
    "stall_signal",
]

DISH_DRIVER_DETAIL_FIELDS = [
    "门店名称",
    "basis",
    "direction",
    "档口",
    "菜品名称",
    "channel",
    "current_income",
    "baseline_income",
    "income_delta",
    "income_pct",
    "current_quantity",
    "baseline_quantity",
    "quantity_delta",
]


def col_to_num(col: str) -> int:
    value = 0
    for char in col:
        value = value * 26 + ord(char.upper()) - 64
    return value


def is_tag(elem: Any, name: str) -> bool:
    return elem.tag == name or elem.tag.endswith("}" + name)


def load_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    strings: list[str] = []
    with zf.open("xl/sharedStrings.xml") as handle:
        for _, elem in iterparse(handle, events=("end",)):
            if is_tag(elem, "si"):
                strings.append(
                    "".join(
                        node.text or ""
                        for node in elem.iter()
                        if is_tag(node, "t") and node.text is not None
                    )
                )
                elem.clear()
    return strings


def cell_text(cell: Any, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or ""
            for node in cell.iter()
            if is_tag(node, "t") and node.text is not None
        )

    value = ""
    for child in cell.iter():
        if is_tag(child, "v"):
            value = child.text or ""
            break

    if cell_type == "s" and value:
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return value
    return value


def row_values(row: Any, shared_strings: list[str]) -> dict[int, str]:
    values: dict[int, str] = {}
    for cell in row.iter():
        if not is_tag(cell, "c"):
            continue
        match = CELL_RE.match(cell.attrib.get("r", ""))
        if not match:
            continue
        values[col_to_num(match.group(1))] = cell_text(cell, shared_strings)
    return values


def parse_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not DATE_RE.match(text):
        return None
    text = text.replace("-", "/")
    if "/" not in text and len(text) == 8:
        text = f"{text[:4]}/{text[4:6]}/{text[6:8]}"
    try:
        return datetime.strptime(text, "%Y/%m/%d").date()
    except ValueError:
        return None


def date_text(value: date) -> str:
    return value.strftime("%Y/%m/%d")


def week_start_sunday(value: date) -> date:
    return value - timedelta(days=(value.weekday() + 1) % 7)


def week_label(start: date) -> str:
    end = start + timedelta(days=6)
    return f"{date_text(start)}-{date_text(end)}"


def build_trend_comparison_windows(target_windows: dict[str, tuple[str, date, date]]) -> list[tuple[str, str, int, date, date]]:
    current_end = target_windows["current"][2]
    yoy_end = target_windows["yoy"][2]
    return [
        ("prior_year", f"{yoy_end:%Y}同期", index + 1, yoy_end - timedelta(days=(15 - index) * 7 + 6), yoy_end - timedelta(days=(15 - index) * 7))
        for index in range(16)
    ] + [
        ("current_year", f"{current_end:%Y}", index + 1, current_end - timedelta(days=(15 - index) * 7 + 6), current_end - timedelta(days=(15 - index) * 7))
        for index in range(16)
    ]


def target_period_for(value: date, target_windows: dict[str, tuple[str, date, date]]) -> str | None:
    for key, (_, start, end) in target_windows.items():
        if start <= value <= end:
            return key
    return None


def trend_comparison_window_for(value: date, trend_windows: list[tuple[str, str, int, date, date]]) -> tuple[str, str, int, date, date] | None:
    for series_key, series_label, window_index, start, end in trend_windows:
        if start <= value <= end:
            return series_key, series_label, window_index, start, end
    return None


def safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("元", "")
    if text in {"", "--", "null", "None", "合计"}:
        return 0.0
    if text.endswith("%"):
        text = text[:-1]
        try:
            return float(text) / 100
        except ValueError:
            return 0.0
    try:
        number = float(text)
    except ValueError:
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def safe_div(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or abs(baseline) < 1e-12:
        return None
    return (current - baseline) / baseline


def fmt(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def new_agg() -> dict[str, Any]:
    return {
        "rows": 0,
        "dates": set(),
        "sums": defaultdict(float),
        "open_weight": 0.0,
        "turnover_weight": 0.0,
    }


def normalize_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", text)


def strip_channel_prefix(value: Any) -> str:
    return re.sub(r"^【[^】]{1,12}】", "", normalize_name(value))


def add_to_agg(agg: dict[str, Any], row: dict[str, str], row_date: date) -> None:
    agg["rows"] += 1
    agg["dates"].add(row_date)
    sums = agg["sums"]
    for out_name, source_name in ADD_FIELDS.items():
        sums[out_name] += safe_float(row.get(source_name))
    table_days = safe_float(row.get("桌台数x营业天数"))
    if table_days > 0:
        agg["open_weight"] += safe_float(row.get("开台率")) * table_days
        agg["turnover_weight"] += safe_float(row.get("翻台率")) * table_days


def derive(agg: dict[str, Any]) -> dict[str, Any]:
    sums = agg["sums"]
    gross = sums["gross_sales"]
    revenue = sums["net_revenue"]
    positive_orders = sums["positive_orders"]
    dine_orders = sums["dine_in_positive_orders"]
    delivery_orders = sums["delivery_positive_orders"]
    customer_count = sums["customer_count"]
    consumed_tables = sums["consumed_tables"]
    table_days = sums["table_days"]
    return {
        "rows": agg["rows"],
        "active_days": len(agg["dates"]),
        "gross_sales": fmt(gross, 2),
        "net_revenue": fmt(revenue, 2),
        "discount_amount": fmt(sums["discount_amount"], 2),
        "discount_rate": fmt(safe_div(sums["discount_amount"], gross), 4),
        "positive_orders": fmt(positive_orders, 2),
        "valid_orders": fmt(sums["valid_orders"], 2),
        "settled_orders": fmt(sums["settled_orders"], 2),
        "reverse_orders": fmt(sums["reverse_orders"], 2),
        "post_discount_aov": fmt(safe_div(revenue, positive_orders), 2),
        "customer_count": fmt(customer_count, 2),
        "revenue_per_customer": fmt(safe_div(revenue, customer_count), 2),
        "consumed_tables": fmt(consumed_tables, 2),
        "table_uses": fmt(sums["table_uses"], 2),
        "revenue_per_table": fmt(safe_div(sums["dine_in_revenue"], consumed_tables), 2),
        "open_rate": fmt(safe_div(agg["open_weight"], table_days), 4),
        "turnover_rate": fmt(safe_div(agg["turnover_weight"], table_days), 4),
        "dine_in_revenue": fmt(sums["dine_in_revenue"], 2),
        "dine_in_positive_orders": fmt(dine_orders, 2),
        "dine_in_aov": fmt(safe_div(sums["dine_in_revenue"], dine_orders), 2),
        "delivery_revenue": fmt(sums["delivery_revenue"], 2),
        "delivery_positive_orders": fmt(delivery_orders, 2),
        "delivery_aov": fmt(safe_div(sums["delivery_revenue"], delivery_orders), 2),
        "delivery_revenue_share": fmt(safe_div(sums["delivery_revenue"], revenue), 4),
        "meituan_delivery_revenue": fmt(sums["meituan_delivery_revenue"], 2),
        "eleme_delivery_revenue": fmt(sums["eleme_delivery_revenue"], 2),
        "jd_delivery_revenue": fmt(sums["jd_delivery_revenue"], 2),
        "member_revenue": fmt(sums["member_revenue"], 2),
        "member_revenue_share": fmt(safe_div(sums["member_revenue"], revenue), 4),
    }


def read_workbook_rows(path: Path, sheet_index: int = 1) -> Iterable[tuple[int, dict[int, str]]]:
    with ZipFile(path) as zf:
        shared_strings = load_shared_strings(zf)
        with zf.open(f"xl/worksheets/sheet{sheet_index}.xml") as handle:
            for _, elem in iterparse(handle, events=("end",)):
                if not is_tag(elem, "row"):
                    continue
                row_number = int(elem.attrib.get("r", "0") or 0)
                values = row_values(elem, shared_strings)
                elem.clear()
                yield row_number, values


def inspect_workbook(path: Path) -> dict[str, Any]:
    title = ""
    filters = ""
    headers: list[str] = []
    dates: set[date] = set()
    for row_number, values in read_workbook_rows(path):
        if row_number == 1:
            title = values.get(1, "")
        elif row_number == 2:
            filters = values.get(1, "")
        elif row_number == 3:
            headers = [values.get(index, "") for index in range(1, max(values) + 1)]
            missing = [field for field in REQUIRED_COLUMNS if field not in headers]
            if title != "营业分组表":
                raise ValueError(f"{path} is not 营业分组表: {title}")
            if missing:
                raise ValueError(f"{path} missing required columns: {missing}")
        elif row_number >= 4:
            parsed = parse_date(values.get(1, ""))
            if parsed:
                dates.add(parsed)
    return {
        "path": str(path),
        "title": title,
        "filters": filters,
        "header_count": len(headers),
        "dates": sorted(dates),
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }


def date_range_from_export_name(path: Path) -> set[date] | None:
    match = EXPORT_RANGE_RE.search(path.name)
    if not match:
        return None
    start = parse_date(match.group(1))
    end = parse_date(match.group(2))
    if not start or not end or end < start:
        return None
    days = (end - start).days
    return {start + timedelta(days=offset) for offset in range(days + 1)}


def inspect_dish_workbook(path: Path) -> dict[str, Any]:
    title = ""
    filters = ""
    headers: list[str] = []
    dates: set[date] = date_range_from_export_name(path) or set()
    for row_number, values in read_workbook_rows(path):
        if row_number == 1:
            title = values.get(1, "")
        elif row_number == 2:
            filters = values.get(1, "")
        elif row_number == 3:
            headers = [values.get(index, "") for index in range(1, max(values) + 1)]
            missing = [field for field in DISH_REQUIRED_COLUMNS if field not in headers]
            if title != "菜品主题数据":
                raise ValueError(f"{path} is not 菜品主题数据: {title}")
            if missing:
                raise ValueError(f"{path} missing required dish columns: {missing}")
            if dates:
                break
        elif row_number >= 4 and headers:
            row = row_dict(headers, values)
            parsed = parse_date(row.get("营业日", ""))
            if parsed:
                dates.add(parsed)
    return {
        "path": str(path),
        "title": title,
        "filters": filters,
        "header_count": len(headers),
        "dates": sorted(dates),
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }


def load_catalog(path: Path) -> dict[str, Any]:
    title = ""
    filters = ""
    headers: list[str] = []
    by_name: dict[str, set[str]] = defaultdict(set)
    by_clean_name: dict[str, set[str]] = defaultdict(set)
    stalls: dict[str, int] = defaultdict(int)
    rows = 0
    for row_number, values in read_workbook_rows(path, sheet_index=1):
        if row_number == 1:
            title = values.get(1, "")
        elif row_number == 2:
            filters = values.get(1, "")
        elif row_number == 3:
            headers = [values.get(index, "") for index in range(1, max(values) + 1)]
            missing = [field for field in ["菜品名称", "基础分类"] if field not in headers]
            if missing:
                raise ValueError(f"{path} missing required catalog columns: {missing}")
        elif row_number >= 4 and headers:
            row = row_dict(headers, values)
            name = row.get("菜品名称", "")
            if not name:
                continue
            stall = row.get("基础分类", "") or "未分类"
            rows += 1
            stalls[stall] += 1
            by_name[normalize_name(name)].add(stall)
            by_clean_name[strip_channel_prefix(name)].add(stall)
    return {
        "path": str(path),
        "title": title,
        "filters": filters,
        "rows": rows,
        "stall_count": len(stalls),
        "stalls": dict(stalls),
        "by_name": by_name,
        "by_clean_name": by_clean_name,
        "package_sheet_policy": "总部套餐未拆解；套餐销售按菜品主题数据原始菜品名称保留。",
    }


def resolve_stall(dish_name: str, catalog: dict[str, Any]) -> tuple[str, str]:
    candidates = catalog["by_name"].get(normalize_name(dish_name))
    if not candidates:
        candidates = catalog["by_clean_name"].get(strip_channel_prefix(dish_name))
    if not candidates:
        return "未匹配菜品库", "unmatched"
    if len(candidates) > 1:
        return "重名/多分类", "ambiguous"
    return next(iter(candidates)), "matched"


def new_dish_agg() -> dict[str, Any]:
    return {
        "rows": 0,
        "dates": set(),
        "sums": defaultdict(float),
    }


def add_to_dish_agg(agg: dict[str, Any], row: dict[str, str], row_date: date) -> None:
    agg["rows"] += 1
    agg["dates"].add(row_date)
    for out_name, source_name in DISH_ADD_FIELDS.items():
        agg["sums"][out_name] += safe_float(row.get(source_name))


def derive_dish(agg: dict[str, Any]) -> dict[str, Any]:
    sums = agg["sums"]
    return {
        "rows": agg["rows"],
        "active_days": len(agg["dates"]),
        **{key: fmt(sums[key], 2) for key in DISH_ADD_FIELDS},
        "avg_income_per_item": fmt(safe_div(sums["income"], sums["quantity"]), 2),
        "refund_rate_by_qty": fmt(safe_div(sums["refund_quantity"], sums["quantity"]), 4),
    }


def export_dish_group(groups: dict[tuple[Any, ...], dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, agg in groups.items():
        row = {field: key[index] for index, field in enumerate(key_fields)}
        row.update(derive_dish(agg))
        rows.append(row)
    rows.sort(key=lambda item: tuple(str(item.get(field, "")) for field in key_fields))
    return rows


def dish_metric(row: dict[str, Any] | None, name: str) -> float | None:
    if not row:
        return None
    value = row.get(name)
    if value is None or value == "":
        return None
    return float(value)


def dish_diff(current: dict[str, Any] | None, baseline: dict[str, Any] | None, name: str) -> tuple[float | None, float | None]:
    current_value = dish_metric(current, name)
    baseline_value = dish_metric(baseline, name)
    if current_value is None or baseline_value is None:
        return None, None
    return fmt(current_value - baseline_value, 4), fmt(pct_change(current_value, baseline_value), 4)


def row_dict(headers: list[str], values: dict[int, str]) -> dict[str, str]:
    return {header: values.get(index, "") for index, header in enumerate(headers, start=1) if header}


def store_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        row.get("门店名称", "") or "未知门店",
        row.get("城市", "") or "未知城市",
        row.get("商户号", "") or "未知商户号",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_group(groups: dict[tuple[Any, ...], dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, agg in groups.items():
        row = {field: key[index] for index, field in enumerate(key_fields)}
        row.update(derive(agg))
        rows.append(row)
    rows.sort(key=lambda item: tuple(str(item.get(field, "")) for field in key_fields))
    return rows


def metric(row: dict[str, Any] | None, name: str) -> float | None:
    if not row:
        return None
    value = row.get(name)
    if value is None or value == "":
        return None
    return float(value)


def diff(current: dict[str, Any] | None, baseline: dict[str, Any] | None, name: str) -> tuple[float | None, float | None]:
    current_value = metric(current, name)
    baseline_value = metric(baseline, name)
    if current_value is None or baseline_value is None:
        return None, None
    return fmt(current_value - baseline_value, 4), fmt(pct_change(current_value, baseline_value), 4)


def driver_pair(
    store: str,
    basis: str,
    current: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    cur_revenue = metric(current, "net_revenue") or 0
    base_revenue = metric(baseline, "net_revenue") or 0
    cur_orders = metric(current, "positive_orders") or 0
    base_orders = metric(baseline, "positive_orders") or 0
    cur_aov = metric(current, "post_discount_aov") or 0
    base_aov = metric(baseline, "post_discount_aov") or 0

    dine_delta = (metric(current, "dine_in_revenue") or 0) - (metric(baseline, "dine_in_revenue") or 0)
    delivery_delta = (metric(current, "delivery_revenue") or 0) - (metric(baseline, "delivery_revenue") or 0)
    total_delta = cur_revenue - base_revenue
    other_delta = total_delta - dine_delta - delivery_delta
    volume_contribution = (cur_orders - base_orders) * base_aov
    price_contribution = cur_orders * (cur_aov - base_aov)

    signals = {
        "客流下降": (metric(current, "customer_count") or 0) - (metric(baseline, "customer_count") or 0),
        "开台下降": (metric(current, "consumed_tables") or 0) - (metric(baseline, "consumed_tables") or 0),
        "客单下降": cur_aov - base_aov,
        "堂食下降": dine_delta,
        "外卖下降": delivery_delta,
        "折扣升高": -1000000 * ((metric(current, "discount_rate") or 0) - (metric(baseline, "discount_rate") or 0)),
    }
    negative = {key: value for key, value in signals.items() if value < 0}
    top_negative = min(negative.items(), key=lambda item: item[1])[0] if negative else "无明显负向因素"

    return {
        "门店名称": store,
        "basis": basis,
        "net_revenue_delta": fmt(total_delta, 2),
        "net_revenue_pct": fmt(pct_change(cur_revenue, base_revenue), 4),
        "dine_in_delta": fmt(dine_delta, 2),
        "delivery_delta": fmt(delivery_delta, 2),
        "other_delta": fmt(other_delta, 2),
        "order_volume_contribution": fmt(volume_contribution, 2),
        "aov_contribution": fmt(price_contribution, 2),
        "customer_delta": fmt(signals["客流下降"], 2),
        "consumed_tables_delta": fmt(signals["开台下降"], 2),
        "aov_delta": fmt(signals["客单下降"], 2),
        "discount_rate_delta": fmt((metric(current, "discount_rate") or 0) - (metric(baseline, "discount_rate") or 0), 4),
        "top_negative_factor": top_negative,
    }


def classify_stores(comparison_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    revenues = sorted(float(row.get("current_net_revenue") or 0) for row in comparison_rows)
    discounts = sorted(float(row.get("current_discount_rate") or 0) for row in comparison_rows)
    aovs = sorted(float(row.get("current_post_discount_aov") or 0) for row in comparison_rows)

    def percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0
        idx = (len(values) - 1) * pct
        lo = int(idx)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] * (hi - idx) + values[hi] * (idx - lo)

    median_revenue = percentile(revenues, 0.5)
    median_discount = percentile(discounts, 0.5)
    median_aov = percentile(aovs, 0.5)

    rows: list[dict[str, Any]] = []
    for row in comparison_rows:
        revenue = float(row.get("current_net_revenue") or 0)
        wow = row.get("wow_net_revenue_pct")
        yoy = row.get("yoy_net_revenue_pct")
        discount = float(row.get("current_discount_rate") or 0)
        aov = float(row.get("current_post_discount_aov") or 0)
        wow_value = float(wow) if wow not in {None, ""} else 0
        yoy_value = float(yoy) if yoy not in {None, ""} else 0
        high_revenue = revenue >= median_revenue
        growing = wow_value >= 0

        if high_revenue and growing:
            segment = "明星门店"
            reason = "本周业务收入不低于门店中位数，且环比增长率非负"
        elif high_revenue and not growing:
            segment = "高基盘承压"
            reason = "本周业务收入不低于门店中位数，但环比增长率为负"
        elif not high_revenue and growing:
            segment = "成长观察"
            reason = "本周业务收入低于门店中位数，但环比增长率非负"
        else:
            segment = "问题门店"
            reason = "本周业务收入低于门店中位数，且环比增长率为负"

        warnings = []
        if wow_value <= -0.08:
            warnings.append("环比下滑超过 8%")
        if yoy_value <= -0.25:
            warnings.append("同比下滑超过 25%")
        if discount > median_discount * 1.2:
            warnings.append("折扣率高于门店中位水平 20% 以上")
        if aov < median_aov * 0.9:
            warnings.append("客单价低于门店中位水平 10% 以上")
        if warnings:
            reason = f"{reason}；预警：{'、'.join(warnings)}"

        rows.append({
            "门店名称": row["门店名称"],
            "segment": segment,
            "reason": reason,
            "revenue_threshold": fmt(median_revenue, 2),
            "growth_threshold": 0,
            "current_net_revenue": row.get("current_net_revenue"),
            "wow_net_revenue_pct": row.get("wow_net_revenue_pct"),
            "yoy_net_revenue_pct": row.get("yoy_net_revenue_pct"),
            "current_discount_rate": row.get("current_discount_rate"),
            "current_post_discount_aov": row.get("current_post_discount_aov"),
        })
    segment_order = {"明星门店": 0, "问题门店": 1, "高基盘承压": 2, "成长观察": 3}
    rows.sort(key=lambda item: (segment_order.get(str(item["segment"]), 9), -(item["current_net_revenue"] or 0)))
    return rows


def compare_store_stalls(target_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (row["门店名称"], row["档口"], row["period_key"]): row
        for row in target_rows
    }
    keys = sorted({(row["门店名称"], row["档口"]) for row in target_rows})
    comparison_rows: list[dict[str, Any]] = []
    for store, stall in keys:
        current = by_key.get((store, stall, "current"))
        previous = by_key.get((store, stall, "previous"))
        yoy = by_key.get((store, stall, "yoy"))
        row: dict[str, Any] = {"门店名称": store, "档口": stall}
        for label, source in [("current", current), ("previous", previous), ("yoy", yoy)]:
            for field in DISH_METRIC_FIELDS:
                row[f"{label}_{field}"] = source.get(field) if source else None
        for prefix, baseline in [("wow", previous), ("yoy", yoy)]:
            for field in ["income", "quantity", "positive_orders", "discount", "refund_amount"]:
                delta, pct = dish_diff(current, baseline, field)
                row[f"{prefix}_{field}_delta"] = delta
                row[f"{prefix}_{field}_pct"] = pct
        comparison_rows.append(row)
    comparison_rows.sort(key=lambda row: (row["门店名称"], -(row.get("current_income") or 0)))
    return comparison_rows


def store_stall_driver_rows(comparison_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stores = sorted({str(row.get("门店名称") or "") for row in comparison_rows if row.get("门店名称")})
    for store in stores:
        store_rows = [row for row in comparison_rows if row.get("门店名称") == store]
        for basis, prefix in [("环比", "wow"), ("同比", "yoy")]:
            comparable = [row for row in store_rows if row.get(f"{prefix}_income_delta") not in {None, ""}]
            negative = sorted(comparable, key=lambda row: float(row.get(f"{prefix}_income_delta") or 0))
            positive = sorted(comparable, key=lambda row: float(row.get(f"{prefix}_income_delta") or 0), reverse=True)
            top_neg = negative[0] if negative and float(negative[0].get(f"{prefix}_income_delta") or 0) < 0 else None
            top_pos = positive[0] if positive and float(positive[0].get(f"{prefix}_income_delta") or 0) > 0 else None
            signal_parts = []
            if top_neg:
                signal_parts.append(f"{top_neg['档口']} {float(top_neg.get(f'{prefix}_income_delta') or 0):,.0f}")
            if top_pos:
                signal_parts.append(f"{top_pos['档口']} +{float(top_pos.get(f'{prefix}_income_delta') or 0):,.0f}")
            rows.append({
                "门店名称": store,
                "basis": basis,
                "top_negative_stall": top_neg.get("档口") if top_neg else "",
                "top_negative_income_delta": top_neg.get(f"{prefix}_income_delta") if top_neg else None,
                "top_negative_income_pct": top_neg.get(f"{prefix}_income_pct") if top_neg else None,
                "top_positive_stall": top_pos.get("档口") if top_pos else "",
                "top_positive_income_delta": top_pos.get(f"{prefix}_income_delta") if top_pos else None,
                "top_positive_income_pct": top_pos.get(f"{prefix}_income_pct") if top_pos else None,
                "stall_signal": " / ".join(signal_parts) if signal_parts else "无明显档口变化",
            })
    return rows


def dish_driver_rows(
    dish_target_rows: list[dict[str, Any]],
    stall_driver_summary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {
        (row["门店名称"], row["档口"], row["菜品名称"], row["channel"], row["period_key"]): row
        for row in dish_target_rows
    }
    focus = set()
    for row in stall_driver_summary:
        for direction, field in [("negative", "top_negative_stall"), ("positive", "top_positive_stall")]:
            stall = row.get(field)
            if stall:
                focus.add((row["门店名称"], row["basis"], direction, stall))

    rows: list[dict[str, Any]] = []
    for store, basis, direction, stall in sorted(focus):
        prefix = "wow" if basis == "环比" else "yoy"
        baseline_key = "previous" if basis == "环比" else "yoy"
        dish_keys = sorted({
            (dish_store, dish_stall, dish_name, channel)
            for dish_store, dish_stall, dish_name, channel, period_key in by_key
            if dish_store == store and dish_stall == stall and period_key in {"current", baseline_key}
        })
        candidates: list[dict[str, Any]] = []
        for dish_store, dish_stall, dish_name, channel in dish_keys:
            current = by_key.get((dish_store, dish_stall, dish_name, channel, "current"))
            baseline = by_key.get((dish_store, dish_stall, dish_name, channel, baseline_key))
            income_delta, income_pct = dish_diff(current, baseline, "income")
            quantity_delta, _ = dish_diff(current, baseline, "quantity")
            if income_delta is None:
                continue
            candidates.append({
                "门店名称": store,
                "basis": basis,
                "direction": direction,
                "档口": stall,
                "菜品名称": dish_name,
                "channel": channel,
                "current_income": dish_metric(current, "income"),
                "baseline_income": dish_metric(baseline, "income"),
                "income_delta": fmt(income_delta, 2),
                "income_pct": fmt(income_pct, 4),
                "current_quantity": dish_metric(current, "quantity"),
                "baseline_quantity": dish_metric(baseline, "quantity"),
                "quantity_delta": fmt(quantity_delta, 2),
            })
        candidates.sort(key=lambda item: item["income_delta"], reverse=(direction == "positive"))
        rows.extend(candidates[:5])
    return rows


def profile_dish_inputs(
    dish_inputs: list[Path],
    catalog_path: Path,
    output_dir: Path,
    target_windows: dict[str, tuple[str, date, date]],
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    inspections = [inspect_dish_workbook(path) for path in dish_inputs]
    later_dates: list[set[date]] = []
    union_later: set[date] = set()
    for info in reversed(inspections):
        later_dates.append(set(union_later))
        union_later.update(info["dates"])
    later_dates = list(reversed(later_dates))

    store_stall_period: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_dish_agg)
    store_stall_dish_period: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_dish_agg)
    match_counts: dict[str, int] = defaultdict(int)
    period_counts: dict[str, int] = defaultdict(int)
    period_dates: dict[str, set[date]] = defaultdict(set)
    processed_dates: set[date] = set()
    processed_rows = 0
    skipped_duplicate_rows = 0
    skipped_out_of_scope_rows = 0

    for index, path in enumerate(dish_inputs):
        excluded_dates = later_dates[index]
        headers: list[str] = []
        for row_number, values in read_workbook_rows(path):
            if row_number == 3:
                headers = [values.get(col, "") for col in range(1, max(values) + 1)]
                continue
            if row_number < 4 or not headers or not values:
                continue
            row = row_dict(headers, values)
            parsed_date = parse_date(row.get("营业日", ""))
            if not parsed_date:
                continue
            if parsed_date in excluded_dates:
                skipped_duplicate_rows += 1
                continue
            period_key = target_period_for(parsed_date, target_windows)
            if not period_key:
                skipped_out_of_scope_rows += 1
                continue

            store = row.get("门店", "") or "未知门店"
            dish_name = row.get("菜品名称", "") or "未知菜品"
            channel = row.get("订单分类", "") or "未知渠道"
            stall, match_status = resolve_stall(dish_name, catalog)
            match_counts[match_status] += 1
            processed_dates.add(parsed_date)
            period_counts[period_key] += 1
            period_dates[period_key].add(parsed_date)
            processed_rows += 1
            period_label = target_windows[period_key][0]

            add_to_dish_agg(store_stall_period[(period_key, period_label, store, stall)], row, parsed_date)
            add_to_dish_agg(store_stall_dish_period[(period_key, period_label, store, stall, dish_name, channel)], row, parsed_date)

    target_rows = export_dish_group(store_stall_period, ["period_key", "period_label", "门店名称", "档口"])
    dish_target_rows = export_dish_group(store_stall_dish_period, ["period_key", "period_label", "门店名称", "档口", "菜品名称", "channel"])
    comparison_rows = compare_store_stalls(target_rows)
    driver_rows = store_stall_driver_rows(comparison_rows)
    dish_drivers = dish_driver_rows(dish_target_rows, driver_rows)
    total_matches = sum(match_counts.values())
    matched = match_counts.get("matched", 0)
    match_rate = safe_div(matched, total_matches) or 0

    write_csv(output_dir / "weekly_store_stall_metrics.csv", target_rows, ["period_key", "period_label", "门店名称", "档口"] + DISH_METRIC_FIELDS)
    comparison_fields = ["门店名称", "档口"]
    for prefix in ["current", "previous", "yoy"]:
        comparison_fields.extend([f"{prefix}_{field}" for field in DISH_METRIC_FIELDS])
    for prefix in ["wow", "yoy"]:
        for field in ["income", "quantity", "positive_orders", "discount", "refund_amount"]:
            comparison_fields.extend([f"{prefix}_{field}_delta", f"{prefix}_{field}_pct"])
    write_csv(output_dir / "weekly_store_stall_comparison.csv", comparison_rows, comparison_fields)
    write_csv(output_dir / "weekly_store_stall_driver_summary.csv", driver_rows, DISH_DRIVER_SUMMARY_FIELDS)
    write_csv(output_dir / "weekly_store_stall_dish_drivers.csv", dish_drivers, DISH_DRIVER_DETAIL_FIELDS)
    match_rows = [
        {"metric": "processed_rows", "value": processed_rows},
        {"metric": "matched_rows", "value": matched},
        {"metric": "unmatched_rows", "value": match_counts.get("unmatched", 0)},
        {"metric": "ambiguous_rows", "value": match_counts.get("ambiguous", 0)},
        {"metric": "match_rate", "value": fmt(match_rate, 4)},
        {"metric": "catalog_rows", "value": catalog["rows"]},
        {"metric": "catalog_stall_count", "value": catalog["stall_count"]},
        {"metric": "skipped_duplicate_rows", "value": skipped_duplicate_rows},
        {"metric": "skipped_out_of_scope_rows", "value": skipped_out_of_scope_rows},
    ]
    write_csv(output_dir / "dish_catalog_match_summary.csv", match_rows, ["metric", "value"])

    return {
        "enabled": True,
        "inputs": [
            {
                "path": info["path"],
                "title": info["title"],
                "header_count": info["header_count"],
                "min_date": date_text(info["min_date"]) if info["min_date"] else None,
                "max_date": date_text(info["max_date"]) if info["max_date"] else None,
            }
            for info in inspections
        ],
        "catalog": {
            "path": catalog["path"],
            "title": catalog["title"],
            "rows": catalog["rows"],
            "stall_count": catalog["stall_count"],
            "package_sheet_policy": catalog["package_sheet_policy"],
        },
        "processed_rows": processed_rows,
        "processed_date_start": date_text(min(processed_dates)) if processed_dates else None,
        "processed_date_end": date_text(max(processed_dates)) if processed_dates else None,
        "period_coverage": {
            key: {
                "label": label,
                "rows": period_counts.get(key, 0),
                "date_start": date_text(min(period_dates[key])) if period_dates.get(key) else None,
                "date_end": date_text(max(period_dates[key])) if period_dates.get(key) else None,
            }
            for key, (label, _start, _end) in target_windows.items()
        },
        "match_counts": dict(match_counts),
        "match_rate": fmt(match_rate, 4),
        "outputs": [
            "weekly_store_stall_metrics.csv",
            "weekly_store_stall_comparison.csv",
            "weekly_store_stall_driver_summary.csv",
            "weekly_store_stall_dish_drivers.csv",
            "dish_catalog_match_summary.csv",
        ],
    }


def profile(
    inputs: list[Path],
    output_dir: Path,
    target_windows: dict[str, tuple[str, date, date]],
    dish_inputs: list[Path] | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    inspections = [inspect_workbook(path) for path in inputs]
    trend_windows = build_trend_comparison_windows(target_windows)
    later_dates: list[set[date]] = []
    union_later: set[date] = set()
    for info in reversed(inspections):
        later_dates.append(set(union_later))
        union_later.update(info["dates"])
    later_dates = list(reversed(later_dates))

    weekly_store: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    weekly_store_channel: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    weekly_store_daypart: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    target_store_period: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    trend_comparison_store: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(new_agg)
    processed_dates: set[date] = set()
    skipped_duplicate_rows = 0
    skipped_summary_rows = 0
    processed_rows = 0

    for index, path in enumerate(inputs):
        excluded_dates = later_dates[index]
        headers: list[str] = []
        for row_number, values in read_workbook_rows(path):
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

            start = week_start_sunday(parsed_date)
            end = start + timedelta(days=6)
            period_key = target_period_for(parsed_date, target_windows)
            trend_window = trend_comparison_window_for(parsed_date, trend_windows)
            processed_dates.add(parsed_date)
            processed_rows += 1

            weekly_key = (date_text(start), date_text(end), week_label(start)) + key_store
            add_to_agg(weekly_store[weekly_key], row, parsed_date)

            target_name = target_windows[period_key][0] if period_key else "其他周"
            if period_key:
                add_to_agg(target_store_period[(period_key, target_windows[period_key][0]) + key_store], row, parsed_date)
            if trend_window:
                series_key, series_label, window_index, trend_start, trend_end = trend_window
                trend_key = (
                    series_key,
                    series_label,
                    window_index,
                    date_text(trend_start),
                    date_text(trend_end),
                    f"{trend_start:%m/%d}-{trend_end:%m/%d}",
                ) + key_store
                add_to_agg(trend_comparison_store[trend_key], row, parsed_date)

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
                    add_to_agg(weekly_store_channel[weekly_key + (target_name, channel_name)], channel_row, parsed_date)

            daypart = row.get("餐段", "") or "未知餐段"
            hour = row.get("时段", "") or "未知时段"
            add_to_agg(weekly_store_daypart[weekly_key + (target_name, daypart, hour)], row, parsed_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    weekly_rows = export_group(weekly_store, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号"])
    channel_rows = export_group(weekly_store_channel, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号", "period", "channel"])
    daypart_rows = export_group(weekly_store_daypart, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号", "period", "餐段", "时段"])
    target_rows = export_group(target_store_period, ["period_key", "period_label", "门店名称", "城市", "商户号"])
    trend_comparison_rows = export_group(
        trend_comparison_store,
        ["series_key", "series_label", "window_index", "week_start", "week_end", "week_label", "门店名称", "城市", "商户号"],
    )

    by_store_period = {
        (row["门店名称"], row["period_key"]): row
        for row in target_rows
    }
    stores = sorted({row["门店名称"] for row in target_rows})
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

    write_csv(output_dir / "weekly_store_metrics.csv", weekly_rows, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_channel_metrics.csv", channel_rows, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号", "period", "channel"] + METRIC_FIELDS)
    write_csv(output_dir / "weekly_store_daypart_metrics.csv", daypart_rows, ["week_start", "week_end", "week_label", "门店名称", "城市", "商户号", "period", "餐段", "时段"] + METRIC_FIELDS)
    write_csv(
        output_dir / "weekly_trend_comparison_metrics.csv",
        trend_comparison_rows,
        ["series_key", "series_label", "window_index", "week_start", "week_end", "week_label", "门店名称", "城市", "商户号"] + METRIC_FIELDS,
    )

    comparison_fields = ["门店名称"]
    for prefix in ["current", "previous", "yoy"]:
        comparison_fields.extend([f"{prefix}_{field}" for field in METRIC_FIELDS])
    for prefix in ["wow", "yoy"]:
        for field in ["net_revenue", "gross_sales", "dine_in_revenue", "delivery_revenue", "customer_count", "consumed_tables", "table_uses", "post_discount_aov", "discount_rate", "open_rate", "turnover_rate"]:
            comparison_fields.extend([f"{prefix}_{field}_delta", f"{prefix}_{field}_pct"])
    write_csv(output_dir / "weekly_store_comparison.csv", comparison_rows, comparison_fields)
    write_csv(output_dir / "store_driver_summary.csv", driver_rows, list(driver_rows[0].keys()) if driver_rows else [])
    write_csv(output_dir / "star_problem_stores.csv", star_rows, list(star_rows[0].keys()) if star_rows else [])

    stall_attribution: dict[str, Any] = {"enabled": False}
    stall_gap = "当前未提供自助菜品取数和菜品库基础信息，不能做档口穿透归因。"
    if dish_inputs and catalog_path:
        stall_attribution = profile_dish_inputs(dish_inputs, catalog_path, output_dir, target_windows)
        period_coverage = stall_attribution.get("period_coverage", {})
        missing_periods = [
            period_coverage.get(key, {}).get("label", key)
            for key in ["current", "previous", "yoy"]
            if not period_coverage.get(key, {}).get("rows")
        ]
        missing_note = (
            f"；菜品主题数据缺少{'、'.join(missing_periods)}，对应档口/菜品同比环比变化会显示为 N/A"
            if missing_periods else ""
        )
        stall_gap = (
            f"档口按菜品库「总部菜品.基础分类」归因；菜品库匹配率 {stall_attribution.get('match_rate', 0):.1%}，"
            f"未匹配和重名菜品单独归类；总部套餐暂未拆解到套餐组成菜品{missing_note}。"
        )
    elif dish_inputs or catalog_path:
        stall_gap = "档口穿透需要同时提供自助菜品取数和菜品库基础信息；当前只提供了一类输入，未启用档口归因。"

    summary = {
        "meta": {
            "inputs": [
                {
                    "path": info["path"],
                    "title": info["title"],
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
                "weekly_store_metrics.csv",
                "weekly_store_channel_metrics.csv",
                "weekly_store_daypart_metrics.csv",
                "weekly_trend_comparison_metrics.csv",
                "weekly_store_comparison.csv",
                "store_driver_summary.csv",
                "star_problem_stores.csv",
                *stall_attribution.get("outputs", []),
                "weekly_meeting_summary.json",
            ],
            "stall_attribution": stall_attribution,
        },
        "comparison": comparison_rows,
        "drivers": driver_rows,
        "store_segments": star_rows,
        "channel_current": [row for row in channel_rows if row.get("period") == "本周"],
        "daypart_current_previous": [row for row in daypart_rows if row.get("period") in {"本周", "环比周"}],
        "weekly_trend": weekly_rows,
        "weekly_trend_comparison": trend_comparison_rows,
        "data_gaps": [
            "当前营业分组表没有网评分数、评论文本字段，不能做网评分数和词云分析。",
            stall_gap,
        ],
    }
    (output_dir / "weekly_meeting_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, nargs="+", type=Path)
    parser.add_argument("--dish-input", nargs="+", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--current-start", type=parse_date, default=DEFAULT_TARGET_WINDOWS["current"][1])
    parser.add_argument("--current-end", type=parse_date, default=DEFAULT_TARGET_WINDOWS["current"][2])
    parser.add_argument("--previous-start", type=parse_date, default=DEFAULT_TARGET_WINDOWS["previous"][1])
    parser.add_argument("--previous-end", type=parse_date, default=DEFAULT_TARGET_WINDOWS["previous"][2])
    parser.add_argument("--yoy-start", type=parse_date, default=DEFAULT_TARGET_WINDOWS["yoy"][1])
    parser.add_argument("--yoy-end", type=parse_date, default=DEFAULT_TARGET_WINDOWS["yoy"][2])
    args = parser.parse_args()
    target_windows = {
        "current": ("本周", args.current_start, args.current_end),
        "previous": ("环比周", args.previous_start, args.previous_end),
        "yoy": ("同比周", args.yoy_start, args.yoy_end),
    }
    summary = profile(args.input, args.output_dir, target_windows, args.dish_input, args.catalog)
    print(json.dumps({
        "coverage_start": summary["meta"]["coverage_start"],
        "coverage_end": summary["meta"]["coverage_end"],
        "processed_rows": summary["meta"]["processed_rows"],
        "skipped_duplicate_rows": summary["meta"]["skipped_duplicate_rows"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
