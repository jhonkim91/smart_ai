"""단일 대표 프레임 렌더(현재 tuning.json 반영). autotune의 서브프로세스 평가용.

reference_style.draw_frame로 story의 한 장면을 PNG로 렌더한다. 별도 프로세스로
실행되므로 매번 최신 tuning.json을 새로 import해 반영한다.

사용:
    python -m pipelines.shorts.render_one --story s.json --index 0 --out frame.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipelines.shorts import reference_style as ref


def render(story_path: str, index: int, out: str) -> str:
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))
    scene = story["scenes"][index]
    ref.draw_frame(
        out,
        title=story["title"],
        brand=story.get("brand") or "댕소리",
        brand_sub=story.get("brand_sub") or "오늘의 실화 썰",
        scene=scene.get("scene") or scene,
        subtitle=scene.get("subtitle") or scene["text"],
        highlights=scene.get("highlights") or {},
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.render_one")
    p.add_argument("--story", required=True)
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        print(render(args.story, args.index, args.out))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[render_one] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
