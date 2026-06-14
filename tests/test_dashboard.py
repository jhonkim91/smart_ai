"""대시보드 테스트 — 읽기 전용 보장 + 데이터 모델 스키마.

실행: python -m unittest tests.test_dashboard
"""
import unittest

from dashboard import queries
from dashboard.tui import _plain_frame


class TestQueries(unittest.TestCase):
    def test_board_schema(self):
        b = queries.board()
        self.assertEqual(b["columns"], queries.BOARD_COLUMNS)
        self.assertIn("cards", b)
        self.assertIn("counts", b)
        for col in queries.BOARD_COLUMNS:
            self.assertIn(col, b["cards"])
            self.assertIsInstance(b["cards"][col], list)

    def test_agents_schema(self):
        a = queries.agents()
        self.assertEqual(a["order"], queries.AGENT_LANES)
        self.assertIn("ollama", a["lanes"])
        for name in queries.AGENT_LANES:
            lane = a["lanes"][name]
            self.assertIn("running", lane)
            self.assertIn("queued", lane)
            self.assertIsInstance(lane["active"], bool)
        self.assertGreaterEqual(a["parallel"], 0)
        self.assertLessEqual(a["parallel"], len(queries.AGENT_LANES))

    def test_pipeline_schema(self):
        p = queries.pipeline()
        keys = [n["key"] for n in p["nodes"]]
        self.assertEqual(keys, [s["key"] for s in queries.PIPELINE_STAGES])
        for n in p["nodes"]:
            self.assertIn(n["state"], ("done", "active", "idle"))
        self.assertIn("episodes", p["metrics"])

    def test_snapshot_and_fingerprint(self):
        s = queries.snapshot()
        for key in ("ts", "board", "agents", "pipeline", "events"):
            self.assertIn(key, s)
        self.assertIsInstance(queries.fingerprint(), str)

    def test_readonly_connection_blocks_writes(self):
        """mode=ro 연결은 쓰기를 거부해야 한다(읽기 전용 불변식)."""
        import sqlite3
        with queries._ro_conn() as c:
            if c is None:
                self.skipTest("DB 없음")
            with self.assertRaises(sqlite3.OperationalError):
                c.execute("CREATE TABLE __x(a)")

    def test_plain_frame_renders(self):
        txt = _plain_frame(queries.snapshot())
        self.assertIn("에이전트", txt)
        for name in queries.AGENT_LANES:
            self.assertIn(name, txt)


class TestRouteMapping(unittest.TestCase):
    def test_lane_assignment(self):
        self.assertEqual(queries._lane_for({"kind": "draft", "title": ""}), "ollama")
        self.assertEqual(queries._lane_for({"kind": "code", "title": ""}), "forge")
        self.assertEqual(queries._lane_for({"kind": "review", "title": ""}), "warden")


class TestInstrumentationLightsLanes(unittest.TestCase):
    """Phase 4: activity 계측이 대시보드 레인을 실제로 점등시키는지 임시 DB로 e2e 검증."""

    def setUp(self):
        import tempfile
        from unittest import mock
        from pathlib import Path
        from hermes import bus, config
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "hermes.db"
        self._p1 = mock.patch.object(bus, "DB_PATH", db)
        self._p2 = mock.patch.object(config, "DB_PATH", db)
        self._p1.start(); self._p2.start()
        bus.init_db()

    def tearDown(self):
        self._p1.stop(); self._p2.stop(); self._tmp.cleanup()

    def test_claim_lights_active_then_recent(self):
        from hermes import activity, bus
        tid = bus.add_task("투표용지 부족 사태", kind="draft")

        # claim 이벤트 → ollama 레인 active 점등
        activity.start(tid, "ollama", kind="draft")
        ag = queries.agents()
        self.assertEqual(ag["lanes"]["ollama"]["state"], "active")
        self.assertGreaterEqual(ag["parallel"], 1)

        # done 이벤트 → 최근 가동(recent)으로 전환
        bus.set_result(tid, "ok", status="done")
        activity.done(tid, "ollama", kind="draft")
        ag2 = queries.agents()
        self.assertEqual(ag2["lanes"]["ollama"]["state"], "recent")
        self.assertEqual(ag2["lanes"]["ollama"]["last"]["stage"], "done")

    def test_subagent_lane_lights(self):
        from hermes import activity, bus
        tid = bus.add_task("SSIM 개선", kind="code")
        activity.start(tid, "forge", kind="code")
        ag = queries.agents()
        self.assertEqual(ag["lanes"]["forge"]["state"], "active")

    def test_events_parse_agent_stage(self):
        from hermes import activity, bus
        tid = bus.add_task("요약", kind="summary")
        activity.start(tid, "ollama", kind="summary")
        evs = queries.events(10)
        self.assertTrue(evs)
        self.assertEqual(evs[0]["agent"], "ollama")
        self.assertEqual(evs[0]["stage"], "claimed")


if __name__ == "__main__":
    unittest.main()
