"""렌더링 단계: FFmpeg로 1080x1920 세로 영상 합성.

이 환경의 ffmpeg 빌드에는 libass/freetype(자막·drawtext)이 없어서,
텍스트는 Pillow로 투명 PNG에 그린 뒤 overlay 필터로 시간 구간별 합성한다.

구성: 배경 그라디언트 + 상단 고정 제목 + 하단 자막(문장별 enable 구간) + TTS 오디오.

사용:
    python -m pipelines.shorts.render <에피소드 디렉토리>
    (디렉토리에 script.json / voice.m4a / tts_manifest.json 필요 — produce가 만든다)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # macOS 기본 한글 폰트
TITLE_SIZE, SUB_SIZE = 58, 64
SUB_BOTTOM_MARGIN = 240  # 자막 기준선(하단에서)


def _font(size: int):
    from PIL import ImageFont
    return ImageFont.truetype(FONT, size)


def _wrap(text: str, font, max_w: int) -> list[str]:
    """픽셀 폭 기준 단어 줄바꿈."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _text_png(text: str, size: int, out: Path, y_anchor: str) -> None:
    """1080x1920 투명 캔버스에 외곽선 있는 텍스트를 그린다.

    y_anchor: "top"(제목, y=180 박스) | "bottom"(자막, 하단 여백 위)
    """
    from PIL import Image, ImageDraw

    font = _font(size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines = _wrap(text, font, W - 160)
    line_h = int(size * 1.35)
    block_h = line_h * len(lines)
    y0 = 180 if y_anchor == "top" else H - SUB_BOTTOM_MARGIN - block_h

    if y_anchor == "top":  # 제목 뒤 반투명 박스
        pad = 28
        widths = [font.getlength(ln) for ln in lines]
        bw = max(widths) + pad * 2
        d.rounded_rectangle(
            [(W - bw) / 2, y0 - pad, (W + bw) / 2, y0 + block_h + pad],
            radius=20, fill=(16, 24, 32, 150))

    for i, ln in enumerate(lines):
        lw = font.getlength(ln)
        d.text(((W - lw) / 2, y0 + i * line_h), ln, font=font,
               fill=(255, 255, 255, 255),
               stroke_width=max(2, size // 16), stroke_fill=(16, 24, 32, 255))
    img.save(out)


def render(episode_dir: Path) -> Path:
    script = json.loads((episode_dir / "script.json").read_text(encoding="utf-8"))
    manifest = json.loads((episode_dir / "tts_manifest.json").read_text(encoding="utf-8"))
    audio = episode_dir / "voice.m4a"
    dur = manifest["duration"] + 0.5
    out = episode_dir / "final.mp4"

    # 1) 텍스트 PNG 생성 (제목 1 + 자막 N)
    ov_dir = episode_dir / "overlays"
    ov_dir.mkdir(exist_ok=True)
    title_png = ov_dir / "title.png"
    _text_png(script["title"], TITLE_SIZE, title_png, "top")
    cue_pngs = []
    for i, cue in enumerate(manifest["cues"]):
        p = ov_dir / f"cue_{i:03d}.png"
        _text_png(cue["text"], SUB_SIZE, p, "bottom")
        cue_pngs.append((p, cue["start"], cue["end"]))

    # 2) overlay 체인 구성 (still PNG는 eof_action=repeat로 유지)
    inputs = ["-f", "lavfi",
              "-i", f"gradients=s={W}x{H}:c0=0x0F2027:c1=0x2C5364:duration={dur:.2f}:rate=30",
              "-i", str(audio), "-i", str(title_png)]
    chains = ["[0:v][2:v]overlay=0:0:eof_action=repeat[v0]"]
    for i, (p, s, e) in enumerate(cue_pngs):
        inputs += ["-i", str(p)]
        chains.append(
            f"[v{i}][{i + 3}:v]overlay=0:0:eof_action=repeat:"
            f"enable='between(t,{s:.3f},{e:.3f})'[v{i + 1}]")
    last = f"v{len(cue_pngs)}"

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", ";".join(chains),
           "-map", f"[{last}]", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    return out


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.render")
    p.add_argument("episode_dir")
    args = p.parse_args()
    try:
        print(render(Path(args.episode_dir)))
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[render] ffmpeg 실패: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[render] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
