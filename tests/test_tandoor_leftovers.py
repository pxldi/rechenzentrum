import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from tandoor_mcp import leftovers as lo  # noqa: E402

TODAY = date(2026, 9, 18)
PRODUCE = {"id": 19, "name": "Obst & Gemüse", "open_data_slug": "category-produce"}
CHEESE = {"id": 21, "name": "Käse", "open_data_slug": "category-cheese"}
NOODLES = {"id": 1, "name": "Nudeln & Reis", "open_data_slug": "category-noodles"}
OFENGEMUESE = {"id": 24, "name": "Ofengemüse mit Feta"}
PASTA = {"id": 17, "name": "One-Pot Tomaten-Spinat-Pasta"}


def entry(eid, food, amount, unit=None, recipe=None, checked=True, completed="2026-09-15T18:07:01+02:00"):
    return {
        "id": eid,
        "food": food,
        "amount": amount,
        "unit": {"name": unit} if unit else None,
        "checked": checked,
        "completed_at": completed if checked else None,
        "list_recipe_data": {"recipe_data": recipe} if recipe else None,
    }


FETA = {"id": 1, "name": "Feta", "supermarket_category": CHEESE}
NUDELN = {"id": 2, "name": "Nudeln", "supermarket_category": NOODLES}
ZITRONE = {"id": 3, "name": "Zitrone", "supermarket_category": PRODUCE}
BANANEN = {"id": 4, "name": "Bananen", "supermarket_category": PRODUCE}
PETERSILIE = {"id": 5, "name": "Petersilie", "supermarket_category": PRODUCE}
SAFRAN = {"id": 6, "name": "Safran", "supermarket_category": {"name": "Gewürze"}}


class PackSizes(unittest.TestCase):
    def test_default_pack_prefers_the_longest_fragment(self):
        self.assertEqual(lo.default_pack("Räuchertofu"), (200, "g"))
        self.assertEqual(lo.default_pack("rote Linsen"), (500, "g"))
        self.assertIsNone(lo.default_pack("Safran"))

    def test_conversions_read_either_direction(self):
        convs = [
            {"food": {"id": 1}, "base_amount": 1, "base_unit": {"name": "Packung"}, "converted_amount": 150, "converted_unit": {"name": "g"}},
            {"food": {"id": 2}, "base_amount": 1000, "base_unit": {"name": "g"}, "converted_amount": 2, "converted_unit": {"name": "Packung"}},
            {"food": None, "base_amount": 1, "base_unit": {"name": "cup"}, "converted_amount": 5, "converted_unit": {"name": "oz"}},
        ]
        self.assertEqual(lo.pack_sizes_from_conversions(convs), {1: (150.0, "g"), 2: (500.0, "g")})

    def test_tandoor_pack_beats_default_and_mismatched_family_is_unknown(self):
        self.assertEqual(lo.resolve_pack(FETA, "mass", {1: (150.0, "g")}), (150.0, "tandoor"))
        self.assertEqual(lo.resolve_pack(FETA, "mass", {}), (200.0, "default"))
        self.assertEqual(lo.resolve_pack(FETA, "volume", {}), (None, "unknown"))
        self.assertEqual(lo.resolve_pack(ZITRONE, "stück", {}), (1.0, "unit"))


class ShelfLife(unittest.TestCase):
    def test_category_name_and_food_overrides(self):
        self.assertEqual(lo.shelf_life_days(FETA), 14)
        self.assertEqual(lo.shelf_life_days(ZITRONE), 7)
        self.assertEqual(lo.shelf_life_days(PETERSILIE), 4)
        self.assertEqual(lo.shelf_life_days(SAFRAN), 180)
        self.assertEqual(lo.shelf_life_days({"name": "Tofu", "supermarket_category": {"name": "Feinkost & Tofu"}}), 10)


class Leftovers(unittest.TestCase):
    def test_uncooked_recipe_is_reserved_not_free(self):
        items = lo.compute_leftovers([entry(1, FETA, 200, "g", OFENGEMUESE)], {}, {}, TODAY)
        self.assertEqual(len(items), 1)
        feta = items[0]
        self.assertEqual((feta["on_hand"], feta["free"]), (200.0, 0.0))
        self.assertEqual(feta["reserved_for"], ["Ofengemüse mit Feta"])
        self.assertEqual(feta["reserved_for_ids"], [24])
        self.assertTrue(feta["estimate"])
        self.assertEqual(feta["pack"]["source"], "default")

    def test_two_recipes_share_one_pack(self):
        entries = [entry(1, NUDELN, 250, "g", PASTA), entry(2, NUDELN, 250, "g", OFENGEMUESE)]
        cooked = {17: [date(2026, 9, 16)], 24: [date(2026, 9, 17)]}
        items = lo.compute_leftovers(entries, {}, cooked, TODAY)
        self.assertEqual(items, [])

    def test_one_recipe_cooked_leaves_the_rest_of_the_pack(self):
        entries = [entry(1, NUDELN, 250, "g", PASTA)]
        items = lo.compute_leftovers(entries, {}, {17: [date(2026, 9, 16)]}, TODAY)
        self.assertEqual((items[0]["on_hand"], items[0]["free"]), (250.0, 250.0))
        self.assertEqual(items[0]["reserved_for"], [])

    def test_cooking_before_the_purchase_does_not_count(self):
        entries = [entry(1, NUDELN, 250, "g", PASTA)]
        items = lo.compute_leftovers(entries, {}, {17: [date(2026, 9, 1)]}, TODAY)
        self.assertEqual((items[0]["on_hand"], items[0]["free"]), (500.0, 250.0))
        self.assertEqual(items[0]["reserved_for"], ["One-Pot Tomaten-Spinat-Pasta"])

    def test_kg_and_g_add_up_and_tandoor_pack_is_not_an_estimate(self):
        entries = [entry(1, NUDELN, 0.25, "kg", PASTA), entry(2, NUDELN, 300, "g", OFENGEMUESE)]
        cooked = {17: [date(2026, 9, 16)], 24: [date(2026, 9, 16)]}
        items = lo.compute_leftovers(entries, {2: (1000.0, "g")}, cooked, TODAY)
        self.assertEqual((items[0]["on_hand"], items[0]["unit"]), (450.0, "g"))
        self.assertFalse(items[0]["estimate"])

    def test_pieces_round_up_and_off_list_counts_whole(self):
        entries = [entry(1, ZITRONE, 0.5, None, OFENGEMUESE), entry(2, BANANEN, 6, None)]
        items = lo.compute_leftovers(entries, {}, {24: [date(2026, 9, 16)]}, TODAY)
        by = {i["food"]: i for i in items}
        self.assertEqual(by["Zitrone"]["free"], 0.5)
        self.assertEqual(by["Zitrone"]["pack"]["source"], "unit")
        self.assertFalse(by["Zitrone"]["estimate"])
        self.assertEqual(by["Zitrone"]["unit"], "Stück")
        self.assertEqual((by["Bananen"]["on_hand"], by["Bananen"]["free"]), (6.0, 6.0))

    def test_expired_food_drops_out(self):
        entries = [entry(1, PETERSILIE, 0.5, "Bund", OFENGEMUESE, completed="2026-09-10T10:00:00+02:00")]
        self.assertEqual(lo.compute_leftovers(entries, {}, {24: [date(2026, 9, 11)]}, TODAY), [])
        fresh = lo.compute_leftovers([entry(1, PETERSILIE, 0.5, "Bund", OFENGEMUESE)], {}, {}, TODAY)
        self.assertEqual((fresh[0]["unit"], fresh[0]["on_hand"]), ("Bund", 1.0))

    def test_unknown_pack_reports_need_instead_of_guessing(self):
        items = lo.compute_leftovers([entry(1, SAFRAN, 0.5, "g", OFENGEMUESE)], {}, {}, TODAY)
        self.assertIsNone(items[0]["on_hand"])
        self.assertEqual(items[0]["pack"]["source"], "unknown")
        self.assertEqual(items[0]["needed"], 0.5)

    def test_unchecked_entries_are_not_purchases(self):
        self.assertEqual(lo.compute_leftovers([entry(1, FETA, 200, "g", checked=False)], {}, {}, TODAY), [])

    def test_sorted_by_expiry(self):
        entries = [entry(1, FETA, 100, "g", PASTA), entry(2, ZITRONE, 0.5, None, PASTA)]
        items = lo.compute_leftovers(entries, {}, {17: [date(2026, 9, 16)]}, TODAY)
        self.assertEqual([(i["food"], i["expires_in_days"]) for i in items], [("Zitrone", 4), ("Feta", 11)])


class CookedDates(unittest.TestCase):
    def test_future_meal_plans_do_not_count(self):
        logs = [{"recipe": 17, "created_at": "2026-09-10T19:00:00+02:00"}]
        plans = [
            {"recipe": {"id": 24}, "from_date": "2026-09-17T00:00:00+02:00"},
            {"recipe": {"id": 24}, "from_date": "2026-09-20T00:00:00+02:00"},
            {"recipe": None, "from_date": "2026-09-17T00:00:00+02:00"},
        ]
        self.assertEqual(lo.cooked_dates(logs, plans, TODAY), {17: [date(2026, 9, 10)], 24: [date(2026, 9, 17)]})


class Ranking(unittest.TestCase):
    def recipes(self):
        def r(rid, name, *foods):
            return {"id": rid, "name": name, "servings": 2, "keywords": [], "steps": [{"ingredients": [{"food": f} for f in foods]}]}

        return [
            r(17, "Pasta", NUDELN, FETA, {"id": 9, "name": "Tomaten"}),
            r(24, "Ofengemüse", FETA, ZITRONE),
            r(30, "Kuchen", {"id": 10, "name": "Mehl"}),
        ]

    def leftovers(self):
        entries = [entry(1, FETA, 100, "g", PASTA), entry(2, ZITRONE, 0.5, None, PASTA), entry(3, NUDELN, 250, "g", PASTA)]
        return lo.compute_leftovers(entries, {}, {17: [date(2026, 9, 16)]}, TODAY)

    def test_perishables_weigh_more_and_recent_recipes_are_skipped(self):
        ranked = lo.rank_recipes(self.recipes(), self.leftovers(), {17: [date(2026, 9, 16)]}, TODAY)
        self.assertEqual([x["name"] for x in ranked], ["Ofengemüse"])
        self.assertEqual(ranked[0]["uses"], ["Feta", "Zitrone"])
        self.assertEqual(ranked[0]["missing"], [])

    def test_reserved_food_counts_for_its_own_recipe(self):
        items = lo.compute_leftovers([entry(1, FETA, 200, "g", OFENGEMUESE), entry(2, ZITRONE, 1, None, OFENGEMUESE)], {}, {}, TODAY)
        ranked = lo.rank_recipes(self.recipes(), items, {}, TODAY)
        self.assertEqual([(x["name"], x["uses"]) for x in ranked], [("Ofengemüse", ["Feta", "Zitrone"])])

    def test_a_recipe_using_nothing_is_not_listed(self):
        ranked = lo.rank_recipes(self.recipes(), self.leftovers(), {}, TODAY)
        # Ofengemüse uses two perishables; Pasta uses one plus dry noodles.
        self.assertEqual([x["name"] for x in ranked], ["Ofengemüse", "Pasta"])
        self.assertEqual(ranked[1]["missing"], ["Tomaten"])
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])


if __name__ == "__main__":
    unittest.main()
