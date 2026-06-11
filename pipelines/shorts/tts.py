"""TTS 단계: edge-tts(무료)로 문장별 음성 생성 + SRT 자막 타이밍 산출.

문장마다 따로 합성해 실제 오디오 길이로 자막 타이밍을 잡는다
(단어 단위 SubMaker보다 단순하고 문장 자막에 정확).

사용:
    python -m pipelines.shorts.tts script.json out_dir/
"""
import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from hermes.config import EDGE_TTS_VOICE

GAP = 0.20  # 문장 사이 무음(초)


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


async def _synth_one(text: str, path: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, EDGE_TTS_VOICE).save(str(path))


def _ts(sec: float) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    ms = round((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def synthesize(sentences: list[str], out_dir: Path) -> dict:
    """문장별 mp3 + 전체 연결 오디오 + SRT 생성. 매니페스트 반환."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(exist_ok=True)

    paths: list[Path] = []
    for i, sent in enumerate(sentences):
        p = seg_dir / f"{i:03d}.mp3"
        asyncio.run(_synth_one(sent, p))
        paths.append(p)

    # 타임라인 계산 + SRT
    cursor = 0.0
    cues = []
    for sent, p in zip(sentences, paths):
        d = _duration(p)
        cues.append({"start": cursor, "end": cursor + d, "text": sent, "dur": d})
        cursor += d + GAP

    srt_path = out_dir / "subtitles.srt"
    with srt_path.open("w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['text']}\n\n")

    # 무음 패딩을 넣어 하나의 오디오로 연결
    audio_path = out_dir / "voice.m4a"
    inputs = []
    for p in paths:
        inputs += ["-i", str(p)]
    pad = f"apad=pad_dur={GAP}"
    filtergraph = (
        "".join(f"[{i}:a]{pad}[a{i}];" for i in range(len(paths) - 1))
        + "".join(f"[a{i}]" for i in range(len(paths) - 1))
        + f"[{len(paths) - 1}:a]concat=n={len(paths)}:v=0:a=1[out]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", filtergraph, "-map", "[out]",
         "-c:a", "aac", "-b:a", "192k", str(audio_path)],
        check=True,
    )
    total = _duration(audio_path)
    manifest = {"audio": str(audio_path), "srt": str(srt_path),
                "duration": total, "cues": cues, "voice": EDGE_TTS_VOICE}
    (out_dir / "tts_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.tts")
    p.add_argument("script_json", help="script_gen 출력 JSON 파일")
    p.add_argument("out_dir")
    args = p.parse_args()
    from pipelines.shorts.script_gen import sentences as to_sentences

    script = json.loads(Path(args.script_json).read_text(encoding="utf-8"))
    try:
        m = synthesize(to_sentences(script), Path(args.out_dir))
        print(json.dumps({"audio": m["audio"], "duration": m["duration"]},
                         ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[tts] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
