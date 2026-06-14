"""에이전트 가동 계측 — 누가 어느 작업을 잡고/끝냈는지 구조화 기록.

run_events에 `{"agent","stage","kind"}` payload를 남겨 대시보드 병렬 뷰가
레인을 점등할 수 있게 한다. worker(자동)와 HERMES 위임(수동/CLI)이 공용으로 호출한다.

CLI (HERMES가 서브에이전트에 위임할 때):
    python -m hermes.activity start <task_id> <agent> [--kind code]   # 위임 시작
    python -m hermes.activity done  <task_id> <agent> [--kind code]   # 완료
    python -m hermes.activity fail  <task_id> <agent> [--note "사유"]  # 실패

예: forge에 #20 위임
    python -m hermes.activity start 20 forge --kind code
    ... (forge 작업) ...
    python -m hermes.activity done 20 forge --kind code
"""
from __future__ import annotations

import argparse
import sys

from hermes import bus

STAGES = ("claimed", "done", "failed")

# router 레인 이름과 일치해야 대시보드가 매칭한다(dashboard.queries.AGENT_LANES).
KNOWN_AGENTS = (
    "ollama", "forge", "atlas", "probe", "warden",
    "oracle", "scribe", "augur", "herald",
)


def mark(task_id: int, agent: str, stage: str, *, kind: str = "general",
         note: str = "", level: str = "info") -> int:
    """가동 이벤트 1건 기록. stage in {claimed, done, failed}."""
    stage = stage if stage in STAGES else "claimed"
    label = {"claimed": "잡음", "done": "완료", "failed": "실패"}[stage]
    msg = f"{agent} {label} #{task_id} ({kind})" + (f" — {note}" if note else "")
    return bus.log_event(
        task_id, msg, level=level,
        payload={"agent": agent, "stage": stage, "kind": kind},
    )


def start(task_id: int, agent: str, *, kind: str = "general") -> int:
    return mark(task_id, agent, "claimed", kind=kind)


def done(task_id: int, agent: str, *, kind: str = "general") -> int:
    return mark(task_id, agent, "done", kind=kind)


def fail(task_id: int, agent: str, *, kind: str = "general", note: str = "") -> int:
    return mark(task_id, agent, "failed", kind=kind, note=note, level="error")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes.activity", description="에이전트 가동 계측")
    p.add_argument("stage", choices=["start", "done", "fail"])
    p.add_argument("task_id", type=int)
    p.add_argument("agent")
    p.add_argument("--kind", default="general")
    p.add_argument("--note", default="")
    a = p.parse_args(argv)
    if a.agent not in KNOWN_AGENTS:
        print(f"⚠️  미등록 에이전트 '{a.agent}' — 대시보드 레인과 안 맞을 수 있음", file=sys.stderr)
    fn = {"start": start, "done": done}.get(a.stage)
    if fn:
        eid = fn(a.task_id, a.agent, kind=a.kind)
    else:
        eid = fail(a.task_id, a.agent, kind=a.kind, note=a.note)
    print(f"event #{eid} 기록: {a.agent} {a.stage} #{a.task_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
