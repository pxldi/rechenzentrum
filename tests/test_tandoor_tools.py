"""The recipe server's tools against a fake Tandoor API.

Needs the MCP SDK, so it runs inside the homelab-mcp image (see the image
workflow) and is skipped where the SDK is not installed. The fake answers the
way Tandoor 2.6 does for the endpoints these tools use.
"""

import asyncio
import importlib.util
import json
import os
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
        self.next_id = 100
        self.calls = []

    def handle(self, request):
        import httpx

        path = request.url.path.removeprefix("/api")
        method = request.method
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
            return httpx.Response(200, json={"results": hits})
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
            ok = body["image_url"].endswith(".jpg")
            return httpx.Response(200, json={"image": "/media/x.jpg" if ok else None, "image_url": body["image_url"]})
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
