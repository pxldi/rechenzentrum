import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from tandoor_mcp.foods import base_name, match_food  # noqa: E402

FOODS = [
    {"id": 1, "name": "Zwiebel"},
    {"id": 2, "name": "Ingwer"},
    {"id": 3, "name": "Tomaten"},
    {"id": 4, "name": "Tomaten, passiert"},
    {"id": 5, "name": "Knoblauch"},
    {"id": 6, "name": "Kichererbsen"},
]


class MatchFoodTest(unittest.TestCase):
    def test_same_name_up_to_case_and_spacing_is_used(self):
        self.assertEqual(match_food("  zwiebel ", FOODS), ({"id": 1, "name": "Zwiebel"}, []))

    def test_plural_is_the_same_food(self):
        food, similar = match_food("Zwiebeln", FOODS)
        self.assertEqual(food["id"], 1)
        self.assertEqual(similar, [])

    def test_qualified_name_asks_instead_of_creating(self):
        food, similar = match_food("Zwiebel, klein", FOODS)
        self.assertIsNone(food)
        self.assertEqual([f["id"] for f in similar], [1])
        food, similar = match_food("Ingwer (frisch)", FOODS)
        self.assertIsNone(food)
        self.assertIn(2, [f["id"] for f in similar])

    def test_a_qualifier_is_not_silently_dropped(self):
        food, similar = match_food("Tomaten, gehackt", FOODS)
        self.assertIsNone(food)
        self.assertEqual({f["id"] for f in similar}, {3, 4})

    def test_near_spelling_with_the_same_qualifier_is_the_same_food(self):
        food, _ = match_food("Tomaten, passierte", FOODS)
        self.assertEqual(food["id"], 4)

    def test_unqualified_name_does_not_take_a_qualified_food(self):
        food, similar = match_food("Tomate", FOODS)
        self.assertEqual(food["id"], 3)

    def test_unrelated_name_is_new(self):
        self.assertEqual(match_food("Paprika", FOODS), (None, []))
        self.assertEqual(match_food("", FOODS), (None, []))

    def test_base_name(self):
        self.assertEqual(base_name("Zwiebel, klein"), "zwiebel")
        self.assertEqual(base_name("Ingwer (frisch)"), "ingwer")
        self.assertEqual(base_name("Kichererbsen"), "kichererbsen")


if __name__ == "__main__":
    unittest.main()
