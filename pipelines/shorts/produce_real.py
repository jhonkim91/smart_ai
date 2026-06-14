"""실사 합성 쇼츠: 실사 스톡영상 배경 + 스틱 캐릭터(부유 애니메이션) + UI 레이어.

댕소리 원본 기법 재현: 각 장면마다
  1) Pexels 실사 클립을 카드 영역에 스케일/크롭(없으면 2D 그라디언트 폴백)
  2) 긴 팔다리 스틱 캐릭터(actor)를 투명 PNG로 올려 ffmpeg overlay (sin 부유 모션)
  3) 흰 프레임+제목+브랜딩+자막 박스(UI 레이어, 카드 구멍은 투명)를 맨 위에 합성
장면 클립을 concat 한 뒤 edge-tts 오디오를 mux 한다. 업로드는 이 모듈에 없다 —
외부 게시는 반드시 HITL 승인 후 별도 단계로 실행한다.

사용:
    python -m pipelines.shorts.produce_real "제목" --story story.json --notify
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from hermes.config import SHORTS_DIR
from pipelines.shorts import actor, stock_bg, tts
from pipelines.shorts import reference_style as ref

FPS = 30
TAIL_PAD = 0.30
ANIM_FRAMES = 20  # 캐릭터 애니메이션 루프 길이(프레임). FPS와 함께 ~0.67초 루프
XFADE = 0.40      # 장면 전환 크로스페이드 길이(초). 0이면 하드컷

CARDX, CARDY, CARDX1, CARDY1 = ref.CARD
CARDW, CARDH = CARDX1 - CARDX, CARDY1 - CARDY


def _slug(topic: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", topic).strip("-")
    return s[:40] or "real"


def _scene_durations(cues: list[dict], total: float) -> list[float]:
    durs: list[float] = []
    for i, cue in enumerate(cues):
        d = (cues[i + 1]["start"] - cue["start"]) if i + 1 < len(cues) \
            else (total - cue["start"] + TAIL_PAD)
        durs.append(max(d, 0.4))
    return durs


def _render_ui(story: dict, scene: dict, subtitle: str, highlights: dict, out: Path) -> Path:
    """흰 프레임(카드 구멍 투명) + 헤더/제목/자막 박스 → 투명 PNG."""
    S = ref.S
    canvas = Image.new("RGBA", (ref.W * S, ref.H * S), (255, 255, 255, 255))
    # 카드 영역을 투명 구멍으로 (둥근 모서리)
    hole = Image.new("L", canvas.size, 255)
    ImageDraw.Draw(hole).rounded_rectangle(
        [CARDX * S, CARDY * S, CARDX1 * S, CARDY1 * S],
        radius=ref.CARD_RADIUS * S, fill=0)
    canvas.putalpha(hole)
    # 카드 테두리
    ImageDraw.Draw(canvas).rounded_rectangle(
        [CARDX * S, CARDY * S, CARDX1 * S - 1, CARDY1 * S - 1],
        radius=ref.CARD_RADIUS * S, outline=(204, 204, 204), width=2 * S)
    brand = story.get("brand") or "댕소리"
    brand_sub = story.get("brand_sub") or "오늘의 실화 썰"
    ref._draw_header(canvas, brand, brand_sub)
    ref._draw_title(canvas, story["title"])
    ref._draw_subtitle(canvas, subtitle, highlights or {})
    out_img = canvas.resize((ref.W, ref.H), Image.Resampling.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(out)
    return out


def _fallback_bg(scene: dict, out: Path) -> Path:
    """Pexels 실패 시: 카드 영역 크기의 2D 그라디언트 still PNG."""
    bg = scene.get("bg", "room")
    colors = scene.get("bg_colors") or ref.PALETTES.get(bg, ref.PALETTES["room"])
    img = ref._v_gradient(CARDW, CARDH, colors[0], colors[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def _scene_clip(idx: int, scene: dict, story: dict, dur: float, ep_dir: Path) -> tuple[Path, dict | None]:
    """장면 1개를 합성한 mp4 클립 생성 → (clip_path, credits)."""
    work = ep_dir / "work"
    work.mkdir(exist_ok=True)
    subtitle = scene.get("subtitle") or scene["text"]
    highlights = scene.get("highlights") or {}

    anim_dir = work / f"anim_{idx:03d}"
    n_frames = actor.render_actors_anim(scene, anim_dir, frames=ANIM_FRAMES)
    ui_png = work / f"ui_{idx:03d}.png"
    _render_ui(story, scene, subtitle, highlights, ui_png)

    # 배경: Pexels 실사 우선, 실패 시 2D 폴백
    credits = None
    res = stock_bg.fetch(stock_bg.resolve_query(scene), orientation="portrait")
    if res:
        bg_path, credits = res
        bg_is_video = True
    else:
        bg_path = _fallback_bg(scene, work / f"bgfb_{idx:03d}.png")
        bg_is_video = False

    clip = work / f"clip_{idx:03d}.mp4"
    # 전환(xfade) 겹침을 위해 각 클립을 XFADE만큼 더 길게 렌더(배경/캐릭터/자막이 그대로 유지됨)
    clip_len = dur + XFADE
    # 캐릭터: 애니 시퀀스를 loop 필터로 장면 길이만큼 반복(모션이 계속 움직임)
    fc = (
        f"[0:v]scale={CARDW}:{CARDH}:force_original_aspect_ratio=increase,"
        f"crop={CARDW}:{CARDH},setsar=1,fps={FPS}[bg];"
        f"[1:v]loop=loop=-1:size={n_frames}:start=0,fps={FPS}[chars];"
        f"color=c=white:s={ref.W}x{ref.H}:r={FPS}:d={clip_len:.3f}[cv];"
        f"[cv][bg]overlay={CARDX}:{CARDY}[s1];"
        f"[s1][chars]overlay=0:0[s2];"
        f"[s2][2:v]overlay=0:0[v]"
    )
    bg_in = (["-stream_loop", "-1", "-i", str(bg_path)] if bg_is_video
             else ["-loop", "1", "-i", str(bg_path)])
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        *bg_in,
        "-framerate", str(FPS), "-i", str(anim_dir / "anim_%03d.png"),
        "-i", str(ui_png),
        "-filter_complex", fc,
        "-map", "[v]", "-t", f"{clip_len:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(FPS), str(clip),
    ]
    subprocess.run(cmd, check=True)
    return clip, credits


def _xfade_concat(ep_dir: Path, clips: list[Path], scene_durs: list[float]) -> Path:
    """장면 클립들을 xfade(크로스페이드)로 이어붙인 무음 영상 → xfade.mp4.

    각 클립은 scene_dur+XFADE 길이. 누적 장면시간을 offset으로 줘 전환이 정확히
    오디오 cue 경계에서 일어나게 한다(총 길이는 오디오 길이 + XFADE → mux에서 -shortest로 정리).
    """
    out = ep_dir / "xfade.mp4"
    if len(clips) == 1:
        return clips[0]

    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c.relative_to(ep_dir))]
    filt: list[str] = []
    prev = "0:v"
    cum = 0.0
    for i in range(1, len(clips)):
        cum += scene_durs[i - 1]
        label = f"x{i}"
        filt.append(
            f"[{prev}][{i}:v]xfade=transition=fade:duration={XFADE}:"
            f"offset={cum:.3f}[{label}]")
        prev = label
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(filt),
         "-map", f"[{prev}]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out.name],
        cwd=ep_dir, check=True)
    return out


def produce_real(topic: str, story_file: str, notify: bool = False,
                 bgm: str | None = None) -> dict:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ep_dir = SHORTS_DIR / f"{stamp}-real-{_slug(topic)}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    story = json.loads(Path(story_file).read_text(encoding="utf-8"))
    (ep_dir / "story.json").write_text(
        json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes = story["scenes"]
    print(f"  제목: {story['title']} / 장면 {len(scenes)}개")

    print("▸ TTS 합성 (edge-tts)…")
    manifest = tts.synthesize([s["text"] for s in scenes], ep_dir)
    print(f"  오디오 {manifest['duration']:.1f}초")
    if len(manifest["cues"]) != len(scenes):
        raise RuntimeError(
            f"cue {len(manifest['cues'])}개 ≠ 장면 {len(scenes)}개")

    durs = _scene_durations(manifest["cues"], manifest["duration"])

    print("▸ 장면별 합성 (실사 배경 + 스틱 캐릭터 + UI)…")
    clips: list[Path] = []
    credits_all: list[dict] = []
    real_count = 0
    for i, (scene, d) in enumerate(zip(scenes, durs)):
        clip, credits = _scene_clip(i, scene, story, d, ep_dir)
        clips.append(clip)
        if credits:
            credits_all.append(credits)
            real_count += 1
        print(f"  [{i+1}/{len(scenes)}] {d:.1f}s "
              f"{'실사:' + credits['query'] if credits else '2D 폴백'}")

    out = ep_dir / "final.mp4"
    if XFADE > 0 and len(clips) > 1:
        print(f"▸ 장면 전환(xfade {XFADE}s) + 오디오 mux…")
        xf = _xfade_concat(ep_dir, clips, durs)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-i", xf.name, "-i", Path(manifest["audio"]).name,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", out.name],
            cwd=ep_dir, check=True)
        xf.unlink(missing_ok=True)
    else:
        # 하드컷(동일 인코딩 파라미터 → copy 안전)
        print("▸ concat + 오디오 mux…")
        concat_txt = ep_dir / "clips.txt"
        concat_txt.write_text(
            "\n".join(f"file 'work/{c.name}'" for c in clips) + "\n", encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "concat", "-safe", "0", "-i", "clips.txt",
             "-i", Path(manifest["audio"]).name,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", out.name],
            cwd=ep_dir, check=True)
    size_mb = out.stat().st_size / 1e6
    print(f"  완료: {out} ({size_mb:.1f}MB)")

    result = {
        "episode_dir": str(ep_dir), "video": str(out),
        "title": story["title"], "duration": round(manifest["duration"], 1),
        "scenes": len(scenes), "real_bg_scenes": real_count,
        "style": "real", "credits": credits_all,
    }

    if bgm:
        from pipelines.shorts import bgm as bgm_mod
        bgm_path, bgm_credits = bgm_mod.resolve_track(bgm)
        mixed = ep_dir / "final_bgm.mp4"
        print(f"▸ BGM 합성 ({bgm_path.name})…")
        out = bgm_mod.mix(out, bgm_path, mixed)
        result["video"] = str(out)
        result["bgm"] = {"file": bgm_path.name, "credits": bgm_credits}

    (ep_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if notify:
        from channel.notify import send
        send(f"🎬 실사합성 쇼츠 완료\n제목: {story['title']}\n"
             f"장면 {len(scenes)}개(실사 {real_count}) / {result['duration']}초\n파일: {out}",
             title="shorts-real", level="ok")
    return result


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.produce_real")
    p.add_argument("topic")
    p.add_argument("--story", required=True, help="스토리 JSON 경로")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--bgm", default=None)
    args = p.parse_args()
    try:
        result = produce_real(args.topic, args.story, args.notify, args.bgm)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[produce_real] ffmpeg 실패: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[produce_real] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
