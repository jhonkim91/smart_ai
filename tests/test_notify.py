import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from channel import notify


class NotifyFallbackTest(unittest.TestCase):
    def test_missing_webhook_writes_local_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_url = notify.DISCORD_WEBHOOK_URL
            old_data_dir = notify.DATA_DIR
            notify.DISCORD_WEBHOOK_URL = ""
            notify.DATA_DIR = Path(tmp)
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    delivered = notify.send("메시지", title="테스트", level="warn")
            finally:
                notify.DISCORD_WEBHOOK_URL = old_url
                notify.DATA_DIR = old_data_dir

            self.assertFalse(delivered)
            log_path = Path(tmp) / "logs" / "notifications.log"
            record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(record["delivery"], "local_log")
            self.assertEqual(record["title"], "테스트")
            self.assertEqual(record["message"], "메시지")
            self.assertEqual(record["level"], "warn")


if __name__ == "__main__":
    unittest.main()
