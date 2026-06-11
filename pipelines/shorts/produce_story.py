"""썰 스토리 쇼츠 생산 오케스트레이션: 주제 → 스토리 → TTS → 만화 프레임 → 슬라이드쇼 조립.

댕소리 스타일(흰 배경 + 장면 카드 + 젤리 캐릭터 + 자막 박스) 썰 쇼츠를 만든다.
이 환경의 ffmpeg는 슬림 빌드라 drawtext/subtitles 필터가 없으므로 텍스트는 전부
cartoon 모듈이 Pillow로 PNG 프레임에 그려 넣고, 여기서는 concat demuxer로
프레임 슬라이드쇼와 TTS 오디오를 합치기만 한다. 업로드는 이 모듈에 없다 —
외부 게시는 반드시 HITL 승인(bus add --approve) 후 별도 단계로 실행한다.

사용:
    python -m pipelines.shorts.produce_story "낙하산 2개가 모두 안 펴질 확률"
    python -m pipelines.shorts.produce_story "주제" --story story.json   # 수정본으로 재생산
    python -m pipelines.shorts.produce_story "주제" --notify             # 완료 시 Discord 보고
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from hermes.config import SHORTS_DIR
from pipelines.shorts import tts

TAIL_PAD = 0.30  # 마지막 장면을 오디오 끝보다 살짝 길게 잡는 여유(초)


def _slug(topic: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", topic).strip("-")
    return s[:40] or "story"


def _load_story(topic: str, story_file: str | None) -> dict:
    """수정본 JSON이 있으면 그것을, 없으면 story_gen으로 초안 생성(Ollama)."""
    if story_file:
        print(f"▸ 스토리: 수정본 사용 ({story_file})")
        return json.loads(Path(story_file).read_text(encoding="utf-8"))
    print("▸ 스토리 초안 생성 (Ollama)…")
    from pipelines.shorts.story_gen import generate_story  # 지연 import (동시 작성 중인 모듈)

    return generate_story(topic)


def _render_frames(story: dict, ep_dir: Path) -> list[Path]:
    """장면별 만화 프레임 PNG 생성. 텍스트(제목/브랜딩/자막)까지 프레임에 포함된다."""
    from pipelines.shorts import cartoon  # 지연 import (동시 작성 중인 모듈)

    frames_dir = ep_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    paths: list[Path] = []
    for i, scene in enumerate(story["scenes"]):
        p = frames_dir / f"scene_{i:03d}.png"
        cartoon.draw_frame(
            out_path=p,
            title=story["title"],
            brand=story.get("brand", "Dang_sound"),
            brand_sub=story.get("brand_sub", ""),
            scene=scene.get("scene") or {},
            subtitle=scene.get("subtitle") or scene["text"],
            highlights=scene.get("highlights") or {},
        )
        paths.append(p)
    return paths


def _scene_durations(cues: list[dict], total: float) -> list[float]:
    """cue 타임라인으로 장면별 표시 시간 계산.

    i번째 = 다음 cue 시작까지(문장 간 무음 GAP 포함),
    마지막 = 오디오 끝까지 + TAIL_PAD.
    """
    durs: list[float] = []
    for i, cue in enumerate(cues):
        if i + 1 < len(cues):
            d = cues[i + 1]["start"] - cue["start"]
        else:
            d = total - cue["start"] + TAIL_PAD
        durs.append(max(d, 0.1))
    return durs


def _assemble(ep_dir: Path, frames: list[Path], durations: list[float],
              audio: Path) -> Path:
    """ffmpeg concat demuxer 슬라이드쇼 + 오디오 합성 → final.mp4."""
    lines: list[str] = []
    for p, d in zip(frames, durations):
        lines.append(f"file '{p.relative_to(ep_dir)}'")
        lines.append(f"duration {d:.3f}")
    # concat demuxer 관례: 마지막 duration이 적용되려면 같은 file을 한 줄 더 쓴다
    lines.append(f"file '{frames[-1].relative_to(ep_dir)}'")
    (ep_dir / "frames.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = ep_dir / "final.mp4"
    # drawtext/subtitles 필터 금지(슬림 빌드) — 텍스트는 이미 PNG에 박혀 있다
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", "frames.txt",
         "-i", audio.name,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", "30",
         "-c:a", "aac", "-b:a", "192k", "-shortest", out.name],
        cwd=ep_dir, check=True,
    )
    return out


def produce_story(topic: str, story_file: str | None = None,
                  notify: bool = False) -> dict:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ep_dir = SHORTS_DIR / f"{stamp}-story-{_slug(topic)}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    # 1) 스토리 (초안=Ollama, 수정본이 있으면 그것을 사용)
    story = _load_story(topic, story_file)
    (ep_dir / "story.json").write_text(
        json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes = story["scenes"]
    print(f"  제목: {story['title']} / 장면 {len(scenes)}개")

    # 2) TTS + 자막 타이밍
    print("▸ TTS 합성 (edge-tts)…")
    manifest = tts.synthesize([s["text"] for s in scenes], ep_dir)
    print(f"  오디오 {manifest['duration']:.1f}초")
    if len(manifest["cues"]) != len(scenes):
        raise RuntimeError(
            f"cue {len(manifest['cues'])}개 ≠ 장면 {len(scenes)}개 — 스토리/TTS 불일치")

    # 3) 만화 프레임 (Pillow — 텍스트 포함 풀프레임 1080x1920)
    print("▸ 프레임 렌더링 (Pillow)…")
    frames = _render_frames(story, ep_dir)

    # 4) 영상 조립 (concat demuxer 슬라이드쇼)
    print("▸ 영상 조립 (FFmpeg)…")
    durations = _scene_durations(manifest["cues"], manifest["duration"])
    out = _assemble(ep_dir, frames, durations, Path(manifest["audio"]))
    size_mb = out.stat().st_size / 1e6
    print(f"  완료: {out} ({size_mb:.1f}MB)")

    result = {"episode_dir": str(ep_dir), "video": str(out),
              "title": story["title"],
              "duration": round(manifest["duration"], 1),
              "scenes": len(scenes)}
    (ep_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) 보고 (단방향 webhook — 승인 아님. 업로드는 별도 HITL)
    if notify:
        from channel.notify import send
        send(f"🎬 썰 쇼츠 렌더링 완료\n제목: {story['title']}\n"
             f"장면: {len(scenes)}개 / 길이: {result['duration']}초\n파일: {out}",
             title="shorts-story", level="ok")
    return result


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.produce_story")
    p.add_argument("topic")
    p.add_argument("--story", default=None, help="다듬은 스토리 JSON 경로")
    p.add_argument("--notify", action="store_true", help="완료 시 Discord 알림")
    args = p.parse_args()
    try:
        result = produce_story(args.topic, args.story, args.notify)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[produce_story] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
