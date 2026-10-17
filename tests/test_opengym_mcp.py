"""The openGym MCP server: reading the state document, progression, and
writes that must not lose anything.

The logic tests need only the standard library. The write-path tests talk to
a fake openGym through httpx and need the SDK, so they run inside the
homelab-mcp image (see the image workflow) and are skipped elsewhere.
"""

import asyncio
import copy
import importlib.util
import json
import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

from opengym_mcp import logic as og  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
BENCH, SQUAT, PUSHUP, ASSIST, LATERAL = "0025", "0043", "0662", "0017", "0334"
HAVE_SDK = all(importlib.util.find_spec(m) is not None for m in ("mcp", "httpx", "pydantic"))


def ms(day: str, hm: str = "18:00") -> int:
    y, m, d = (int(x) for x in day.split("-"))
    hh, mm = (int(x) for x in hm.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=TZ).timestamp() * 1000)


def sets(*pairs, warmup=0):
    rows = [{"w": w, "r": r, "done": True, "phase": "warmup"} for w, r in pairs[:warmup]]
    return rows + [{"w": w, "r": r, "done": True} for w, r in pairs[warmup:]]


def workout(wid, day, entries, rid="pushA", name="Push A"):
    return {"id": wid, "d": day, "start": ms(day), "end": ms(day, "19:00"), "routineIds": [rid], "routineId": rid,
            "name": name, "entries": entries, "prs": []}


def plan(cfg):
    return {k: cfg[k] for k in ("sets", "reps", "repsMin", "weight") if k in cfg}


BENCH_CFG = {"id": BENCH, "sets": 3, "reps": 8, "weight": 60}
LATERAL_CFG = {"id": LATERAL, "sets": 3, "reps": 12, "repsMin": 8, "weight": 8, "prog": "double"}
PUSHUP_CFG = {"id": PUSHUP, "sets": 3, "reps": 10}


def base_state():
    return {
        "_rev": 7,
        "_ts": ms("2026-10-15", "20:00"),
        "unit": "kg",
        "routines": [{"id": "pushA", "name": "Push A", "ex": [BENCH_CFG, LATERAL_CFG, PUSHUP_CFG]},
                     {"id": "legsA", "name": "Legs A", "ex": [{"id": SQUAT, "sets": 3, "reps": 5, "weight": 80}]}],
        "week": {"1": ["pushA"], "3": ["legsA"]},
        "exWeights": {BENCH: {"w": 60, "d": "2026-10-12"}},
        "customEx": [{"id": "im1", "n": "Hip thrust machine", "bp": "upper legs", "eq": "leverage machine"}],
        "bodyweight": [{"d": "2026-10-10", "w": 78.4, "t": 1}, {"d": "2026-10-14", "w": 78.0, "t": 2}],
        "workouts": [
            workout("a1", "2026-10-05", [
                {"id": BENCH, "sets": sets((40, 5), (60, 8), (60, 8), (60, 8), warmup=1), "target": {"sets": 3, "reps": 8, "weight": 60}, "planned": plan(BENCH_CFG)},
                {"id": LATERAL, "sets": sets((8, 9), (8, 9), (8, 8)), "target": {"sets": 3, "reps": 12, "repsMin": 8}, "planned": plan(LATERAL_CFG)},
                {"id": PUSHUP, "sets": sets((0, 10), (0, 10), (0, 10)), "target": {"sets": 3, "reps": 10}, "planned": plan(PUSHUP_CFG)},
            ]),
            workout("a2", "2026-10-12", [
                {"id": BENCH, "sets": sets((62.5, 8), (62.5, 7), (62.5, 6)), "target": {"sets": 3, "reps": 8, "weight": 60}, "planned": plan(BENCH_CFG)},
                {"id": LATERAL, "sets": sets((8, 12), (8, 12), (8, 12)), "target": {"sets": 3, "reps": 12, "repsMin": 8}, "planned": plan(LATERAL_CFG)},
            ]),
        ],
    }


class Catalogue(unittest.TestCase):
    def test_names_and_custom_exercises(self):
        cat = og.Catalogue(base_state())
        self.assertEqual(cat.name(BENCH), "barbell bench press")
        self.assertTrue(cat.get("im1").custom)
        self.assertTrue(cat.get(ASSIST).assisted)
        self.assertFalse(cat.get(BENCH).assisted)

    def test_resolve_prefers_exercises_in_use(self):
        state = base_state()
        cat = og.Catalogue(state)
        used = og.used_exercise_ids(state)
        self.assertEqual(cat.resolve("bench press", prefer=used).id, BENCH)
        self.assertEqual(cat.resolve("Barbell Bench Press").id, BENCH)
        self.assertEqual(cat.resolve(BENCH).id, BENCH)

    def test_ambiguous_name_lists_candidates(self):
        cat = og.Catalogue(base_state())
        with self.assertRaises(og.StateError) as ctx:
            cat.resolve("curl")
        self.assertIn("several", str(ctx.exception))
        with self.assertRaises(og.StateError):
            cat.resolve("no such lift xyz")


class Reading(unittest.TestCase):
    def test_history_skips_warmups_for_top_weight_and_1rm(self):
        state = base_state()
        cat = og.Catalogue(state)
        hist = og.exercise_sessions(state, cat.get(BENCH), TZ)
        self.assertEqual([h["date"] for h in hist], ["2026-10-05", "2026-10-12"])
        self.assertEqual(hist[0]["top_weight"], 60)
        self.assertTrue(hist[0]["sets"][0]["warmup"])
        self.assertEqual(hist[1]["est_1rm"], og.epley(62.5, 8))

    def test_workout_detail(self):
        state = base_state()
        d = og.workout_detail(state["workouts"][0], og.Catalogue(state), TZ)
        self.assertEqual(d["date"], "2026-10-05")
        self.assertEqual(d["sets_done"], 9)
        self.assertEqual(d["entries"][0]["exercise"], "barbell bench press")
        self.assertEqual(d["volume"], 60 * 8 * 3 + 8 * 26 + 0)

    def test_week_plan_names_routines(self):
        week = og.week_plan(base_state())
        self.assertEqual(week["monday"], ["Push A"])
        self.assertEqual(week["wednesday"], ["Legs A"])
        self.assertEqual(week["sunday"], [])


class Progression(unittest.TestCase):
    def setUp(self):
        self.state = base_state()
        self.cat = og.Catalogue(self.state)
        self.push = self.state["routines"][0]

    def p(self, cfg, routine=None):
        return og.next_prescription(self.state, cfg, routine or self.push, self.cat)

    def test_linear_holds_after_a_miss(self):
        p = self.p(BENCH_CFG)
        self.assertEqual((p["kind"], p["weight"]), ("hold", 62.5))

    def test_linear_goes_up_after_every_rep(self):
        self.state["workouts"][1]["entries"][0]["sets"] = sets((62.5, 8), (62.5, 8), (62.5, 8))
        p = self.p(BENCH_CFG)
        self.assertEqual((p["kind"], p["weight"]), ("up", 65))

    def test_linear_deloads_after_three_misses_at_one_weight(self):
        for i, day in enumerate(["2026-10-13", "2026-10-14"]):
            self.state["workouts"].append(workout(f"m{i}", day, [
                {"id": BENCH, "sets": sets((62.5, 7), (62.5, 6), (62.5, 6)), "target": {"sets": 3, "reps": 8}, "planned": plan(BENCH_CFG)}]))
        p = self.p(BENCH_CFG)
        self.assertEqual(p["kind"], "deload")
        self.assertEqual(p["weight"], 57.5)  # 62.5 * 0.9 = 56.25, rounded half up onto the 2.5 grid as in JS

    def test_lower_body_steps_by_five(self):
        legs = self.state["routines"][1]
        self.state["workouts"].append(workout("l1", "2026-10-14", [
            {"id": SQUAT, "sets": sets((80, 5), (80, 5), (80, 5)), "target": {"sets": 3, "reps": 5}, "planned": plan(legs["ex"][0])}], rid="legsA", name="Legs A"))
        p = self.p(legs["ex"][0], legs)
        self.assertEqual((p["kind"], p["weight"]), ("up", 85))

    def test_double_progression_raises_at_the_top_of_the_range(self):
        p = self.p(LATERAL_CFG)
        self.assertEqual((p["kind"], p["weight"], p["reps"]), ("up", 10.5, 8))

    def test_double_progression_climbs_reps_below_the_top(self):
        self.state["workouts"].pop()
        p = self.p(LATERAL_CFG)
        self.assertEqual((p["kind"], p["weight"], p["reps"]), ("hold", 8, 9))

    def test_bodyweight_climbs_reps(self):
        p = self.p(PUSHUP_CFG)
        self.assertEqual((p["kind"], p["weight"], p["reps"]), ("up", 0, 11))

    def test_changed_plan_restarts_from_it(self):
        cfg = {**BENCH_CFG, "reps": 5, "weight": 70}
        p = self.p(cfg)
        self.assertEqual((p["kind"], p["weight"]), ("hold", 70))

    def test_nothing_logged(self):
        cfg = {"id": "im1", "sets": 3, "reps": 10, "weight": 40}
        self.assertEqual(self.p(cfg)["kind"], "first")

    def test_suggest_routine_lists_every_exercise(self):
        out = og.suggest_routine(self.state, self.push, self.cat, TZ)
        self.assertEqual([e["exercise_id"] for e in out["exercises"]], [BENCH, LATERAL, PUSHUP])
        self.assertEqual(out["exercises"][0]["next"], {"weight": 62.5, "reps": 8, "sets": 3})
        self.assertEqual(out["exercises"][0]["last"]["date"], "2026-10-12")


class Writing(unittest.TestCase):
    NOW = ms("2026-10-17", "12:00")

    def add(self, state, **kw):
        args = {"day": date(2026, 10, 16), "entries": [og.EntryIn("bench press", [og.SetIn(65, 8), og.SetIn(65, 8)])],
                "tz": TZ, "now_ms": self.NOW, **kw}
        return og.add_workout(state, **args)

    def test_add_keeps_everything_else(self):
        state = base_state()
        before = copy.deepcopy(state)
        new, w = self.add(state, routine_ref="push a")
        self.assertEqual(state, before, "the input document must not be changed")
        og.check_change(state, new, workouts=1)
        self.assertEqual(len(new["workouts"]), 3)
        self.assertEqual(new["workouts"][-1]["id"], w["id"])
        self.assertTrue(w["id"].startswith(og.MCP_ID_PREFIX))
        self.assertEqual(w["d"], "2026-10-16")
        self.assertEqual(w["routineIds"], ["pushA"])
        self.assertEqual(w["name"], "Push A")
        self.assertEqual(w["entries"][0]["rid"], "pushA")
        self.assertEqual(w["entries"][0]["planned"], plan(BENCH_CFG))
        self.assertEqual(w["entries"][0]["sets"][0], {"w": 65, "r": 8, "done": True})
        self.assertEqual(w["prs"], [BENCH])
        self.assertEqual(w["bw"], 78.0)
        self.assertEqual(w["vol"], 65 * 16)
        self.assertEqual(w["_ts"], self.NOW)
        self.assertEqual(new["exWeights"], state["exWeights"])
        self.assertGreater(new["_ts"], state["_ts"])

    def test_logged_workout_drives_the_next_prescription(self):
        state = base_state()
        new, _ = self.add(state, routine_ref="pushA", entries=[og.EntryIn(BENCH, [og.SetIn(62.5, 8)] * 3)])
        p = og.next_prescription(new, BENCH_CFG, new["routines"][0], og.Catalogue(new))
        self.assertEqual((p["kind"], p["weight"]), ("up", 65))

    def test_sorted_in_by_day(self):
        new, w = self.add(base_state(), day=date(2026, 10, 8))
        self.assertEqual([x["id"] for x in new["workouts"]], ["a1", w["id"], "a2"])
        self.assertEqual(w["prs"], [BENCH])  # beats 60 from before it, not 62.5 from after

    def test_refuses_nonsense(self):
        state = base_state()
        for kw in ({"entries": []},
                   {"entries": [og.EntryIn(BENCH, [og.SetIn(60, 0)])]},
                   {"entries": [og.EntryIn(BENCH, [og.SetIn(-5, 8)])]},
                   {"day": date(2026, 10, 17), "start_hm": "18:00"},
                   {"start_hm": "evening"},
                   {"routine_ref": "Pull Z"}):
            with self.subTest(kw=kw), self.assertRaises(og.StateError):
                self.add(state, **kw)

    def test_delete_only_own_workouts(self):
        state = base_state()
        with self.assertRaises(og.StateError):
            og.remove_workout(state, "a1")
        new, w = self.add(state)
        gone, _ = og.remove_workout(new, w["id"])
        og.check_change(new, gone, workouts=-1)
        self.assertEqual([x["id"] for x in gone["workouts"]], ["a1", "a2"])

    def test_bodyweight_one_entry_per_day(self):
        state = base_state()
        new, entry, old = og.set_bodyweight(state, date(2026, 10, 14), 77.6, now_ms=self.NOW)
        self.assertEqual(old["w"], 78.0)
        self.assertEqual([b["w"] for b in new["bodyweight"]], [78.4, 77.6])
        og.check_change(state, new, bodyweight=1)
        new, entry, old = og.set_bodyweight(state, date(2026, 10, 16), 77.9, now_ms=self.NOW)
        self.assertIsNone(old)
        self.assertEqual(len(new["bodyweight"]), 3)
        with self.assertRaises(og.StateError):
            og.set_bodyweight(state, date(2026, 10, 16), 7.79)

    def test_check_change_catches_a_lost_routine(self):
        state = base_state()
        bad = copy.deepcopy(state)
        bad["routines"].pop()
        with self.assertRaises(og.StateError):
            og.check_change(state, bad)

    def test_parse_day(self):
        today = date(2026, 10, 17)
        self.assertEqual(og.parse_day("gestern", TZ, today), date(2026, 10, 16))
        self.assertEqual(og.parse_day("2026-10-01", TZ, today), date(2026, 10, 1))
        with self.assertRaises(og.StateError):
            og.parse_day("2026-10-18", TZ, today)


class FakeOpenGym:
    """openGym's /api/data with its compare-and-swap, and a phone that can
    save between our read and our write."""

    def __init__(self, state, token="tok"):
        self.state = state
        self.token = token
        self.puts = 0
        self.phone_saves_once = None

    def handler(self, request):
        import httpx

        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "not signed in"})
        if request.method == "GET" and request.url.path == "/api/data":
            return httpx.Response(200, json={"state": copy.deepcopy(self.state), "rev": self.state["_rev"]})
        if request.method == "PUT" and request.url.path == "/api/data":
            self.puts += 1
            if self.phone_saves_once:
                self.phone_saves_once(self.state)
                self.state["_rev"] += 1
                self.phone_saves_once = None
            body = json.loads(request.content)
            if body.get("baseRev") != self.state["_rev"]:
                return httpx.Response(409, json={"error": "conflict", "rev": self.state["_rev"], "state": copy.deepcopy(self.state)})
            new = body["state"]
            new["_rev"] = self.state["_rev"] + 1
            self.state = new
            return httpx.Response(200, json={"ok": True, "rev": new["_rev"]})
        return httpx.Response(404)


@unittest.skipUnless(HAVE_SDK, "needs the MCP SDK and httpx (run inside the homelab-mcp image)")
class ServerWrites(unittest.TestCase):
    def setUp(self):
        import httpx

        with mock.patch.dict(os.environ, {"OPENGYM_TOKEN": "tok", "OPENGYM_URL": "http://og.test"}):
            from opengym_mcp import server
        self.server = server
        self.fake = FakeOpenGym(base_state())
        real = httpx.AsyncClient
        transport = httpx.MockTransport(self.fake.handler)
        patcher = mock.patch.object(server, "_client", lambda: real(base_url="http://og.test", headers={"Authorization": "Bearer tok"}, transport=transport))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tool(self, coro):
        return asyncio.run(coro)

    def test_log_workout_survives_a_phone_save_in_between(self):
        phone_workout = workout("phone1", "2026-10-16", [{"id": SQUAT, "sets": sets((80, 5)), "target": None}], rid="legsA", name="Legs A")
        self.fake.phone_saves_once = lambda st: st["workouts"].append(phone_workout)
        ex = [self.server.ExerciseInput(exercise=BENCH, sets=[self.server.SetInput(weight=60, reps=8)])]
        out = self.run_tool(self.server.log_workout(exercises=ex, date="2026-10-15", start_time="", duration_min=45, routine="", name="", note=""))
        self.assertEqual(self.fake.puts, 2)
        ids = [w["id"] for w in self.fake.state["workouts"]]
        self.assertIn("phone1", ids)
        self.assertIn(out["logged"]["id"], ids)
        self.assertEqual(len(ids), 4)
        self.assertEqual(self.fake.state["routines"], base_state()["routines"])
        self.assertNotIn("active", self.fake.state)

    def test_revoked_token_says_pair_again(self):
        from mcp.server.mcpserver.exceptions import ToolError

        self.fake.token = "other"
        with self.assertRaises(ToolError) as ctx:
            self.run_tool(self.server.list_workouts(days=30, limit=5))
        self.assertIn("pair again", str(ctx.exception))

    def test_reads(self):
        out = self.run_tool(self.server.exercise_history(exercise="bench press", sessions=1))
        self.assertEqual(out["sessions_total"], 2)
        self.assertEqual(out["sessions"][0]["date"], "2026-10-12")
        out = self.run_tool(self.server.suggest_progression(routine="Push A"))
        self.assertEqual(out["exercises"][1]["kind"], "up")


if __name__ == "__main__":
    unittest.main()
