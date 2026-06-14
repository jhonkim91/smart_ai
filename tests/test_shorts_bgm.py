import json
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hermes import bus
from pipelines.shorts import bgm
from pipelines.shorts import produce as produce_mod
from pipelines.shorts import upload as upload_mod


class ShortsBgmTest(unittest.TestCase):
    def test_has_required_ffmpeg_filters(self):
        self.assertTrue(bgm.has_filter("amix"))
        self.assertTrue(bgm.has_filter("afade"))
        self.assertTrue(bgm.has_filter("volume"))

    def test_no_bgm_produce_path_keeps_result_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            short_dir = Path(tmp) / "shorts"
            short_dir.mkdir()

            def fake_synthesize(_sentences, ep_dir):
                (ep_dir / "voice.m4a").write_bytes(b"fake")
                return {"duration": 3.0, "cues": []}

            def fake_render(ep_dir):
                out = ep_dir / "final.mp4"
                out.write_bytes(b"fake")
                return out

            with patch.object(produce_mod, "SHORTS_DIR", short_dir), \
                 patch.object(produce_mod.script_gen, "generate",
                              return_value={
                                  "title": "No BGM",
                                  "hook": "hook",
                                  "lines": ["hello"],
                                  "outro": "outro",
                              }), \
                 patch.object(produce_mod.tts, "synthesize", side_effect=fake_synthesize), \
                 patch.object(produce_mod.render_mod, "render", side_effect=fake_render), \
                 patch.object(produce_mod.bgm_mod, "mix") as mix:
                with redirect_stdout(io.StringIO()):
                    result = produce_mod.produce("topic", bgm=None)

            self.assertNotIn("bgm", result)
            self.assertEqual(Path(result["video"]).name, "final.mp4")
            mix.assert_not_called()

    def test_upload_description_uses_bgm_credits_from_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_db_path = bus.DB_PATH
            bus.DB_PATH = root / "hermes.db"
            self.addCleanup(setattr, bus, "DB_PATH", old_db_path)
            bus.init_db()

            ep_dir = root / "episode"
            ep_dir.mkdir()
            (ep_dir / "final.mp4").write_bytes(b"fake")
            (ep_dir / "script.json").write_text(
                json.dumps({"title": "With Credits", "lines": ["hello"]}),
                encoding="utf-8",
            )
            (ep_dir / "result.json").write_text(
                json.dumps({
                    "title": "With Credits",
                    "video": "final.mp4",
                    "bgm": {"file": "track.mp3", "credits": "Music: Track by Artist"},
                }),
                encoding="utf-8",
            )

            body, _video, _title, _ep = upload_mod.build_video_resource(ep_dir)

            self.assertIn("BGM 출처: Music: Track by Artist",
                          body["snippet"]["description"])


if __name__ == "__main__":
    unittest.main()
