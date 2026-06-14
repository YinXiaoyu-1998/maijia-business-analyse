#!/usr/bin/env python3
"""Stream-profile Maijia business data without loading the full workbook."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse
from zipfile import ZipFile


CELL_RE = re.compile(r"([A-Z]+)(\d+)")
MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

DIMENSION_FIELDS = [
    "营业日期",
    "周",
    "月",
    "门店名称",
    "城市",
    "商户号",
    "一级组织机构名称",
    "二级组织机构名称",
    "三级组织机构名称",
    "四级组织机构名称",
    "订单分类",
    "订单来源",
    "时段",
    "餐段",
    "退单类型名称",
    "是否是会员",
    "就餐方式",
]

ADDITIVE_FIELDS = [
    "营业额(元)",
    "订单营业收入",
    "优惠金额",
    "有效订单量",
    "逆向订单量",
    "正向订单量",
    "已结账订单量",
    "消费桌数",
    "消费次数",
    "会员消费金额",
    "会员订单收入",
    "店内营业额",
    "店内营业收入",
    "店内优惠金额",
    "店内正向单订单量",
    "店内退单量",
    "店内已结账订单量",
    "店内退款金额",
    "店内订单量",
    "外卖营业额",
    "外卖营业收入",
    "外卖折扣金额",
    "外卖订单量",
    "外卖正向单订单量",
    "外卖退单量",
    "外卖已结账订单量",
    "外卖退款金额",
    "美团外卖营业额",
    "美团外卖营业收入",
    "美团外卖折扣金额",
    "美团外卖订单量",
    "美团外卖正向单订单量",
    "美团外卖退单量",
    "美团外卖已结账订单量",
    "美团外卖退款金额",
    "京东外卖营业额",
    "京东外卖营业收入",
    "京东外卖折扣金额",
    "京东外卖订单量",
    "京东外卖正向单订单量",
    "京东外卖退单量",
    "京东外卖已结账订单量",
    "京东外卖退款金额",
    "饿了么外卖营业额",
    "饿了么外卖营业收入",
    "饿了么外卖折扣金额",
    "饿了么外卖订单量",
    "饿了么外卖正向单订单量",
    "饿了么外卖退单量",
    "饿了么外卖已结账订单量",
    "饿了么外卖退款金额",
    "自提营业额",
    "自提营业收入",
    "自提折扣金额",
    "自提订单量",
    "自提正向单订单量",
    "自提已结账订单量",
    "自提退单量",
    "自提退款金额",
    "现金营业额",
    "现金营业收入",
    "现金优惠金额",
    "现金支付次数",
    "扫码支付营业收入",
    "扫码支付营业额",
    "扫码支付优惠金额",
    "扫码支付支付次数",
    "扫码支付微信营业额",
    "扫码支付支付宝营业额",
    "扫码支付微信营业收入",
    "扫码支付支付宝营业收入",
    "扫码支付微信优惠金额",
    "扫码支付支付宝优惠金额",
    "扫码支付微信支付次数",
    "扫码支付支付宝支付次数",
    "团购营业额",
    "美团团购营业额",
    "抖音团购营业额",
    "快手团购营业额",
    "团购营业收入",
    "美团团购营业收入",
    "抖音团购营业收入",
    "快手团购营业收入",
    "团购优惠金额",
    "美团团购优惠金额",
    "抖音团购优惠金额",
    "快手团购优惠金额",
    "团购支付次数",
    "美团团购支付次数",
    "抖音团购支付次数",
    "快手团购支付次数",
    "抵用券营业额",
    "抵用券营业收入",
    "抵用券优惠金额",
    "抵用券支付次数",
    "优惠券营业额",
    "优惠券营业收入",
    "优惠券优惠金额",
    "优惠券支付次数",
    "自定义记账营业额",
    "自定义记账营业收入",
    "自定义记账优惠金额",
    "自定义记账支付次数",
    "店内营销会员订单量",
    "店内非会员订单量",
    "外卖营销会员订单量",
    "店内营销会员营业额",
    "店内非会员营业额",
    "店内营销会员营业收入",
    "外卖营销会员营业额",
    "用餐人数",
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
        for event, elem in iterparse(handle, events=("end",)):
            if is_tag(elem, "si"):
                parts = [
                    node.text or ""
                    for node in elem.iter()
                    if is_tag(node, "t") and node.text is not None
                ]
                strings.append("".join(parts))
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


def safe_float(value: str) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "null", "None"}:
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


def fmt_number(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def new_agg() -> dict[str, Any]:
    return {
        "rows": 0,
        "sums": defaultdict(float),
        "dates": set(),
        "stores": set(),
        "cities": set(),
    }


def add_row(agg: dict[str, Any], row: dict[str, str]) -> None:
    agg["rows"] += 1
    date = row.get("营业日期", "")
    store = row.get("门店名称", "")
    city = row.get("城市", "")
    if date:
        agg["dates"].add(date)
    if store:
        agg["stores"].add(store)
    if city:
        agg["cities"].add(city)
    sums = agg["sums"]
    for field in ADDITIVE_FIELDS:
        sums[field] += safe_float(row.get(field, ""))


def derived_metrics(agg: dict[str, Any]) -> dict[str, Any]:
    sums = agg["sums"]
    gross = sums["营业额(元)"]
    revenue = sums["订单营业收入"]
    discount = sums["优惠金额"]
    orders = sums["正向订单量"]
    refunds = sums["店内退款金额"] + sums["外卖退款金额"] + sums["自提退款金额"]
    dine_in_revenue = sums["店内营业收入"]
    delivery_revenue = sums["外卖营业收入"]
    pickup_revenue = sums["自提营业收入"]
    member_revenue = sums["会员订单收入"]
    customer_count = sums["用餐人数"]
    tables = sums["消费桌数"]

    return {
        "rows": agg["rows"],
        "active_days": len(agg["dates"]),
        "store_count": len(agg["stores"]),
        "city_count": len(agg["cities"]),
        "gross_sales": fmt_number(gross, 2),
        "net_revenue": fmt_number(revenue, 2),
        "discount_amount": fmt_number(discount, 2),
        "discount_rate": fmt_number(safe_div(discount, gross), 4),
        "positive_orders": fmt_number(orders, 2),
        "settled_orders": fmt_number(sums["已结账订单量"], 2),
        "reverse_orders": fmt_number(sums["逆向订单量"], 2),
        "pre_discount_aov": fmt_number(safe_div(gross, orders), 2),
        "post_discount_aov": fmt_number(safe_div(revenue, orders), 2),
        "dine_in_revenue": fmt_number(dine_in_revenue, 2),
        "delivery_revenue": fmt_number(delivery_revenue, 2),
        "pickup_revenue": fmt_number(pickup_revenue, 2),
        "dine_in_revenue_share": fmt_number(safe_div(dine_in_revenue, revenue), 4),
        "delivery_revenue_share": fmt_number(safe_div(delivery_revenue, revenue), 4),
        "pickup_revenue_share": fmt_number(safe_div(pickup_revenue, revenue), 4),
        "member_revenue": fmt_number(member_revenue, 2),
        "member_revenue_share": fmt_number(safe_div(member_revenue, revenue), 4),
        "refund_amount_known": fmt_number(refunds, 2),
        "refund_rate_known": fmt_number(safe_div(refunds, gross), 4),
        "customer_count": fmt_number(customer_count, 2),
        "revenue_per_customer": fmt_number(safe_div(revenue, customer_count), 2),
        "consumed_tables": fmt_number(tables, 2),
        "revenue_per_table": fmt_number(safe_div(dine_in_revenue, tables), 2),
    }


def row_dict_from_values(headers: list[str], values: dict[int, str]) -> dict[str, str]:
    return {
        header: values.get(index, "")
        for index, header in enumerate(headers, start=1)
        if header
    }


def as_member_label(value: str) -> str:
    text = str(value).strip()
    if text == "1":
        return "会员"
    if text == "0":
        return "非会员"
    return text or "未知"


def is_summary_row(row: dict[str, str]) -> bool:
    summary_markers = [
        row.get("月", "").strip(),
        row.get("门店名称", "").strip(),
        row.get("城市", "").strip(),
        row.get("订单分类", "").strip(),
        row.get("订单来源", "").strip(),
    ]
    return summary_markers.count("--") >= 3


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_group(
    groups: dict[Any, dict[str, Any]],
    key_fields: list[str],
    sort_field: str = "net_revenue",
    reverse: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, agg in groups.items():
        if not isinstance(key, tuple):
            key = (key,)
        prefix = {field: key[index] for index, field in enumerate(key_fields)}
        rows.append({**prefix, **derived_metrics(agg)})
    rows.sort(key=lambda row: (row.get(sort_field) is None, row.get(sort_field) or 0), reverse=reverse)
    return rows


def compact_top(rows: list[dict[str, Any]], label_fields: list[str], limit: int = 10) -> list[dict[str, Any]]:
    keep_fields = label_fields + [
        "net_revenue",
        "gross_sales",
        "discount_rate",
        "positive_orders",
        "post_discount_aov",
        "delivery_revenue_share",
        "member_revenue_share",
        "refund_rate_known",
    ]
    return [{field: row.get(field) for field in keep_fields if field in row} for row in rows[:limit]]


def profile_workbook(input_path: Path, output_dir: Path) -> dict[str, Any]:
    overall = new_agg()
    monthly: dict[Any, dict[str, Any]] = defaultdict(new_agg)
    stores: dict[Any, dict[str, Any]] = defaultdict(new_agg)
    channels: dict[Any, dict[str, Any]] = defaultdict(new_agg)
    dayparts: dict[Any, dict[str, Any]] = defaultdict(new_agg)
    members: dict[Any, dict[str, Any]] = defaultdict(new_agg)
    store_dayparts: dict[Any, dict[str, Any]] = defaultdict(new_agg)

    unique_values: dict[str, set[str]] = {field: set() for field in DIMENSION_FIELDS}
    headers: list[str] = []
    warnings: list[str] = []
    data_rows = 0
    skipped_summary_rows = 0
    title = ""
    filters = ""

    with ZipFile(input_path) as zf:
        shared_strings = load_shared_strings(zf)
        sheet_path = "xl/worksheets/sheet1.xml"
        with zf.open(sheet_path) as handle:
            for event, elem in iterparse(handle, events=("end",)):
                if not is_tag(elem, "row"):
                    continue

                row_number = int(elem.attrib.get("r", "0") or 0)
                values = row_values(elem, shared_strings)

                if row_number == 1 and values:
                    title = values.get(1, "")
                elif row_number == 2 and values:
                    filters = values.get(1, "")
                elif row_number == 3 and values:
                    headers = [values.get(index, "") for index in range(1, max(values) + 1)]
                    missing = [field for field in DIMENSION_FIELDS + ["营业额(元)", "订单营业收入"] if field not in headers]
                    if missing:
                        raise ValueError(f"Missing required columns: {missing}")
                elif row_number >= 4 and headers and values:
                    row = row_dict_from_values(headers, values)
                    if not any(row.get(field) for field in DIMENSION_FIELDS):
                        elem.clear()
                        continue
                    if is_summary_row(row):
                        skipped_summary_rows += 1
                        elem.clear()
                        continue
                    data_rows += 1

                    for field in DIMENSION_FIELDS:
                        value = row.get(field, "")
                        if value and len(unique_values[field]) < 200:
                            unique_values[field].add(value)

                    month = row.get("月", "") or "未知月份"
                    store_key = (
                        row.get("门店名称", "") or "未知门店",
                        row.get("城市", "") or "未知城市",
                        row.get("商户号", "") or "未知商户号",
                    )
                    channel_key = (
                        row.get("订单分类", "") or "未知订单分类",
                        row.get("订单来源", "") or "未知订单来源",
                    )
                    daypart_key = (
                        row.get("餐段", "") or "未知餐段",
                        row.get("时段", "") or "未知时段",
                    )
                    member_key = as_member_label(row.get("是否是会员", ""))
                    store_daypart_key = store_key + daypart_key

                    for agg in [
                        overall,
                        monthly[month],
                        stores[store_key],
                        channels[channel_key],
                        dayparts[daypart_key],
                        members[member_key],
                        store_dayparts[store_daypart_key],
                    ]:
                        add_row(agg, row)

                    if data_rows % 100000 == 0:
                        print(f"streamed_rows={data_rows}")

                elem.clear()

    if not headers:
        raise ValueError("Could not find header row at row 3.")

    output_dir.mkdir(parents=True, exist_ok=True)

    monthly_rows = export_group(monthly, ["月"], reverse=False)
    store_rows = export_group(stores, ["门店名称", "城市", "商户号"])
    channel_rows = export_group(channels, ["订单分类", "订单来源"])
    daypart_rows = export_group(dayparts, ["餐段", "时段"])
    member_rows = export_group(members, ["会员类型"])
    store_daypart_rows = export_group(
        store_dayparts,
        ["门店名称", "城市", "商户号", "餐段", "时段"],
    )

    common_fields = [
        "rows",
        "active_days",
        "store_count",
        "city_count",
        "gross_sales",
        "net_revenue",
        "discount_amount",
        "discount_rate",
        "positive_orders",
        "settled_orders",
        "reverse_orders",
        "pre_discount_aov",
        "post_discount_aov",
        "dine_in_revenue",
        "delivery_revenue",
        "pickup_revenue",
        "dine_in_revenue_share",
        "delivery_revenue_share",
        "pickup_revenue_share",
        "member_revenue",
        "member_revenue_share",
        "refund_amount_known",
        "refund_rate_known",
        "customer_count",
        "revenue_per_customer",
        "consumed_tables",
        "revenue_per_table",
    ]

    write_csv(output_dir / "monthly_trend.csv", monthly_rows, ["月"] + common_fields)
    write_csv(output_dir / "store_summary.csv", store_rows, ["门店名称", "城市", "商户号"] + common_fields)
    write_csv(output_dir / "channel_summary.csv", channel_rows, ["订单分类", "订单来源"] + common_fields)
    write_csv(output_dir / "daypart_summary.csv", daypart_rows, ["餐段", "时段"] + common_fields)
    write_csv(output_dir / "member_summary.csv", member_rows, ["会员类型"] + common_fields)
    write_csv(
        output_dir / "store_daypart_summary.csv",
        store_daypart_rows,
        ["门店名称", "城市", "商户号", "餐段", "时段"] + common_fields,
    )

    summary = {
        "source_file": str(input_path),
        "title": title,
        "filters": filters,
        "header_count": len(headers),
        "data_rows_streamed": data_rows,
        "skipped_summary_rows": skipped_summary_rows,
        "overall_kpis": derived_metrics(overall),
        "dimension_samples": {
            field: sorted(values)
            for field, values in unique_values.items()
        },
        "top_stores_by_revenue": compact_top(store_rows, ["门店名称", "城市", "商户号"], 12),
        "bottom_stores_by_revenue": compact_top(list(reversed(store_rows)), ["门店名称", "城市", "商户号"], 12),
        "top_channels_by_revenue": compact_top(channel_rows, ["订单分类", "订单来源"], 12),
        "top_dayparts_by_revenue": compact_top(daypart_rows, ["餐段", "时段"], 12),
        "member_summary": member_rows,
        "warnings": warnings,
        "outputs": [
            "monthly_trend.csv",
            "store_summary.csv",
            "channel_summary.csv",
            "daypart_summary.csv",
            "member_summary.csv",
            "store_daypart_summary.csv",
            "analysis_summary.json",
        ],
    }

    with (output_dir / "analysis_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    summary = profile_workbook(args.input, args.output_dir)
    print(json.dumps({
        "data_rows_streamed": summary["data_rows_streamed"],
        "overall_kpis": summary["overall_kpis"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
