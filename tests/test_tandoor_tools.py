"""The recipe server's tools against a fake Tandoor API.

Needs the MCP SDK, so it runs inside the homelab-mcp image (see the image
workflow) and is skipped where the SDK is not installed. The fake answers the
way Tandoor 2.6 does for the endpoints these tools use.
"""

import asyncio
import importlib.util
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

HAVE_SDK = all(importlib.util.find_spec(m) is not None for m in ("mcp", "httpx", "pydantic"))


class FakeTandoor:
    def __init__(self):
        self.foods = {1: {"id": 1, "name": "Zwiebel"}, 2: {"id": 2, "name": "Ingwer"}, 3: {"id": 3, "name": "Salz"}}
        self.entries = {10: {"id": 10, "food": {"name": "Zwiebel"}, "amount": 2, "unit": None, "checked": False}}
        self.property_types = [{"id": 31, "name": "Kalorien", "unit": "kcal", "fdc_id": 1008, "order": 2}, {"id": 32, "name": "Salz", "unit": "g", "fdc_id": None}]
        self.recipes = {5: {"id": 5, "name": "Chili"}}
        self.keywords = {7: {"id": 7, "name": "test"}}
        self.conversions = {}
        self.next_id = 100
        self.calls = []

    def handle(self, request):
        import httpx

        path = request.url.path.removeprefix("/api")
        method = request.method
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/"):
            # Only the image endpoint takes a form; keep its text fields.
            body = dict(re.findall(rb'name="([^"]+)"\r\n\r\n([^\r]*)', request.content))
            body = {k.decode(): v.decode() for k, v in body.items()}
        else:
            body = json.loads(request.content) if request.content else None
        self.calls.append((method, path, body))
        q = request.url.params

        if path == "/recipe/" and method == "GET":
            return httpx.Response(200, json={"results": [{"id": 5, "name": "Chili", "keywords": [{"id": 7, "label": "meal-prep"}]}]})
        if path == "/keyword/" and method == "GET":
            return httpx.Response(200, json={"results": [{"id": 7, "name": "meal-prep"}], "next": None})
        if path == "/food/" and method == "GET":
            word = (q.get("query") or "").lower()
            hits = [f for f in self.foods.values() if word in f["name"].lower() or f["name"].lower() in word]
            # Like Tandoor, the recipe count is only there with extended=1.
            if q.get("extended") == "1":
                hits = [{**f, "numrecipe": 4} for f in hits]
            return httpx.Response(200, json={"results": hits})
        for kind, store in (("recipe", self.recipes), ("keyword", self.keywords)):
            prefix = f"/{kind}/"
            if path.startswith(prefix) and path.count("/") == 3:
                oid = int(path.split("/")[2])
                if oid not in store:
                    return httpx.Response(404, json={"detail": "Not found."})
                if method == "DELETE":
                    del store[oid]
                    return httpx.Response(204)
                return httpx.Response(200, json=store[oid])
        if path == "/shopping-list-entry/" and method == "POST":
            name = body["food"]["name"]
            if "id" not in body["food"] and not any(f["name"] == name for f in self.foods.values()):
                fid = self.next_id
                self.next_id += 1
                self.foods[fid] = {"id": fid, "name": name}
            eid = self.next_id
            self.next_id += 1
            self.entries[eid] = {"id": eid, "food": {"name": name}, "amount": body["amount"], "unit": body["unit"], "checked": False}
            return httpx.Response(201, json=self.entries[eid])
        if path == "/shopping-list-entry/bulk/":
            for i in body["ids"]:
                self.entries[i]["checked"] = body["checked"]
            return httpx.Response(200, json=body)
        if path.startswith("/shopping-list-entry/") and path.count("/") == 3:
            eid = int(path.split("/")[2])
            if eid not in self.entries:
                return httpx.Response(404, json={"detail": "Not found."})
            if method == "DELETE":
                del self.entries[eid]
                return httpx.Response(204)
            return httpx.Response(200, json=self.entries[eid])
        if path.endswith("/image/") and method == "PUT":
            if not ctype.startswith("multipart/"):
                return httpx.Response(415, json={"detail": f'Unsupported media type "{ctype}" in request.'})
            ok = body["image_url"].endswith(".jpg")
            return httpx.Response(200, json={"image": "/media/x.jpg" if ok else None, "image_url": body["image_url"]})
        if path == "/property-type/" and method == "GET":
            return httpx.Response(200, json={"results": self.property_types, "next": None})
        if path == "/property-type/" and method == "POST":
            t = {"id": self.next_id, **body}
            self.next_id += 1
            self.property_types.append(t)
            return httpx.Response(201, json=t)
        if path == "/unit/" and method == "GET":
            return httpx.Response(200, json={"results": [{"id": 1, "name": "g"}], "next": None})
        if path == "/unit/" and method == "POST":
            return httpx.Response(201, json={"id": 2, **body})
        if path.startswith("/food/") and path.count("/") == 3:
            fid = int(path.split("/")[2])
            if method == "PATCH":
                props = [{**p, "id": p.get("id") or 900 + i} for i, p in enumerate(body["properties"])]
                self.foods[fid] = {**self.foods[fid], **body, "properties": props}
            return httpx.Response(200, json=self.foods[fid])
        if path == "/unit-conversion/" and method == "GET":
            fid = int(q.get("food_id") or 0)
            return httpx.Response(200, json={"results": [c for c in self.conversions.values() if c["food"]["id"] == fid], "next": None})
        if path == "/unit-conversion/" and method == "POST":
            cid = self.next_id
            self.next_id += 1
            self.conversions[cid] = {"id": cid, **body}
            return httpx.Response(201, json=self.conversions[cid])
        if path.startswith("/unit-conversion/") and method == "PATCH":
            cid = int(path.split("/")[2])
            self.conversions[cid] = {"id": cid, **body}
            return httpx.Response(200, json=self.conversions[cid])
        if path == "/meal-type/":
            return httpx.Response(200, json={"results": [{"id": 1, "name": "Dinner"}]})
        if path == "/meal-plan/" and method == "POST":
            return httpx.Response(201, json={"id": 50, "title": body["title"], "shopping": False})
        return httpx.Response(500, json={"unexpected": f"{method} {path}"})


@unittest.skipUnless(HAVE_SDK, "needs the MCP SDK (run inside the homelab-mcp image)")
class TandoorToolsTest(unittest.TestCase):
    def setUp(self):
        import httpx

        with mock.patch.dict(os.environ, {"TANDOOR_TOKEN": "t"}):
            from tandoor_mcp import server

        self.s = server
        self.fake = FakeTandoor()
        transport = httpx.MockTransport(self.fake.handle)
        patcher = mock.patch.object(
            server, "_client", lambda: httpx.AsyncClient(base_url="http://tandoor.test/api", transport=transport)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_(self, coro):
        return asyncio.run(coro)

    def test_search_recipes_returns_list_keywords(self):
        out = self.run_(self.s.search_recipes(query="", keyword_ids=[], keywords=["Meal-Prep"], match_all_keywords=False, limit=10))
        self.assertEqual(out[0]["keywords"], ["meal-prep"])
        params = [c for c in self.fake.calls if c[1] == "/recipe/"]
        self.assertEqual(len(params), 1)

    def test_add_items_reuses_asks_and_creates(self):
        items = [
            self.s.ShoppingItem(food="Zwiebeln", amount=3),
            self.s.ShoppingItem(food="Ingwer, frisch"),
            self.s.ShoppingItem(food="Paprika", amount=2),
        ]
        out = self.run_(self.s.add_shopping_items(items=items))
        self.assertTrue(out[0]["added"])
        self.assertEqual(out[0]["used_existing_food"], "Zwiebel")
        self.assertFalse(out[1]["added"])
        self.assertEqual(out[1]["similar_foods"], [{"id": 2, "name": "Ingwer"}])
        self.assertTrue(out[2]["added"])
        self.assertEqual(sorted(f["name"] for f in self.fake.foods.values()), ["Ingwer", "Paprika", "Salz", "Zwiebel"])

    def test_new_food_overrides_the_question(self):
        out = self.run_(self.s.add_shopping_items(items=[self.s.ShoppingItem(food="Ingwer, frisch", new_food=True)]))
        self.assertTrue(out[0]["added"])

    def test_remove_reports_each_id_and_repeats_are_harmless(self):
        out = self.run_(self.s.remove_shopping_items(entry_ids=[10, 999]))
        self.assertEqual(out, [{"id": 10, "status": "removed"}, {"id": 999, "status": "already_removed"}])
        out = self.run_(self.s.remove_shopping_items(entry_ids=[10]))
        self.assertEqual(out, [{"id": 10, "status": "already_removed"}])

    def test_check_reports_missing_ids(self):
        out = self.run_(self.s.check_shopping_items(entry_ids=[10, 999], checked=True))
        self.assertEqual(out, [{"id": 10, "status": "checked"}, {"id": 999, "status": "not_found"}])
        self.assertTrue(self.fake.entries[10]["checked"])
        bulk = [c for c in self.fake.calls if c[1] == "/shopping-list-entry/bulk/"]
        self.assertEqual(bulk[0][2], {"ids": [10], "checked": True})

    def test_add_meal_plans_keeps_going_after_a_failure(self):
        entries = [
            self.s.PlanEntry(date="2026-10-19", meal_type="Dinner", title="Reste"),
            self.s.PlanEntry(date="2026-10-20", meal_type="Brunch", title="x"),
            self.s.PlanEntry(date="2026-10-21", meal_type="dinner", title="Pizza"),
        ]
        out = self.run_(self.s.add_meal_plans(entries=entries))
        self.assertEqual([o["added"] for o in out], [True, False, True])
        self.assertIn("Brunch", out[1]["error"])

    def test_search_food_counts_recipes(self):
        out = self.run_(self.s.search_food(query="Zwiebel", limit=10))
        self.assertEqual(out[0]["used_in_recipes"], 4)

    def test_delete_recipe_and_keyword_are_repeatable(self):
        self.assertEqual(self.run_(self.s.delete_recipe(recipe_id=5)), {"id": 5, "status": "removed", "name": "Chili"})
        self.assertEqual(self.run_(self.s.delete_recipe(recipe_id=5)), {"id": 5, "status": "already_removed"})
        self.assertEqual(self.run_(self.s.delete_keyword(keyword_id=7)), {"id": 7, "status": "removed", "name": "test"})
        self.assertEqual(self.run_(self.s.delete_keyword(keyword_id=7)), {"id": 7, "status": "already_removed"})
        self.assertNotIn(5, self.fake.recipes)

    def test_set_food_nutrients_keeps_other_properties(self):
        self.fake.foods[3]["properties"] = [{"id": 70, "property_amount": 2.5, "property_type": {"id": 32, "name": "Salz"}}]
        out = self.run_(self.s.set_food_nutrients(food_id=3, kcal=7, protein_g=0.3, fat_g=None, carbs_g=None, fibre_g=None, per="100ml", g_per_ml=1.0))
        self.assertEqual(out["values"], {"kcal": 7, "protein_g": 0.3})
        (patch,) = [c for c in self.fake.calls if c[0] == "PATCH"]
        body = patch[2]
        self.assertEqual(body["properties_food_amount"], 100)
        self.assertEqual(body["properties_food_unit"]["name"], "ml")
        kept = [p for p in body["properties"] if p.get("id") == 70]
        self.assertEqual(kept[0]["property_amount"], 2.5)
        created = [c for c in self.fake.calls if c[:2] == ("POST", "/property-type/")]
        self.assertEqual([c[2]["name"] for c in created], ["Eiweiß"])
        with self.assertRaises(Exception):
            self.run_(self.s.set_food_nutrients(food_id=3, kcal=None, protein_g=None, fat_g=None, carbs_g=None, fibre_g=None, per="100g", g_per_ml=1.0))

    def test_volume_values_on_a_food_kept_per_100g_are_converted(self):
        # Stock whose label values were first stored per 100 g, then given per 100 ml.
        self.fake.foods[3].update({
            "properties_food_amount": 100,
            "properties_food_unit": {"id": 1, "name": "g"},
            "properties": [{"id": 70, "property_amount": 5, "property_type": {"id": 31, "name": "Kalorien"}}],
        })
        out = self.run_(self.s.set_food_nutrients(food_id=3, kcal=6, protein_g=None, fat_g=None, carbs_g=None, fibre_g=None, per="100ml", g_per_ml=1.2))
        self.assertEqual(out["per"], "100g")
        self.assertEqual(out["values"], {"kcal": 5})
        (patch,) = [c for c in self.fake.calls if c[0] == "PATCH" and c[1] == "/food/3/"]
        self.assertEqual(patch[2]["properties_food_unit"]["name"], "g")
        self.assertEqual(out["conversions"], ["1 l = 1200 g", "100 ml = 120 g"])
        units = sorted((c["base_unit"]["name"], c["converted_amount"]) for c in self.fake.conversions.values())
        self.assertEqual(units, [("l", 1200.0), ("ml", 120.0)])
        # Again with another density: the two conversions are replaced, not added.
        self.run_(self.s.set_food_nutrients(food_id=3, kcal=6, protein_g=None, fat_g=None, carbs_g=None, fibre_g=None, per="100ml", g_per_ml=1.0))
        self.assertEqual(len(self.fake.conversions), 2)
        self.assertEqual(sorted(c["converted_amount"] for c in self.fake.conversions.values()), [100.0, 1000.0])

    def test_other_unit_mismatch_still_refused(self):
        self.fake.foods[3].update({
            "properties_food_amount": 1,
            "properties_food_unit": {"id": 9, "name": "stück"},
            "properties": [{"id": 70, "property_amount": 5, "property_type": {"id": 31, "name": "Kalorien"}}],
        })
        with self.assertRaises(Exception):
            self.run_(self.s.set_food_nutrients(food_id=3, kcal=6, protein_g=None, fat_g=None, carbs_g=None, fibre_g=None, per="100g", g_per_ml=1.0))
        self.assertEqual([c for c in self.fake.calls if c[0] == "PATCH"], [])

    def test_set_unit_conversion(self):
        out = self.run_(self.s.set_unit_conversion(food_id=1, amount=1, unit="Stück", equals=150, equals_unit="g"))
        self.assertEqual(out, {"id": 1, "name": "Zwiebel", "conversion": "1 Stück = 150 g"})
        self.run_(self.s.set_unit_conversion(food_id=1, amount=1, unit="Stück", equals=120, equals_unit="g"))
        (conv,) = self.fake.conversions.values()
        self.assertEqual((conv["base_unit"]["name"], conv["converted_amount"], conv["food"]["id"]), ("Stück", 120, 1))
        with self.assertRaises(Exception):
            self.run_(self.s.set_unit_conversion(food_id=1, amount=1, unit="g", equals=1, equals_unit="G"))

    def test_recipe_image(self):
        self.assertEqual(self.run_(self.s.set_recipe_image(recipe_id=5, image_url="https://example.org/chili.jpg")), {"id": 5, "image": True})
        with self.assertRaises(Exception):
            self.run_(self.s.set_recipe_image(recipe_id=5, image_url="https://example.org/page.html"))
        for bad in ("file:///etc/passwd", "http://127.0.0.1/a.jpg", "http://10.0.0.5/a.jpg", "http://[::1]/a.jpg",
                    "http://tandoor.tandoor.svc.cluster.local/a.jpg", "http://localhost/a.jpg", "http://169.254.169.254/a.jpg"):
            with self.subTest(url=bad), self.assertRaises(Exception):
                self.run_(self.s.set_recipe_image(recipe_id=5, image_url=bad))
        puts = [c for c in self.fake.calls if c[1].endswith("/image/")]
        self.assertEqual(len(puts), 2)


if __name__ == "__main__":
    unittest.main()
