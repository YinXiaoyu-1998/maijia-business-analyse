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

    def test_payload_uses_daypart_attribution_instead_of_stall_attribution(self) -> None:
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
                            "store_count": 1,
                            "outputs": [],
                            "daypart_attribution": {"enabled": True, "basis": "测试时段归因"},
                        },
                        "data_gaps": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            write_csv(
                input_dir / "weekly_store_comparison.csv",
                [{"门店名称": "麦家小馆（甲店）", "current_net_revenue": 300, "previous_net_revenue": 200, "yoy_net_revenue": 250, "current_positive_orders": 10}],
            )
            write_csv(input_dir / "star_problem_stores.csv", [{"门店名称": "麦家小馆（甲店）", "segment": "明星门店", "reason": ""}])
            write_csv(input_dir / "store_driver_summary.csv", [{"门店名称": "麦家小馆（甲店）", "basis": "环比"}])
            write_csv(input_dir / "weekly_store_channel_metrics.csv", [{"period": "本周", "门店名称": "麦家小馆（甲店）", "channel": "堂食", "net_revenue": 300}])
            write_csv(input_dir / "weekly_store_daypart_metrics.csv", [{"period": "本周", "门店名称": "麦家小馆（甲店）", "餐段": "午餐", "时段": "12", "net_revenue": 120}])
            write_csv(input_dir / "weekly_store_metrics.csv", [{"week_label": "06/29-07/05", "week_end": "2026/07/05", "门店名称": "麦家小馆（甲店）", "net_revenue": 300}])
            write_csv(
                input_dir / "weekly_store_daypart_driver_summary.csv",
                [
                    {
                        "门店名称": "麦家小馆（甲店）",
                        "basis": "环比",
                        "top_negative_daypart": "午餐",
                        "top_negative_time_slot": "12:00-13:00",
                        "top_negative_net_revenue_delta": -50,
                        "top_positive_daypart": "晚餐",
                        "top_positive_time_slot": "18:00-19:00",
                        "top_positive_net_revenue_delta": 80,
                        "daypart_signal": "午餐 12:00-13:00 -50 / 晚餐 18:00-19:00 +80",
                    }
                ],
            )
            write_csv(
                input_dir / "weekly_store_daypart_comparison.csv",
                [
                    {"门店名称": "麦家小馆（甲店）", "餐段": "午餐", "时段": "12:00-13:00", "current_net_revenue": 100, "previous_net_revenue": 150, "wow_net_revenue_delta": -50},
                    {"门店名称": "麦家小馆（甲店）", "餐段": "晚餐", "时段": "18:00-19:00", "current_net_revenue": 180, "previous_net_revenue": 100, "wow_net_revenue_delta": 80},
                ],
            )

            payload = report.build_payload(input_dir, "麦家小馆")

        self.assertIn("daypart_attribution", payload)
        self.assertNotIn("stall_attribution", payload)
        self.assertEqual(payload["comparison"][0]["top_daypart_signal"], "午餐 12:00-13:00 -50 / 晚餐 18:00-19:00 +80")
        self.assertEqual(payload["daypart_attribution"]["drivers"][0]["negative_slots"][0]["时段"], "12:00-13:00")
        self.assertEqual(payload["daypart_attribution"]["drivers"][0]["positive_slots"][0]["时段"], "18:00-19:00")

    def test_trend_template_uses_standard_extrema_palette_and_comparison_dash(self) -> None:
        self.assertIn("colors.yellow", report.HTML_TEMPLATE)
        self.assertIn("colors.minimum", report.HTML_TEMPLATE)
        self.assertIn("colors.maximum", report.HTML_TEMPLATE)
        self.assertIn("'7 5'", report.HTML_TEMPLATE)

    def test_template_replaces_stall_attribution_with_daypart_attribution(self) -> None:
        self.assertIn("daypartAttribution", report.HTML_TEMPLATE)
        self.assertIn("renderDaypartAttribution", report.HTML_TEMPLATE)
        self.assertIn("主要时段信号", report.HTML_TEMPLATE)
        self.assertNotIn("stallAttribution", report.HTML_TEMPLATE)
        self.assertNotIn("主要档口信号", report.HTML_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
