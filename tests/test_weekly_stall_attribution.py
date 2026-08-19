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


if __name__ == "__main__":
    unittest.main()
