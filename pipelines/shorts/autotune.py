"""자동 레이아웃 튜닝 루프 — SSIM(생성본 vs 원본 프레임)을 최대화.

좌표하강(coordinate descent)으로 tuning.SEARCH_SPACE의 파라미터를 한 축씩
±step 움직여 점수가 오르면 채택한다. 매 평가는 서브프로세스 render_one으로
현재 파라미터의 단일 프레임을 렌더해 레퍼런스 프레임과 SSIM을 잰다.

이것이 "자동으로 계속 개선" 루프의 1회 실행 단위다. n8n이 스케줄로 이걸 트리거하고,
점수/이력을 Discord로 보고한다. 코드 패치 같은 판단은 여기(세션 계층)와 HITL이 한다.
배경/캐릭터는 원본 소스 자산이 없어 픽셀 일치가 불가하므로 점수는 레이아웃 정합의
상한에서 수렴한다(100% 도달 아님 — 측정 가능한 최대치 수렴).

사용:
    python -m pipelines.shorts.autotune --iters 40
    python -m pipelines.shorts.autotune --iters 40 --report   # 끝에 Discord 보고
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from hermes.config import DATA_DIR
from pipelines.shorts import compare, tuning

REF_FRAME = DATA_DIR / "reference" / "frame_001.jpg"
STORY = DATA_DIR / "reference" / "story_real_parachute.json"
SCENE_INDEX = 0
HISTORY = DATA_DIR / "tune" / "history.jsonl"
PYTHON = sys.executable


def _evaluate(params: dict, work: Path) -> float:
    """params를 tuning.json에 쓰고 1프레임 렌더 → 레퍼런스와 layout SSIM."""
    tuning.save(params)
    out = work / "cand.png"
    r = subprocess.run(
        [PYTHON, "-m", "pipelines.shorts.render_one",
         "--story", str(STORY), "--index", str(SCENE_INDEX), "--out", str(out)],
        capture_output=True, text=True)
    if r.returncode != 0:
        return -1.0
    s = compare.score_images(out, REF_FRAME)
    # 목적함수: 레이아웃(헤더+제목+자막) 정합. 배경/캐릭터(card)는 구조적 한계라 제외.
    return s["layout"]


def _log(entry: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def autotune(iters: int = 40) -> dict:
    if not REF_FRAME.exists():
        raise FileNotFoundError(f"레퍼런스 프레임 없음: {REF_FRAME}")
    stamp = datetime.datetime.now().isoformat(timespec="seconds")

    best = tuning.load()
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        best_score = _evaluate(best, work)
        start_score = best_score
        evals = 1

        improved = True
        while improved and evals < iters:
            improved = False
            for key, (lo, hi, step) in tuning.SEARCH_SPACE.items():
                if evals >= iters:
                    break
                for delta in (step, -step):
                    if evals >= iters:
                        break
                    cand = dict(best)
                    cand[key] = max(lo, min(hi, best[key] + delta))
                    if cand[key] == best[key]:
                        continue
                    score = _evaluate(cand, work)
                    evals += 1
                    if score > best_score + 1e-4:
                        best, best_score = cand, score
                        improved = True
                        print(f"  ↑ {key} {best[key]} → layout={best_score:.4f} (eval {evals})")
                        break

        tuning.save(best)  # 최종 best 영속화

    result = {
        "ts": stamp, "evals": evals,
        "start_layout": round(start_score, 4),
        "best_layout": round(best_score, 4),
        "gain": round(best_score - start_score, 4),
        "params": best,
    }
    _log(result)
    return result


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.autotune")
    p.add_argument("--iters", type=int, default=40, help="최대 평가 횟수(렌더 수)")
    p.add_argument("--report", action="store_true", help="끝에 Discord 보고")
    args = p.parse_args()
    try:
        result = autotune(args.iters)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.report:
            from channel.notify import send
            send(f"🔧 레이아웃 자동튜닝 1회 완료\n"
                 f"layout SSIM {result['start_layout']} → {result['best_layout']} "
                 f"(Δ{result['gain']:+.4f}, {result['evals']}평가)",
                 title="autotune", level="ok")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[autotune] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
