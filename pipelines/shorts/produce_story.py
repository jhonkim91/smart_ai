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
    python -m pipelines.shorts.produce_story "주제" --motion             # Ken Burns 줌 모션
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from hermes.config import SHORTS_DIR
from pipelines.shorts import bgm as bgm_mod
from pipelines.shorts import tts

TAIL_PAD = 0.30  # 마지막 장면을 오디오 끝보다 살짝 길게 잡는 여유(초)
FPS = 30  # 출력 프레임레이트 — zoompan fps와 인코딩 -r에 공통 적용
ZOOM_MAX = 1.025  # 풀프레임 zoompan은 상단 브랜딩/제목까지 같이 잘리므로 아주 약하게만 적용
ZOOM_STEP = 0.00025
ZOOM_IN = f"min(zoom+{ZOOM_STEP}, {ZOOM_MAX})"   # 짝수 장면: 상태변수 zoom 기반 미세 줌인
ZOOM_OUT = f"max({ZOOM_MAX}-{ZOOM_STEP}*on,1.0)"  # 홀수 장면: on 기반 미세 줌아웃


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


def _renderer(style: str):
    """프레임 렌더러 모듈 선택."""
    if style == "dang_reference":
        from pipelines.shorts import dang_reference

        return dang_reference
    if style == "reference":
        from pipelines.shorts import reference_style

        return reference_style
    if style == "cartoon":
        from pipelines.shorts import cartoon

        return cartoon
    raise ValueError(f"지원하지 않는 style: {style}")


def _brand_defaults(story: dict, style: str) -> tuple[str, str]:
    """렌더 스타일별 기본 브랜딩.

    기존 cartoon 스타일은 과거 호환을 위해 Dang_sound 기본값을 유지하고,
    reference 스타일은 원본 레퍼런스와 맞는 한국어 브랜딩을 기본값으로 쓴다.
    """
    if style == "reference":
        return (story.get("brand") or "댕소리",
                story.get("brand_sub") or "오늘의 실화 썰")
    if style == "dang_reference":
        return (story.get("brand") or "Dang_sound",
                story.get("brand_sub") or "댕소리")
    return story.get("brand") or "Dang_sound", story.get("brand_sub") or ""


def _render_frames(story: dict, ep_dir: Path, style: str = "cartoon") -> list[Path]:
    """장면별 만화 프레임 PNG 생성. 텍스트(제목/브랜딩/자막)까지 프레임에 포함된다."""
    renderer = _renderer(style)
    brand, brand_sub = _brand_defaults(story, style)

    frames_dir = ep_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    paths: list[Path] = []
    for i, scene in enumerate(story["scenes"]):
        p = frames_dir / f"scene_{i:03d}.png"
        renderer.draw_frame(
            out_path=p,
            title=story["title"],
            brand=brand,
            brand_sub=brand_sub,
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


def _frame_counts(durations: list[float]) -> list[int]:
    """누적 경계 반올림으로 장면별 프레임 수 산정.

    장면별 독립 반올림(round(d*FPS))은 누적 드리프트가 생기므로,
    누적 시작시간의 경계를 반올림해 모든 장면 경계와 총 길이를
    진실값 대비 0.5프레임(1/60초) 이내로 묶는다.
    """
    counts: list[int] = []
    cursor = 0.0
    for d in durations:
        n = round((cursor + d) * FPS) - round(cursor * FPS)
        counts.append(max(n, 1))
        cursor += d
    return counts


def _assemble_motion(ep_dir: Path, frames: list[Path], durations: list[float],
                     audio: Path) -> Path:
    """장면별 zoompan(Ken Burns) 클립 생성 → concat copy → 오디오 mux → final.mp4.

    각 프레임을 lanczos 2배 업스케일(2160x3840) 후 zoompan에 넣어 떨림을 막고,
    짝수 장면은 줌인 / 홀수 장면은 줌아웃을 교차한다. 클립은 최종 인코딩
    파라미터로 한 번만 인코딩하고 concat은 -c:v copy라 이중 인코딩이 없다.
    """
    clips_dir = ep_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    counts = _frame_counts(durations)

    clips: list[Path] = []
    for i, (frame, n) in enumerate(zip(frames, counts)):
        zexpr = ZOOM_IN if i % 2 == 0 else ZOOM_OUT
        # 중앙 고정 줌(패닝 없음) — 텍스트가 비대칭으로 잘리는 것을 방지.
        # zoompan fps=30 명시 필수(기본 25라 누락 시 싱크 붕괴).
        vf = (f"scale=2160:3840:flags=lanczos,"
              f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={n}:s=1080x1920:fps={FPS}")
        clip = clips_dir / f"clip_{i:03d}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(frame),
             "-vf", vf, "-frames:v", str(n),
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", "30", str(clip)],
            check=True,
        )
        clips.append(clip)

    # 동일 템플릿으로 인코딩한 클립이라 코덱 파라미터가 같아 copy concat이 안전하다
    clips_txt = ep_dir / "clips.txt"
    clips_txt.write_text(
        "\n".join(f"file 'clips/{c.name}'" for c in clips) + "\n", encoding="utf-8")

    out = ep_dir / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", "clips.txt",
         "-i", audio.name,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", out.name],
        cwd=ep_dir, check=True,
    )
    # 성공 시에만 중간 산출물 정리 — 실패하면 디버깅용으로 남는다
    shutil.rmtree(clips_dir)
    clips_txt.unlink()
    return out


def produce_story(topic: str, story_file: str | None = None,
                  notify: bool = False, bgm: str | None = None,
                  motion: bool = False, style: str = "cartoon") -> dict:
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
    print(f"▸ 프레임 렌더링 (Pillow, style={style})…")
    frames = _render_frames(story, ep_dir, style=style)

    # 4) 영상 조립 (정적 슬라이드쇼 또는 Ken Burns 모션)
    print("▸ 영상 조립 (FFmpeg" + (", Ken Burns 모션)…" if motion else ")…"))
    durations = _scene_durations(manifest["cues"], manifest["duration"])
    out = (_assemble_motion if motion else _assemble)(
        ep_dir, frames, durations, Path(manifest["audio"]))
    size_mb = out.stat().st_size / 1e6
    print(f"  완료: {out} ({size_mb:.1f}MB)")

    result = {"episode_dir": str(ep_dir), "video": str(out),
              "title": story["title"],
              "duration": round(manifest["duration"], 1),
              "scenes": len(scenes),
              "motion": motion,
              "style": style}

    # 5) BGM 합성 (선택)
    if bgm:
        bgm_path, credits = bgm_mod.resolve_track(bgm)
        mixed = ep_dir / "final_bgm.mp4"
        print(f"▸ BGM 합성 ({bgm_path.name})…")
        out = bgm_mod.mix(out, bgm_path, mixed)
        result["video"] = str(out)
        result["bgm"] = {"file": bgm_path.name, "credits": credits}
        print(f"  완료: {out}")

    (ep_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6) 보고 (단방향 webhook — 승인 아님. 업로드는 별도 HITL)
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
    p.add_argument("--bgm", default=None,
                   help="assets/bgm 파일명 또는 random. 생략 시 기존 무BGM 경로")
    p.add_argument("--motion", action="store_true",
                   help="장면별 Ken Burns 줌 모션(zoompan). 생략 시 기존 정적 슬라이드쇼")
    p.add_argument("--style", default="cartoon", choices=("cartoon", "reference", "dang_reference"),
                   help="프레임 렌더 스타일. dang_reference는 제공 레퍼런스의 제작 문법/레이아웃에 맞춘 스타일")
    args = p.parse_args()
    try:
        result = produce_story(args.topic, args.story, args.notify, args.bgm,
                               args.motion, args.style)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[produce_story] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
