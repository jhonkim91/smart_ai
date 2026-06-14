import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from hermes import bus
from pipelines.shorts import upload as upload_mod


class ShortsUploadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_db_path = bus.DB_PATH
        bus.DB_PATH = self.root / "hermes.db"
        bus.init_db()
        self.episode_dir = self.root / "episode"
        self.episode_dir.mkdir()
        (self.episode_dir / "final.mp4").write_bytes(b"not a real mp4")
        (self.episode_dir / "script.json").write_text(
            json.dumps(
                {
                    "title": "Probe Short",
                    "hook": "첫 문장",
                    "lines": ["둘째 문장", "셋째 문장"],
                    "outro": "마무리",
                    "bgm_attribution": "Test Track by Example Artist",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.episode_dir / "result.json").write_text(
            json.dumps(
                {
                    "title": "Probe Short",
                    "video": "final.mp4",
                    "duration": 12.3,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        bus.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def _approved_task(self, privacy="unlisted"):
        task_id = upload_mod.request_upload_approval(self.episode_dir, privacy)
        bus.set_status(task_id, "approved")
        return task_id

    def test_public_privacy_is_blocked_before_approval(self):
        with self.assertRaises(ValueError):
            upload_mod.upload(self.episode_dir, privacy="public", wait_timeout=0)

        self.assertEqual(bus.list_tasks(limit=10), [])

    def test_duplicate_episode_upload_is_blocked(self):
        task_id = self._approved_task()
        with patch.object(upload_mod, "_execute_insert", return_value={"id": "video-1"}) as insert:
            first = upload_mod.execute_approved_upload(
                self.episode_dir,
                approval_task_id=task_id,
                youtube_service=object(),
            )
        self.assertEqual(first["video_id"], "video-1")
        insert.assert_called_once()

        second_task_id = self._approved_task()
        with patch.object(upload_mod, "_execute_insert", return_value={"id": "video-2"}) as insert:
            with self.assertRaises(upload_mod.DuplicateUploadError):
                upload_mod.execute_approved_upload(
                    self.episode_dir,
                    approval_task_id=second_task_id,
                    youtube_service=object(),
                )
        insert.assert_not_called()

        history = bus.get_publish_history(str(self.episode_dir.resolve()))
        self.assertEqual(history["video_id"], "video-1")

    def test_unapproved_cli_path_does_not_execute_upload(self):
        with patch.object(upload_mod, "execute_approved_upload") as execute:
            with self.assertRaises(upload_mod.UploadApprovalError):
                upload_mod.upload(self.episode_dir, dry_run=True, wait_timeout=0)

        execute.assert_not_called()
        tasks = bus.list_tasks(limit=10)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "pending")

    def test_bus_cli_cannot_approve_hitl_task(self):
        task_id = upload_mod.request_upload_approval(self.episode_dir, "unlisted")

        with redirect_stderr(io.StringIO()):
            exit_code = bus.main(["set-status", str(task_id), "approved"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(bus.get_task(task_id)["status"], "pending")

    def test_dry_run_uses_safe_metadata_and_bgm_attribution(self):
        task_id = self._approved_task("private")
        result = upload_mod.execute_approved_upload(
            self.episode_dir,
            privacy="private",
            approval_task_id=task_id,
            dry_run=True,
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["privacy_status"], "private")
        self.assertFalse(result["request_body"]["status"]["selfDeclaredMadeForKids"])
        self.assertIn("BGM 출처: Test Track", result["request_body"]["snippet"]["description"])
        self.assertIsNone(bus.get_publish_history(str(self.episode_dir.resolve())))


if __name__ == "__main__":
    unittest.main()
