"""Pexels 무료 스톡영상 배경 수집기.

장면 키워드(또는 한국어 자막에서 매핑한 영어 쿼리)로 세로형 실사 클립을 검색·
다운로드하고 data/stock/에 캐시한다. 같은 쿼리는 재다운로드하지 않는다.
저작권: Pexels 라이선스(무료, 상업적 사용 가능, 출처표기 권장)를 credits로 반환한다.

API 키는 hermes.config.PEXELS_API_KEY(.env의 PEXELS_API_KEY). 키가 없거나
검색 실패 시 None을 반환해 호출 측이 2D 폴백을 쓰도록 한다.

사용:
    python -m pipelines.shorts.stock_bg "airplane interior" --orientation portrait
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests

from hermes.config import PEXELS_API_KEY, STOCK_DIR

SEARCH_URL = "https://api.pexels.com/videos/search"
TIMEOUT = 30

# 한국어 장면 의미 → 영어 검색어. story JSON의 scene.bg 또는 scene.query로 직접 지정도 가능.
BG_QUERY = {
    "night": "city night skyline aerial",
    "room": "cozy living room interior",
    "street": "empty street walking",
    "sky": "sky clouds aerial falling",
    "office": "police office desk",
    "alert": "dark dramatic storm",
    "airplane": "skydiving airplane interior",
    "farm": "rural farm field countryside",
    "hospital": "hospital corridor empty",
    "court": "courtroom justice",
    "cafe": "cafe coffee shop interior",
}


def _cache_path(query: str) -> Path:
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
    safe = "".join(c if c.isalnum() else "_" for c in query)[:30]
    return STOCK_DIR / f"{safe}_{h}.mp4"


def resolve_query(scene: dict) -> str:
    """scene에서 검색어 결정: 명시적 query > bg 매핑 > 'cinematic'."""
    if scene.get("query"):
        return str(scene["query"])
    return BG_QUERY.get(scene.get("bg", ""), "cinematic background")


def _pick_file(video: dict, want_portrait: bool) -> str | None:
    """Pexels video 객체에서 적당한 해상도의 mp4 link를 고른다.

    세로형 쇼츠라 height>=width이고 높이 720~1920 사이를 우선한다.
    없으면 가장 큰 link로 폴백.
    """
    files = video.get("video_files", [])
    if not files:
        return None

    def score(f: dict) -> tuple:
        w, h = f.get("width") or 0, f.get("height") or 0
        portrait = h >= w
        # 1080~1920 높이 선호, 세로형 가산
        ideal = -abs((h or 0) - 1280)
        return (portrait == want_portrait, ideal)

    best = max(files, key=score)
    return best.get("link")


def fetch(query: str, *, orientation: str = "portrait", cache: bool = True) -> tuple[Path, dict] | None:
    """query로 스톡영상 1개를 받아 (경로, credits) 반환. 실패 시 None."""
    out = _cache_path(query)
    meta_path = out.with_suffix(".json")
    if cache and out.exists() and meta_path.exists():
        return out, json.loads(meta_path.read_text(encoding="utf-8"))

    if not PEXELS_API_KEY:
        return None

    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(
            SEARCH_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": orientation,
                    "per_page": 5, "size": "medium"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        if not videos:
            return None
        video = videos[0]
        link = _pick_file(video, orientation == "portrait")
        if not link:
            return None

        with requests.get(link, stream=True, timeout=TIMEOUT) as dl:
            dl.raise_for_status()
            with out.open("wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)

        credits = {
            "source": "Pexels",
            "query": query,
            "author": video.get("user", {}).get("name", ""),
            "url": video.get("url", ""),
            "license": "Pexels License (free, attribution appreciated)",
        }
        meta_path.write_text(json.dumps(credits, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return out, credits
    except Exception as e:  # noqa: BLE001
        print(f"[stock_bg] 검색/다운로드 실패({query}): {e}", file=sys.stderr)
        return None


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.stock_bg")
    p.add_argument("query")
    p.add_argument("--orientation", default="portrait",
                   choices=("portrait", "landscape", "square"))
    args = p.parse_args()
    res = fetch(args.query, orientation=args.orientation)
    if not res:
        print("[stock_bg] 결과 없음 (키 미설정이거나 검색 실패)", file=sys.stderr)
        return 1
    path, credits = res
    print(json.dumps({"path": str(path), "credits": credits}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
