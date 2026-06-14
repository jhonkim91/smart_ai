"""유사도 측정: 생성본 프레임 vs 원본 레퍼런스 프레임 SSIM.

레이아웃(헤더/제목/카드/자막)이 원본과 얼마나 일치하는지 객관 점수를 낸다.
이 점수는 autotune의 목적함수이자 진척 보고용 지표다. 배경/캐릭터 영역은
원본 소스 자산이 없어 픽셀 일치가 불가하므로, 영역별 분해로 '맞출 수 있는
부분(레이아웃)'과 '구조적 한계(배경/캐릭터)'를 분리해 보여준다.

사용:
    python -m pipelines.shorts.compare gen.png ref.jpg            # 프레임 1쌍
    python -m pipelines.shorts.compare gen.mp4 ref.webm --frames 8  # 영상 샘플 평균
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

W, H = 1080, 1920
# 세로 비율 기준 영역(상단y, 하단y) — 레이아웃 일치를 영역별로 측정
REGIONS = {
    "header": (0.03, 0.16),    # 브랜드/로고
    "title": (0.16, 0.21),     # 제목 텍스트
    "card": (0.21, 0.62),      # 장면 카드(배경/캐릭터 — 구조적 한계 영역)
    "subtitle": (0.55, 0.66),  # 자막 박스
}


def _to_gray(path: Path) -> np.ndarray:
    img = Image.open(path).convert("L").resize((W, H))
    return np.asarray(img, dtype=np.float64)


def score_images(gen_path, ref_path) -> dict:
    """두 프레임의 전체 + 영역별 SSIM(0~1)."""
    g, r = _to_gray(Path(gen_path)), _to_gray(Path(ref_path))
    overall = float(ssim(g, r, data_range=255))
    regions = {}
    for name, (y0, y1) in REGIONS.items():
        a, b = int(y0 * H), int(y1 * H)
        regions[name] = float(ssim(g[a:b], r[a:b], data_range=255))
    # 레이아웃 점수 = 배경/캐릭터(card) 제외한 UI 영역 평균(맞출 수 있는 부분)
    layout = float(np.mean([regions["header"], regions["title"], regions["subtitle"]]))
    return {"overall": round(overall, 4), "layout": round(layout, 4),
            "regions": {k: round(v, 4) for k, v in regions.items()}}


def _extract_frame(video: Path, t: float, out: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
         "-frames:v", "1", str(out)], check=True)
    return out


def _duration(video: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def score_videos(gen: Path, ref: Path, frames: int = 8) -> dict:
    """두 영상에서 같은 상대 시점 N프레임을 뽑아 평균 SSIM."""
    gd, rd = _duration(gen), _duration(ref)
    samples = []
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for i in range(frames):
            frac = (i + 0.5) / frames
            gp = _extract_frame(gen, gd * frac, tdp / f"g{i}.png")
            rp = _extract_frame(ref, rd * frac, tdp / f"r{i}.png")
            samples.append(score_images(gp, rp))
    keys = ("overall", "layout")
    avg = {k: round(float(np.mean([s[k] for s in samples])), 4) for k in keys}
    region_keys = samples[0]["regions"].keys()
    avg["regions"] = {k: round(float(np.mean([s["regions"][k] for s in samples])), 4)
                      for k in region_keys}
    avg["frames"] = frames
    return avg


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.compare")
    p.add_argument("generated")
    p.add_argument("reference")
    p.add_argument("--frames", type=int, default=0,
                   help=">0이면 영상으로 보고 N프레임 샘플 평균")
    args = p.parse_args()
    gen, ref = Path(args.generated), Path(args.reference)
    try:
        result = (score_videos(gen, ref, args.frames) if args.frames > 0
                  else score_images(gen, ref))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[compare] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
