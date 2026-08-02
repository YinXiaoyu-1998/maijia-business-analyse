import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
MODULE_PATH = SCRIPTS_DIR / "generate_monthly_meeting_report_html.py"
SPEC = importlib.util.spec_from_file_location("generate_monthly_meeting_report_html", MODULE_PATH)
report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class MonthlyMeetingReportHtmlTest(unittest.TestCase):
    def test_payload_uses_order_revenue_not_gross_sales_for_business_revenue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp)
            (input_dir / "monthly_meeting_summary.json").write_text(
                json.dumps(
                    {
                        "meta": {
                            "coverage_start": "2026/07/01",
                            "coverage_end": "2026/07/31",
                            "target_windows": {
                                "current": {"label": "本月", "start": "2026/07/01", "end": "2026/07/31"},
                                "previous": {"label": "上月", "start": "2026/06/01", "end": "2026/06/30"},
                                "yoy": {"label": "去年同月", "start": "2025/07/01", "end": "2025/07/31"},
                            },
                            "processed_rows": 3,
                            "store_count": 1,
                            "outputs": [],
                        },
                        "data_gaps": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            write_csv(
                input_dir / "monthly_store_comparison.csv",
                [
                    {
                        "门店名称": "麦家小馆（甲店）",
                        "current_net_revenue": 300,
                        "previous_net_revenue": 200,
                        "yoy_net_revenue": 150,
                        "current_gross_sales": 999,
                        "previous_gross_sales": 888,
                        "yoy_gross_sales": 777,
                        "current_positive_orders": 10,
                    }
                ],
            )
            write_csv(input_dir / "star_problem_stores.csv", [{"门店名称": "麦家小馆（甲店）", "segment": "明星门店", "reason": ""}])
            write_csv(input_dir / "store_driver_summary.csv", [{"门店名称": "麦家小馆（甲店）", "basis": "环比"}])
            write_csv(input_dir / "monthly_store_channel_metrics.csv", [{"period": "本月", "门店名称": "麦家小馆（甲店）", "channel": "堂食", "net_revenue": 300}])
            write_csv(input_dir / "monthly_store_daypart_metrics.csv", [{"period": "本月", "门店名称": "麦家小馆（甲店）", "餐段": "午餐", "时段": "12", "net_revenue": 300}])

            payload = report.build_payload(input_dir, "麦家小馆")

        self.assertEqual(payload["kpis"]["current_revenue"], 300)
        self.assertEqual(payload["kpis"]["wow_pct"], 0.5)
        self.assertEqual(payload["kpis"]["yoy_pct"], 1.0)
        self.assertEqual(payload["meta"]["revenue_basis"], report.REVENUE_BASIS_NOTE)


if __name__ == "__main__":
    unittest.main()
