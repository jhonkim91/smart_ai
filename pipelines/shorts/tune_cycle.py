"""자동 개선 1사이클 — n8n/launchd가 스케줄로 트리거하는 진입점.

흐름:
  1) autotune 1회(레이아웃 SSIM 좌표하강) → best 파라미터 영속화
  2) Discord 보고(점수 변화)
  3) 수렴(plateau)했고 목표 미달이면 HITL 작업을 bus에 등록 →
     다음 HERMES(Claude) 세션이 '코드 개선'(판단 영역)을 이어받는다.

원칙1 준수: n8n은 이 스크립트를 '트리거'만 한다. 측정/탐색/에스컬레이션 판단은
세션 계층 코드(여기)에 있다. 100% 픽셀 동일은 원본 소스 자산이 없어 불가하므로
목표는 '측정 가능한 레이아웃 정합 상한 수렴 + 한계 도달 시 사람/HERMES 인계'다.

사용:
    python -m pipelines.shorts.tune_cycle --iters 40
    python -m pipelines.shorts.tune_cycle --iters 40 --target 0.85
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from pipelines.shorts import autotune

PYTHON = sys.executable
PLATEAU_EPS = 0.002  # 이 미만 향상이면 수렴으로 본다


def _notify(msg: str, level: str = "ok") -> None:
    try:
        from channel.notify import send
        send(msg, title="tune-cycle", level=level)
    except Exception as e:  # noqa: BLE001 — 알림 실패가 사이클을 막지 않게
        print(f"[tune_cycle] 알림 실패: {e}", file=sys.stderr)


def _open_autotune_task() -> str | None:
    """이미 열려 있는 autotune 인계 작업 id(중복 등록 방지)."""
    r = subprocess.run(
        [PYTHON, "-m", "hermes.bus", "list", "--status", "queued"],
        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        for t in json.loads(r.stdout):
            if t.get("kind") == "autotune":
                return str(t.get("id"))
    except Exception:  # noqa: BLE001
        pass
    return None


def _escalate(result: dict, target: float) -> str | None:
    """수렴+목표미달 → HITL 작업 등록(다음 세션이 코드 개선 인계).

    이미 열린 autotune 작업이 있으면 새로 만들지 않는다(6시간 루프 스팸 방지).
    """
    existing = _open_autotune_task()
    if existing:
        return existing
    title = f"[autotune] 레이아웃 SSIM {result['best_layout']} 수렴 — 코드 개선 필요"
    body = (
        f"자동튜닝이 파라미터 한계에 수렴(Δ{result['gain']:+.4f}). "
        f"목표 {target} 미달({result['best_layout']}). "
        "파라미터 탐색만으로 더 못 올림 — 렌더러 코드(폰트/자간/카드 곡률/캐릭터 "
        "스타일) 개선이 필요. 현재 best params: " + json.dumps(result["params"], ensure_ascii=False)
    )
    r = subprocess.run(
        [PYTHON, "-m", "hermes.bus", "add", title, "--body", body, "--kind", "autotune"],
        capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    print(f"[tune_cycle] bus 등록 실패: {r.stderr}", file=sys.stderr)
    return None


def run(iters: int, target: float, quiet: bool = False) -> dict:
    result = autotune.autotune(iters)
    plateaued = result["gain"] < PLATEAU_EPS
    below_target = result["best_layout"] < target

    msg = (f"🔧 자동튜닝 1사이클\n"
           f"layout SSIM {result['start_layout']} → {result['best_layout']} "
           f"(Δ{result['gain']:+.4f}, {result['evals']}평가)")
    task_id = None
    if plateaued and below_target:
        task_id = _escalate(result, target)
        msg += f"\n⚠️ 수렴·목표({target}) 미달 → HERMES 인계 작업 등록 {task_id or '(실패)'}"
    elif not below_target:
        msg += f"\n✅ 목표 {target} 달성"
    if not quiet:  # n8n이 보고를 맡으면 --quiet로 자체 알림 억제(중복 방지)
        _notify(msg)

    result["plateaued"] = plateaued
    result["below_target"] = below_target
    result["escalated_task"] = task_id
    return result


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.tune_cycle")
    p.add_argument("--iters", type=int, default=40)
    p.add_argument("--target", type=float, default=0.85,
                   help="layout SSIM 목표(미달+수렴 시 HITL 인계)")
    p.add_argument("--quiet", action="store_true",
                   help="자체 Discord 알림 억제(n8n이 보고를 맡을 때)")
    args = p.parse_args()
    try:
        result = run(args.iters, args.target, args.quiet)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[tune_cycle] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
