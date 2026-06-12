"""트렌드 수집 파이프라인.

RSS + YouTube mostPopular(KR)를 수집해 Ollama로 쇼츠 주제 5개를 제안하고,
bus에 kind=draft로 적재한 뒤 Discord로 후보 목록을 보고한다.
영상 생산·업로드는 자동 트리거하지 않는다 — 주제 제안까지만.
후보 선택과 forge 위임은 HERMES/사람이 결정한다.

사용:
    python -m pipelines.shorts.trends
    python -m pipelines.shorts.trends --dry-run   # bus/Discord 없이 stdout만
"""
from __future__ import annotations

import argparse
import sys
from typing import NamedTuple

from channel.notify import send as notify
from hermes import bus
from hermes.config import TREND_RSS_FEEDS, YOUTUBE_API_KEY
from hermes.ollama_worker import run as ollama


class Headline(NamedTuple):
    title: str
    source: str


def _fetch_rss(feeds: list[str]) -> tuple[list[Headline], list[str]]:
    """피드 목록에서 최신 헤드라인을 수집한다.

    Returns:
        (성공 헤드라인 목록, 실패 URL 목록)
    """
    import feedparser  # 지연 임포트: feedparser 미설치 환경 방어

    headlines: list[Headline] = []
    failed: list[str] = []

    for url in feeds:
        try:
            d = feedparser.parse(url)
            # bozo=True + 항목 없음 → 파싱 실패 피드로 처리
            if d.get("bozo") and not d.entries:
                print(f"[trends] 빈 피드 또는 파싱 오류: {url}", file=sys.stderr)
                failed.append(url)
                continue
            for entry in d.entries[:10]:
                title = getattr(entry, "title", "").strip()
                if title:
                    headlines.append(Headline(title=title, source="rss"))
        except Exception as exc:
            print(f"[trends] RSS 수집 오류 {url}: {exc}", file=sys.stderr)
            failed.append(url)

    return headlines, failed


def _fetch_youtube_popular(
    api_key: str, region: str = "KR", n: int = 20
) -> list[Headline]:
    """YouTube mostPopular 차트에서 영상 제목을 수집한다 (1 unit/call)."""
    import requests

    params = {
        "part": "snippet",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": n,
        "key": api_key,
    }
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        return [
            Headline(title=item["snippet"]["title"], source="youtube")
            for item in items
            if item.get("snippet", {}).get("title")
        ]
    except Exception as exc:
        print(f"[trends] YouTube API 오류: {exc}", file=sys.stderr)
        return []


def _generate_candidates(headlines: list[Headline]) -> list[str]:
    """Ollama(classify → title)로 쇼츠 주제 후보 5개를 생성한다."""
    if not headlines:
        return []

    combined = "\n".join(f"- {h.title}" for h in headlines[:30])
    category_labels = (
        "건강/습관,기술/AI,재테크/경제,라이프스타일,시사/사회,교육/자기계발,엔터테인먼트"
    )

    # 1) classify: 전체 헤드라인에서 지배적 트렌드 카테고리 추출
    category = ollama("classify", combined, labels=category_labels).strip()
    print(f"[trends] 분류 결과: {category}", file=sys.stderr)

    # 2) title: 카테고리 + 상위 헤드라인으로 제목 후보 5개 생성
    context = f"트렌드 카테고리: {category}\n\n주요 헤드라인:\n{combined}"
    raw = ollama("title", context)

    candidates: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # 섹션 헤더(### 제목 후보:)와 해시태그 줄 건너뜀
        if stripped.startswith("#"):
            continue
        # "제목 후보:", "해시태그 후보:" 같은 레이블 건너뜀
        if stripped.endswith(":") and len(stripped) < 20:
            continue
        # 번호 목록 형식: "1. 제목" 또는 '1. "제목"'
        if stripped[0].isdigit() and ". " in stripped:
            candidate = stripped.split(". ", 1)[1].strip()
        else:
            candidate = stripped
        # 앞뒤 따옴표 제거 (일반 따옴표 및 유니코드 따옴표)
        candidate = candidate.strip('"\'""“”')
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= 5:
            break

    return candidates[:5]


def run(dry_run: bool = False) -> int:
    feeds = TREND_RSS_FEEDS
    if not feeds:
        notify(
            "TREND_RSS_FEEDS 미설정 — .env에 RSS URL을 쉼표로 추가하세요.",
            title="trends",
            level="warn",
        )
        return 1

    # --- RSS 수집 ---
    headlines, failed_feeds = _fetch_rss(feeds)

    # --- YouTube 수집 (선택) ---
    if YOUTUBE_API_KEY:
        yt = _fetch_youtube_popular(YOUTUBE_API_KEY)
        headlines.extend(yt)
        print(f"[trends] YouTube {len(yt)}건 추가", file=sys.stderr)
    else:
        print("[trends] YOUTUBE_API_KEY 미설정 — YouTube 수집 건너뜀", file=sys.stderr)

    # --- 전체 실패 시 warn 알림 후 종료 ---
    if not headlines:
        notify(
            f"트렌드 수집 완전 실패 — RSS {len(failed_feeds)}개 오류, 헤드라인 0건",
            title="trends",
            level="warn",
        )
        return 1

    # --- 일부 피드 실패 시 warn 보고 (수집은 계속) ---
    if failed_feeds:
        notify(
            "일부 RSS 피드 수집 실패 ({}개): {}".format(
                len(failed_feeds),
                ", ".join(failed_feeds[:3]) + (" ..." if len(failed_feeds) > 3 else ""),
            ),
            title="trends",
            level="warn",
        )

    print(f"[trends] 수집 헤드라인: {len(headlines)}건", file=sys.stderr)

    # --- Ollama 주제 생성 ---
    try:
        candidates = _generate_candidates(headlines)
    except Exception as exc:
        notify(f"Ollama 주제 생성 실패: {exc}", title="trends", level="error")
        return 1

    if not candidates:
        notify("Ollama가 후보를 생성하지 못했습니다.", title="trends", level="warn")
        return 1

    # --- Bus 적재 (kind=draft) ---
    task_ids: list[int] = []
    if not dry_run:
        for candidate in candidates:
            tid = bus.add_task(
                title=candidate,
                body=f"트렌드 수집 자동 제안 (헤드라인 {len(headlines)}건 기반)",
                kind="draft",
            )
            task_ids.append(tid)

    # --- Discord 보고 ---
    bullet = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
    ids_note = (
        f" (task #{', #'.join(map(str, task_ids))})" if task_ids else " [dry-run]"
    )
    message = (
        f"**오늘의 쇼츠 주제 후보 {len(candidates)}개**{ids_note}\n\n"
        f"{bullet}\n\n"
        f"_헤드라인 {len(headlines)}건 수집 · 후보 선택 후 forge로 전달하세요_"
    )

    if dry_run:
        print(message)
    else:
        notify(message, title="🎯 트렌드 수집", level="ok")

    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.trends")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="bus/Discord 기록 없이 stdout으로만 출력",
    )
    args = p.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
