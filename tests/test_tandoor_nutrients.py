import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from tandoor_mcp.nutrients import build_properties, map_types  # noqa: E402

TYPES = [
    {"id": 1, "name": "Energy", "unit": "kJ", "fdc_id": 1008},
    {"id": 2, "name": "Eiweiß", "unit": "g", "fdc_id": None},
    {"id": 3, "name": "Protein (old)", "unit": "g", "fdc_id": None},
    {"id": 4, "name": "Zucker", "unit": "g", "fdc_id": None},
]


class NutrientsTest(unittest.TestCase):
    def test_types_by_fdc_id_then_name(self):
        found = map_types(TYPES)
        self.assertEqual(found["kcal"]["id"], 1)
        self.assertEqual(found["protein_g"]["id"], 2)
        self.assertNotIn("fat_g", found)

    def test_values_update_add_and_keep_the_rest(self):
        types = map_types(TYPES)
        existing = [
            {"id": 10, "property_amount": 5, "property_type": {"id": 2, "name": "Eiweiß"}},
            {"id": 11, "property_amount": 9, "property_type": {"id": 4, "name": "Zucker"}},
        ]
        out = build_properties(existing, types, {"kcal": 100, "protein_g": 3})
        by_type = {p["property_type"]["id"]: p for p in out}
        self.assertEqual(by_type[2], {"id": 10, "property_amount": 3, "property_type": {"id": 2, "name": "Eiweiß"}})
        self.assertEqual(by_type[4]["property_amount"], 9)
        # The kcal type is kept in kJ, so the value is converted.
        self.assertEqual(by_type[1]["property_amount"], 418.4)
        self.assertNotIn("id", by_type[1])
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
