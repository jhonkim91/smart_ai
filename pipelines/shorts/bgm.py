"""쇼츠 BGM 합성 유틸리티.

영상의 내레이션 오디오 위에 BGM을 낮은 볼륨으로 반복 합성한다. 로컬 ffmpeg가
sidechaincompress를 지원하면 내레이션 기준 덕킹을 적용하고, 없으면 고정 볼륨으로
폴백한다.
"""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from hermes.config import ROOT

BGM_DIR = ROOT / "assets" / "bgm"
CREDITS_PATH = BGM_DIR / "credits.json"
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=True)


def duration(path: Path) -> float:
    result = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(result.stdout.strip())


def has_filter(name: str) -> bool:
    try:
        result = _run(["ffmpeg", "-hide_banner", "-filters"])
        return any(line.split()[1] == name for line in result.stdout.splitlines()
                   if len(line.split()) >= 2)
    except Exception:
        return False


def load_credits() -> dict[str, str]:
    if not CREDITS_PATH.exists():
        return {}
    return json.loads(CREDITS_PATH.read_text(encoding="utf-8"))


def list_tracks() -> list[Path]:
    if not BGM_DIR.exists():
        return []
    return sorted(
        p for p in BGM_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def resolve_track(name: str) -> tuple[Path, str]:
    tracks = list_tracks()
    if not tracks:
        raise FileNotFoundError(
            f"{BGM_DIR}에 BGM 파일이 없습니다. assets/bgm/README.md 절차에 따라 YouTube Audio Library 음원을 추가하세요."
        )
    if name == "random":
        path = random.choice(tracks)
        return path, load_credits().get(path.name, "")

    requested = Path(name)
    if requested.is_absolute():
        path = requested
    else:
        path = BGM_DIR / requested
    if not path.exists():
        choices = ", ".join(p.name for p in tracks)
        raise FileNotFoundError(f"BGM 파일 없음: {path}. 사용 가능: {choices}")
    return path, load_credits().get(path.name, "")


def mix(video_path: Path | str, bgm_path: Path | str, out_path: Path | str) -> Path:
    """video_path의 내레이션 오디오와 bgm_path를 섞어 out_path로 쓴다."""
    video = Path(video_path)
    bgm = Path(bgm_path)
    out = Path(out_path)
    dur = duration(video)
    fade_out_start = max(dur - 1.0, 0.0)

    if has_filter("sidechaincompress"):
        filter_complex = (
            "[0:a]asplit=2[narr][side];"
            f"[1:a]volume=0.15,afade=t=in:st=0:d=1,"
            f"afade=t=out:st={fade_out_start:.3f}:d=1[bgm];"
            "[bgm][side]sidechaincompress=threshold=0.03:ratio=8:"
            "attack=50:release=500[ducked];"
            "[narr][ducked]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
    else:
        filter_complex = (
            f"[1:a]volume=0.15,afade=t=in:st=0:d=1,"
            f"afade=t=out:st={fade_out_start:.3f}:d=1[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            str(out),
        ],
        check=True,
    )
    return out
