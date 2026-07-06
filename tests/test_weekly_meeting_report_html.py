import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_weekly_meeting_report_html.py"
SPEC = importlib.util.spec_from_file_location("generate_weekly_meeting_report_html", MODULE_PATH)
report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class WeeklyMeetingReportHtmlTest(unittest.TestCase):
    def test_payload_builds_hourly_revenue_entities_without_daypart_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp)
            (input_dir / "weekly_meeting_summary.json").write_text(
                json.dumps(
                    {
                        "meta": {
                            "coverage_start": "2026/06/22",
                            "coverage_end": "2026/07/05",
                            "target_windows": {
                                "current": {"label": "本周", "start": "2026/06/29", "end": "2026/07/05"},
                                "previous": {"label": "环比周", "start": "2026/06/22", "end": "2026/06/28"},
                                "yoy": {"label": "同比周", "start": "2025/06/30", "end": "2025/07/06"},
                            },
                            "processed_rows": 4,
                            "store_count": 2,
                            "outputs": [],
                        },
                        "data_gaps": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            write_csv(
                input_dir / "weekly_store_comparison.csv",
                [
                    {
                        "门店名称": "麦家小馆（甲店）",
                        "current_net_revenue": 300,
                        "previous_net_revenue": 200,
                        "yoy_net_revenue": 250,
                        "current_positive_orders": 10,
                    },
                    {
                        "门店名称": "麦家小馆（乙店）",
                        "current_net_revenue": 100,
                        "previous_net_revenue": 80,
                        "yoy_net_revenue": 90,
                        "current_positive_orders": 5,
                    },
                ],
            )
            write_csv(
                input_dir / "star_problem_stores.csv",
                [
                    {"门店名称": "麦家小馆（甲店）", "segment": "明星门店", "reason": ""},
                    {"门店名称": "麦家小馆（乙店）", "segment": "问题门店", "reason": ""},
                ],
            )
            write_csv(input_dir / "store_driver_summary.csv", [{"门店名称": "麦家小馆（甲店）", "basis": "环比"}])
            write_csv(input_dir / "weekly_store_channel_metrics.csv", [{"period": "本周", "门店名称": "麦家小馆（甲店）", "channel": "堂食", "net_revenue": 300}])
            write_csv(
                input_dir / "weekly_store_daypart_metrics.csv",
                [
                    {"period": "本周", "门店名称": "麦家小馆（甲店）", "餐段": "午餐", "时段": "12", "net_revenue": 120},
                    {"period": "本周", "门店名称": "麦家小馆（甲店）", "餐段": "晚餐", "时段": "12", "net_revenue": 80},
                    {"period": "本周", "门店名称": "麦家小馆（乙店）", "餐段": "夜餐", "时段": "23", "net_revenue": 50},
                    {"period": "环比周", "门店名称": "麦家小馆（甲店）", "餐段": "晚餐", "时段": "12", "net_revenue": 70},
                ],
            )
            write_csv(input_dir / "weekly_store_metrics.csv", [{"week_label": "06/29-07/05", "week_end": "2026/07/05", "门店名称": "麦家小馆（甲店）", "net_revenue": 300}])

            payload = report.build_payload(input_dir, "麦家小馆")

        entities = payload["hourly_revenue_entities"]
        all_store = entities[0]
        first_store = next(entity for entity in entities if entity["key"] == "麦家小馆（甲店）")
        self.assertEqual(all_store["label"], "全体门店")
        self.assertEqual(len(all_store["rows"]), 24)
        self.assertEqual(all_store["rows"][12]["hour"], "12")
        self.assertEqual(all_store["rows"][12]["net_revenue"], 200)
        self.assertEqual(all_store["rows"][23]["net_revenue"], 50)
        self.assertEqual(first_store["rows"][12]["net_revenue"], 200)
        self.assertNotIn("餐段", all_store["rows"][12])

    def test_template_uses_hourly_bar_chart_controls_instead_of_heatmap(self) -> None:
        self.assertIn("hourlyStoreSelect", report.HTML_TEMPLATE)
        self.assertIn("hourlyRevenueBar", report.HTML_TEMPLATE)
        self.assertIn("renderHourlyRevenueBar", report.HTML_TEMPLATE)
        self.assertNotIn('id="heatmap"', report.HTML_TEMPLATE)
        self.assertNotIn("renderHeatmap()", report.HTML_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
