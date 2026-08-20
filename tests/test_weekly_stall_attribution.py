import importlib.util
import unittest
from collections import defaultdict

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "profile_weekly_meeting_data.py"
SPEC = importlib.util.spec_from_file_location("profile_weekly_meeting_data", MODULE_PATH)
profile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(profile)


class WeeklyStallAttributionTest(unittest.TestCase):
    def catalog_for(self, names: dict[str, str]) -> dict[str, dict[str, set[str]]]:
        by_name: dict[str, set[str]] = defaultdict(set)
        by_clean_name: dict[str, set[str]] = defaultdict(set)
        for name, stall in names.items():
            for key in profile.dish_match_keys(name):
                by_name[key].add(stall)
                by_clean_name[key].add(stall)
        return {"by_name": by_name, "by_clean_name": by_clean_name}

    def test_resolve_stall_matches_dish_names_with_parenthetical_sales_copy(self) -> None:
        catalog = self.catalog_for({"西北手工凉皮": "面食·小吃"})

        stall, status = profile.resolve_stall("西北手工凉皮（BTV热播推荐）", catalog)

        self.assertEqual(stall, "面食·小吃")
        self.assertEqual(status, "matched")

    def test_resolve_stall_matches_catalog_names_with_quality_prefix(self) -> None:
        catalog = self.catalog_for({"高品质大串羔羊肉": "高品质烤羊肉"})

        stall, status = profile.resolve_stall("大串羔羊肉（精选小肥羔羊肉穿制）", catalog)

        self.assertEqual(stall, "高品质烤羊肉")
        self.assertEqual(status, "matched")

    def test_resolve_stall_from_names_uses_linked_name_when_display_name_is_unmatched(self) -> None:
        catalog = self.catalog_for({"烤羊腿肉": "高品质烤羊肉"})

        stall, status, source = profile.resolve_stall_from_names(
            "内蒙羊腿肉（精选羊后腿肉穿制）",
            "烤羊腿肉",
            catalog,
        )

        self.assertEqual(stall, "高品质烤羊肉")
        self.assertEqual(status, "matched")
        self.assertEqual(source, "linked_dish_name")

    def test_resolve_stall_from_names_preserves_primary_match_when_names_conflict(self) -> None:
        catalog = self.catalog_for({
            "酸辣海带丝": "爽口凉菜",
            "外-酸辣海带丝": "外卖品项",
        })

        stall, status, source = profile.resolve_stall_from_names(
            "酸辣海带丝",
            "外-酸辣海带丝",
            catalog,
        )

        self.assertEqual(stall, "爽口凉菜")
        self.assertEqual(status, "matched")
        self.assertEqual(source, "dish_name")

    def test_resolve_stall_from_names_reports_unmatched_when_neither_name_matches(self) -> None:
        catalog = self.catalog_for({"烤羊腿肉": "高品质烤羊肉"})

        stall, status, source = profile.resolve_stall_from_names("辣炒花甲", "农家辣炒花蛤", catalog)

        self.assertEqual(stall, "未匹配菜品库")
        self.assertEqual(status, "unmatched")
        self.assertEqual(source, "none")

    def test_product_sales_per_10k_uses_linked_name_and_matching_all_channel_scope(self) -> None:
        catalog = self.catalog_for({
            "蒜蓉生蚝": "海鲜",
            "鸡翅": "烧烤",
        })
        dish_rows = [
            {
                "门店": "甲店",
                "菜品名称": "蒜蓉生蚝特惠",
                "关联菜品名称": "蒜蓉生蚝",
                "订单分类": "店内销售",
                "菜品销售数量": "12",
            },
            {
                "门店": "甲店",
                "菜品名称": "标准生蚝",
                "关联菜品名称": "蒜蓉生蚝",
                "订单分类": "外卖",
                "菜品销售数量": "8",
            },
            {
                "门店": "乙店",
                "菜品名称": "鸡翅",
                "关联菜品名称": "",
                "订单分类": "自提",
                "菜品销售数量": "5",
            },
        ]
        revenue = {
            ("current", "甲店"): 10_000,
            ("current", "乙店"): 5_000,
            ("current", profile.ALL_STORES_LABEL): 15_000,
        }

        rows = profile.aggregate_product_sales_per_10k_rows(
            dish_rows,
            catalog,
            revenue,
            period_key="current",
            period_label="当前区间",
        )

        by_key = {(row["门店名称"], row["产品名称"]): row for row in rows}
        oysters = by_key[("甲店", "蒜蓉生蚝")]
        self.assertEqual(oysters["档口"], "海鲜")
        self.assertEqual(oysters["quantity"], 20)
        self.assertEqual(oysters["order_revenue"], 10_000)
        self.assertEqual(oysters["units_per_10k"], 20)
        self.assertEqual(
            set(oysters["search_names"].split("\u001f")),
            {"蒜蓉生蚝", "蒜蓉生蚝特惠", "标准生蚝"},
        )

        fallback = by_key[("乙店", "鸡翅")]
        self.assertEqual(fallback["档口"], "烧烤")
        self.assertEqual(fallback["units_per_10k"], 10)

        all_oysters = by_key[(profile.ALL_STORES_LABEL, "蒜蓉生蚝")]
        self.assertEqual(all_oysters["quantity"], 20)
        self.assertAlmostEqual(all_oysters["units_per_10k"], 20 / 15_000 * 10_000, places=4)

    def test_product_sales_per_10k_marks_conflicting_or_missing_stalls_unmatched(self) -> None:
        catalog = self.catalog_for({
            "展示名甲": "档口甲",
            "展示名乙": "档口乙",
        })
        rows = profile.aggregate_product_sales_per_10k_rows(
            [
                {"门店": "甲店", "菜品名称": "展示名甲", "关联菜品名称": "统一产品", "菜品销售数量": "2"},
                {"门店": "甲店", "菜品名称": "展示名乙", "关联菜品名称": "统一产品", "菜品销售数量": "3"},
                {"门店": "甲店", "菜品名称": "无库产品", "关联菜品名称": "", "菜品销售数量": "1"},
            ],
            catalog,
            {("current", "甲店"): 10_000, ("current", profile.ALL_STORES_LABEL): 10_000},
            period_key="current",
            period_label="当前区间",
        )

        by_name = {row["产品名称"]: row for row in rows if row["门店名称"] == "甲店"}
        self.assertEqual(by_name["统一产品"]["档口"], "未匹配")
        self.assertEqual(by_name["无库产品"]["档口"], "未匹配")


if __name__ == "__main__":
    unittest.main()
