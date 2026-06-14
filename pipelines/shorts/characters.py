"""캐릭터 레지스트리 — 정체성(색·소품)을 고정하고 장면은 표정/포즈/위치만 덮어쓴다.

딥리서치 보고서의 'character.yaml 중심 운영' 원칙을 결정론적 2D 렌더러에 맞게 적용한다.
우리 캐릭터는 코드로 그려져 생성 드리프트는 0이지만, 사람이 장면마다 색·소품을 손으로
적다 보면 같은 인물이 장면 간 색이 바뀌는 '수동 드리프트'가 생긴다. 레지스트리가 그걸 막는다.

story scene의 chars 항목 사용법:
    {"char": "wife", "x": 0.5, "expr": "shock", "pose": "spread"}   # 레지스트리 참조
    {"color": "#FF8EC7", "x": 0.5, "expr": "shock"}                  # 인라인(하위호환)

resolve(spec): char 참조면 레지스트리 정체성 + 장면 override(overridable만) 병합.
locked 필드(color/prop)는 장면이 덮어써도 무시해 정체성을 보존한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REGISTRY_PATH = Path(__file__).with_name("characters.json")


@lru_cache(maxsize=1)
def load() -> dict:
    if not _REGISTRY_PATH.exists():
        return {"locked": [], "overridable": [], "characters": {}}
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def resolve(spec: dict) -> dict:
    """char 참조 스펙을 정체성+override 병합 스펙으로 변환. 인라인이면 그대로 반환."""
    cid = spec.get("char")
    if not cid:
        return spec  # 인라인 스펙 — 하위호환
    reg = load()
    base = reg.get("characters", {}).get(cid)
    if not base:
        # 미정의 char id → 인라인 필드만이라도 살려서 그린다
        return {k: v for k, v in spec.items() if k != "char"}
    locked = set(reg.get("locked", []))
    out = {k: v for k, v in base.items() if k not in ("display", "signature")}
    for k, v in spec.items():
        if k == "char" or k in locked:
            continue  # 정체성(color/prop) override는 무시 → 드리프트 방지
        out[k] = v
    return out


def resolve_all(chars: list) -> list:
    return [resolve(c) for c in (chars or [])]
