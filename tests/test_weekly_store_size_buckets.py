import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "scripts" / "profile_weekly_meeting_data.py"
REPORT_PATH = ROOT / "scripts" / "generate_weekly_meeting_report_html.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


profile = load_module("profile_weekly_meeting_data", PROFILE_PATH)
report = load_module("generate_weekly_meeting_report_html", REPORT_PATH)


class WeeklyStoreSizeBucketTest(unittest.TestCase):
    def test_classifies_stores_against_their_own_size_bucket_median(self) -> None:
        rows = [
            {
                "门店名称": "麦家小馆（荣京道店）",
                "current_net_revenue": 2000,
                "wow_net_revenue_pct": 0.05,
                "yoy_net_revenue_pct": 0,
                "current_discount_rate": 0.1,
                "current_post_discount_aov": 100,
            },
            {
                "门店名称": "麦家小馆（国粹苑店）",
                "current_net_revenue": 1000,
                "wow_net_revenue_pct": 0.05,
                "yoy_net_revenue_pct": 0,
                "current_discount_rate": 0.1,
                "current_post_discount_aov": 100,
            },
            {
                "门店名称": "麦家小馆（龙玥城店）",
                "current_net_revenue": 200,
                "wow_net_revenue_pct": 0.05,
                "yoy_net_revenue_pct": 0,
                "current_discount_rate": 0.1,
                "current_post_discount_aov": 100,
            },
            {
                "门店名称": "麦家小馆（文化园店）",
                "current_net_revenue": 100,
                "wow_net_revenue_pct": 0.05,
                "yoy_net_revenue_pct": 0,
                "current_discount_rate": 0.1,
                "current_post_discount_aov": 100,
            },
        ]

        classified = {row["门店名称"]: row for row in profile.classify_stores(rows)}

        self.assertEqual(classified["麦家小馆（荣京道店）"]["store_size"], "大店")
        self.assertEqual(classified["麦家小馆（龙玥城店）"]["store_size"], "小店")
        self.assertEqual(classified["麦家小馆（荣京道店）"]["segment"], "明星门店")
        self.assertEqual(classified["麦家小馆（国粹苑店）"]["segment"], "成长观察")
        self.assertEqual(classified["麦家小馆（龙玥城店）"]["segment"], "明星门店")
        self.assertEqual(classified["麦家小馆（文化园店）"]["segment"], "成长观察")
        self.assertEqual(classified["麦家小馆（荣京道店）"]["revenue_threshold"], 1500)
        self.assertEqual(classified["麦家小馆（龙玥城店）"]["revenue_threshold"], 150)

    def test_report_template_exposes_store_size_bucket_surfaces(self) -> None:
        self.assertIn("bucketSegmentSummary", report.HTML_TEMPLATE)
        self.assertIn("renderBucketedRevenueRanking", report.HTML_TEMPLATE)
        self.assertIn("renderBucketedScatter", report.HTML_TEMPLATE)
        self.assertIn("门店类型", report.HTML_TEMPLATE)
        self.assertIn("大店", report.HTML_TEMPLATE)
        self.assertIn("小店", report.HTML_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
