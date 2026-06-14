import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes import bus
from hermes import worker


class HermesWorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = bus.DB_PATH
        bus.DB_PATH = Path(self.tmp.name) / "hermes.db"
        bus.init_db()

    def tearDown(self):
        bus.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_claim_next_task_filters_kinds_and_marks_running(self):
        code_id = bus.add_task("코드 작업", kind="code")
        draft_id = bus.add_task("초안 작업", kind="draft")

        task = bus.claim_next_task({"draft"})

        self.assertEqual(task["id"], draft_id)
        self.assertEqual(bus.get_task(draft_id)["status"], "running")
        self.assertEqual(bus.get_task(code_id)["status"], "queued")

    def test_run_once_processes_ollama_task_and_records_events(self):
        task_id = bus.add_task("요약해줘", body="본문", kind="summary")

        with patch.object(worker, "ollama_run", return_value="요약 결과") as run:
            result = worker.run_once(kinds=("summary",))

        self.assertEqual(result["status"], "done")
        run.assert_called_once_with("summary", "요약해줘\n\n본문")
        task = bus.get_task(task_id)
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["result"], "요약 결과")
        events = bus.task_events(task_id)
        self.assertEqual([e["message"] for e in events], [
            "worker claimed task",
            "worker completed task",
        ])

    def test_run_once_does_not_claim_unsupported_default_kind(self):
        task_id = bus.add_task("코드 작업", kind="code")

        result = worker.run_once()

        self.assertEqual(result, {"status": "idle"})
        self.assertEqual(bus.get_task(task_id)["status"], "queued")

    def test_worker_failure_marks_task_failed(self):
        task_id = bus.add_task("요약해줘", kind="summary")

        with patch.object(worker, "ollama_run", side_effect=RuntimeError("boom")):
            result = worker.run_once(kinds=("summary",))

        self.assertEqual(result["status"], "failed")
        task = bus.get_task(task_id)
        self.assertEqual(task["status"], "failed")
        self.assertIn("boom", task["result"])
        self.assertEqual(bus.task_events(task_id)[-1]["level"], "error")


if __name__ == "__main__":
    unittest.main()
