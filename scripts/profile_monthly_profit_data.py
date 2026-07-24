#!/usr/bin/env python3
"""Build monthly profit and profit-rate fact tables from profit and business exports.

The business workbooks can contain hundreds of thousands of rows and sometimes
declare the wrong Excel used range.  This module reads their worksheet XML
directly and only extracts the date, store and gross-sales columns required for
the monthly profit-rate calculation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from xml.etree.ElementTree import iterparse
from zipfile import ZipFile


CELL_RE = re.compile(r"([A-Z]+)(\d+)")
PROFIT_STORES = {
    "苏州街": ("苏州街",),
    "常营店": ("常营",),
    "保利店": ("通州保利",),
}
RATE_AVAILABLE_FROM = (2024, 7)  # 2024-06 only has partial business data.


def is_tag(elem: Any, name: str) -> bool:
    return elem.tag == name or elem.tag.endswith("}" + name)


def col_to_num(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + ord(char.upper()) - 64
    return value


def load_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    result: list[str] = []
    with workbook.open("xl/sharedStrings.xml") as handle:
        for _, elem in iterparse(handle, events=("end",)):
            if is_tag(elem, "si"):
                result.append("".join(
                    node.text or "" for node in elem.iter() if is_tag(node, "t")
                ))
                elem.clear()
    return result


def cell_text(cell: Any, shared_strings: list[str]) -> str:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if is_tag(node, "t"))
    value = next((node.text or "" for node in cell.iter() if is_tag(node, "v")), "")
    if kind == "s" and value:
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return value
    return value


def row_values(row: Any, shared_strings: list[str], keep: set[int] | None = None) -> dict[int, str]:
    values: dict[int, str] = {}
    for cell in row.iter():
        if not is_tag(cell, "c"):
            continue
        match = CELL_RE.match(cell.attrib.get("r", ""))
        if not match:
            continue
        column = col_to_num(match.group(1))
        if keep is None or column in keep:
            values[column] = cell_text(cell, shared_strings)
    return values


def safe_float(value: str | float | None) -> float:
    try:
        number = float(str(value or "").replace(",", "").strip())
    except ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


def normalize_month(value: str) -> tuple[int, int] | None:
    match = re.search(r"(20\d{2})[/-](\d{1,2})", str(value))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def month_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def resolve_profit_store(business_store: str) -> str | None:
    matches = [name for name, aliases in PROFIT_STORES.items() if any(alias in business_store for alias in aliases)]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous store mapping for {business_store}: {matches}")
    return matches[0] if matches else None


def worksheet_paths(workbook: ZipFile) -> list[str]:
    return sorted(
        name for name in workbook.namelist()
        if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
    )


def read_profit_workbook(path: Path) -> dict[tuple[str, int, int], float | None]:
    profits: dict[tuple[str, int, int], float | None] = {}
    with ZipFile(path) as workbook:
        shared_strings = load_shared_strings(workbook)
        for sheet_path in worksheet_paths(workbook):
            current_store: str | None = None
            with workbook.open(sheet_path) as handle:
                for _, elem in iterparse(handle, events=("end",)):
                    if not is_tag(elem, "row"):
                        continue
                    values = row_values(elem, shared_strings)
                    store_cell = values.get(1, "").strip()
                    year_cell = values.get(2, "").strip()
                    if store_cell and store_cell not in {"门店", "合计"}:
                        current_store = store_cell
                    if current_store in PROFIT_STORES and re.fullmatch(r"\d{2}年", year_cell):
                        year = 2000 + int(year_cell[:2])
                        for month in range(1, 13):
                            raw = values.get(month + 2, "")
                            profits[(current_store, year, month)] = (
                                safe_float(raw) if str(raw).strip() else None
                            )
                    elem.clear()
    if not profits:
        raise ValueError("No profit rows were found for the configured stores.")
    return profits


def is_summary_row(values: dict[int, str], columns: dict[str, int]) -> bool:
    dimensions = [
        values.get(columns.get(field, -1), "").strip()
        for field in ("月", "门店名称", "城市", "订单分类", "订单来源")
    ]
    return dimensions.count("--") >= 3


def aggregate_business_files(paths: Iterable[Path]) -> tuple[dict[tuple[str, int, int], float], list[dict[str, Any]]]:
    revenue: dict[tuple[str, int, int], float] = defaultdict(float)
    source_summary: list[dict[str, Any]] = []
    required = {"营业日期", "门店名称", "营业额(元)"}
    summary_dimensions = {"月", "城市", "订单分类", "订单来源"}

    for path in paths:
        rows = 0
        target_rows = 0
        source_months: set[str] = set()
        with ZipFile(path) as workbook:
            shared_strings = load_shared_strings(workbook)
            for sheet_path in worksheet_paths(workbook):
                headers: dict[str, int] = {}
                keep: set[int] = set()
                with workbook.open(sheet_path) as handle:
                    for _, elem in iterparse(handle, events=("end",)):
                        if not is_tag(elem, "row"):
                            continue
                        row_number = int(elem.attrib.get("r", "0") or 0)
                        if row_number == 3:
                            full = row_values(elem, shared_strings)
                            headers = {value.strip(): index for index, value in full.items() if value.strip()}
                            missing = required - headers.keys()
                            if missing:
                                raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
                            keep = {headers[field] for field in required | summary_dimensions}
                        elif row_number >= 4 and headers:
                            values = row_values(elem, shared_strings, keep)
                            if values and not is_summary_row(values, headers):
                                rows += 1
                                business_store = values.get(headers["门店名称"], "").strip()
                                store = resolve_profit_store(business_store) if business_store else None
                                period = normalize_month(values.get(headers["营业日期"], ""))
                                if store and period:
                                    year, month = period
                                    revenue[(store, year, month)] += safe_float(values.get(headers["营业额(元)"]))
                                    target_rows += 1
                                    source_months.add(month_label(year, month))
                        elem.clear()
        source_summary.append({
            "file": path.name,
            "data_rows_streamed": rows,
            "target_rows_streamed": target_rows,
            "month_start": min(source_months) if source_months else None,
            "month_end": max(source_months) if source_months else None,
        })
    return dict(revenue), source_summary


def rate_available(year: int, month: int) -> bool:
    return (year, month) >= RATE_AVAILABLE_FROM


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["门店", "年份", "月份", "净利润", "营业额", "利润率", "利润状态", "利润率状态"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def profile(profit_file: Path, business_files: list[Path], output_dir: Path) -> dict[str, Any]:
    profits = read_profit_workbook(profit_file)
    revenue, sources = aggregate_business_files(business_files)
    rows: list[dict[str, Any]] = []
    for store, year, month in sorted(profits):
        profit = profits[(store, year, month)]
        gross_sales = revenue.get((store, year, month))
        if profit is None:
            rate = None
            profit_status = "无数据／门店尚未开业"
            rate_status = "无利润数据"
        elif not rate_available(year, month):
            rate = None
            profit_status = "已记录"
            rate_status = "缺少完整流水（2024年6月及更早）"
        elif not gross_sales or gross_sales <= 0:
            rate = None
            profit_status = "已记录"
            rate_status = "无可用流水"
        else:
            rate = profit / gross_sales
            profit_status = "已记录"
            rate_status = "可计算"
        rows.append({
            "门店": store,
            "年份": year,
            "月份": month,
            "净利润": round(profit, 2) if profit is not None else None,
            "营业额": round(gross_sales, 2) if gross_sales is not None else None,
            "利润率": round(rate, 8) if rate is not None else None,
            "利润状态": profit_status,
            "利润率状态": rate_status,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "monthly_profit_metrics.csv", rows)
    summary = {
        "profit_source": str(profit_file),
        "business_sources": [str(path) for path in business_files],
        "stores": list(PROFIT_STORES),
        "years": sorted({row["年份"] for row in rows}),
        "store_mapping": {
            "苏州街": "门店名称包含“苏州街”",
            "常营店": "门店名称包含“常营”",
            "保利店": "门店名称包含“通州保利”",
        },
        "profit_rate_rule": "月净利润 ÷ 当月营业额汇总；2024年6月及更早留空。",
        "business_source_summary": sources,
        "metrics_count": len(rows),
        "outputs": ["monthly_profit_metrics.csv", "monthly_profit_summary.json"],
    }
    (output_dir / "monthly_profit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profit-file", required=True, type=Path)
    parser.add_argument("--business-input", required=True, nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = profile(args.profit_file, args.business_input, args.output_dir)
    print(json.dumps({"stores": summary["stores"], "years": summary["years"], "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
