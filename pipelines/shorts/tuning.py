"""레이아웃 튜닝 파라미터 저장소.

autotune이 SSIM을 최대화하며 찾은 최적 레이아웃 값을 data/tune/params.json에
영속화하고, reference_style이 import 시 이 값을 읽어 카드/제목/자막 위치에 반영한다.
파일이 없거나 키가 빠지면 DEFAULTS로 폴백한다(기존 동작 보존).

판단 로직 아님 — 단순 값 저장/로드. 개선 판단은 autotune(세션 계층 코드)이 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from hermes.config import DATA_DIR

PARAMS_PATH = DATA_DIR / "tune" / "params.json"

# 현재 reference_style의 검증된 기본값과 동일하게 시작한다.
DEFAULTS: dict = {
    "card_x0": 20,
    "card_y0": 380,
    "card_x1": 1060,
    "card_y1": 1240,
    "card_radius": 44,
    "title_gap": 180,     # 카드 상단에서 제목 영역까지 위로 띄우는 거리(px)
    "title_size": 66,     # 제목 최대 폰트(px)
    "sub_size": 58,       # 자막 최대 폰트(px)
    "sub_bottom": 0,      # 자막 박스 하단을 카드 하단(CARD_Y1) 기준 오프셋(px, +면 아래로)
}

# autotune이 탐색하는 파라미터의 (최소, 최대, 1스텝 크기). 키가 여기 있으면 탐색 대상.
SEARCH_SPACE: dict = {
    "card_y0": (300, 460, 8),
    "card_y1": (1140, 1320, 8),
    "card_x0": (8, 60, 6),
    "title_gap": (130, 230, 8),
    "title_size": (54, 76, 2),
    "sub_size": (46, 66, 2),
    "sub_bottom": (-40, 40, 6),
}


def load() -> dict:
    """저장된 파라미터(없는 키는 DEFAULTS로 보충)."""
    p = dict(DEFAULTS)
    if PARAMS_PATH.exists():
        try:
            p.update(json.loads(PARAMS_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — 깨진 파일이면 기본값 유지
            pass
    # card_x1은 좌우 대칭 마진으로 강제(캔버스 폭 1080 기준)
    p["card_x1"] = 1080 - p["card_x0"]
    return p


def save(params: dict) -> None:
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_PATH.write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")


def card(params: dict | None = None) -> tuple[int, int, int, int]:
    p = params or load()
    return (p["card_x0"], p["card_y0"], p["card_x1"], p["card_y1"])
