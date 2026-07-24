import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "scripts" / "profile_monthly_profit_data.py"
REPORT_PATH = ROOT / "scripts" / "generate_monthly_profit_report_html.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


profile = load_module("profile_monthly_profit_data", PROFILE_PATH)
report = load_module("generate_monthly_profit_report_html", REPORT_PATH)


class MonthlyProfitReportTest(unittest.TestCase):
    def test_profit_rate_boundary_and_store_mapping(self) -> None:
        self.assertFalse(profile.rate_available(2024, 6))
        self.assertTrue(profile.rate_available(2024, 7))
        self.assertEqual(profile.resolve_profit_store("麦家小馆（通州保利店）"), "保利店")
        self.assertEqual(profile.resolve_profit_store("麦家小馆（常营店）"), "常营店")

    def test_profit_rate_uses_store_income_not_gross_sales(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "business.xlsx"
            sheet = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="3"><c r="A3" t="inlineStr"><is><t>营业日期</t></is></c><c r="B3" t="inlineStr"><is><t>门店名称</t></is></c><c r="C3" t="inlineStr"><is><t>月</t></is></c><c r="D3" t="inlineStr"><is><t>城市</t></is></c><c r="E3" t="inlineStr"><is><t>订单分类</t></is></c><c r="F3" t="inlineStr"><is><t>订单来源</t></is></c><c r="G3" t="inlineStr"><is><t>店内营业收入</t></is></c><c r="H3" t="inlineStr"><is><t>营业额(元)</t></is></c></row>
<row r="4"><c r="A4" t="inlineStr"><is><t>2024/07/01</t></is></c><c r="B4" t="inlineStr"><is><t>麦家小馆（苏州街店）</t></is></c><c r="C4" t="inlineStr"><is><t>2024/07</t></is></c><c r="D4" t="inlineStr"><is><t>北京市</t></is></c><c r="E4" t="inlineStr"><is><t>到店</t></is></c><c r="F4" t="inlineStr"><is><t>自营</t></is></c><c r="G4"><v>100</v></c><c r="H4"><v>999</v></c></row>
</sheetData></worksheet>'''
            with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            revenue, _ = profile.aggregate_business_files([workbook])
        self.assertEqual(revenue[("苏州街", 2024, 7)], 100.0)

    def test_payload_keeps_all_twelve_months_for_absent_store_year(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "monthly_profit_summary.json").write_text(json.dumps({
                "stores": ["苏州街", "常营店", "保利店"],
                "years": [2023, 2024],
                "profit_source": "profit.xlsx",
                "business_sources": ["business.xlsx"],
                "profit_rate_rule": "test rule",
            }, ensure_ascii=False), encoding="utf-8")
            with (directory / "monthly_profit_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["门店", "年份", "月份", "净利润", "店内营业收入", "利润率", "利润状态", "利润率状态"])
                writer.writeheader()
                writer.writerow({"门店": "苏州街", "年份": 2023, "月份": 2, "净利润": 100, "店内营业收入": "", "利润率": "", "利润状态": "已记录", "利润率状态": "无可用流水"})
            payload = report.build_payload(directory, "麦家小馆")
        months = payload["data"]["保利店"]["2023"]["profit"]
        self.assertEqual([item["month"] for item in months], list(range(1, 13)))
        self.assertTrue(all(item["value"] is None for item in months))
        self.assertIn(".dot[data-month]", report.HTML_TEMPLATE)
        self.assertNotIn("month-hit", report.HTML_TEMPLATE)
        self.assertIn("min-dot", report.HTML_TEMPLATE)
        self.assertIn("max-dot", report.HTML_TEMPLATE)
        self.assertNotIn("negative-dot", report.HTML_TEMPLATE)
        self.assertIn("select", report.HTML_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
