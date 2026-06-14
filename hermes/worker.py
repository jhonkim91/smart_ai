"""Hermes queued-task worker.

Discord/launchd/n8n 등이 `hermes.bus`에 넣은 cheap 작업을 자동 소비한다.
현재 자동 처리 범위는 Ollama로 안전하게 처리 가능한 kind(draft/summary/classify/title/translate)로
제한한다. 코드 작성·리뷰·배포·업로드 같은 고위험 작업은 이 worker가 가져가지 않는다.

사용:
    python -m hermes.worker --once
    python -m hermes.worker --loop --interval 5 --notify
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from hermes import bus
from hermes.ollama_worker import SYSTEM_PROMPTS, run as ollama_run
from hermes.router import OLLAMA_KINDS, route

DEFAULT_KINDS = tuple(sorted(OLLAMA_KINDS))


def _parse_kinds(raw: str) -> tuple[str, ...] | None:
    """CLI kind 필터 파싱. `all`이면 필터 없이 claim한다."""
    if raw.strip().lower() == "all":
        return None
    return tuple(k.strip() for k in raw.split(",") if k.strip())


def _task_text(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "").strip()
    body = str(task.get("body") or "").strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body


def process_task(task: dict[str, Any], *, notify_done: bool = False) -> dict[str, Any]:
    """이미 running으로 claim된 task 하나를 처리하고 result를 저장한다."""
    task_id = int(task["id"])
    kind = str(task.get("kind") or "general")
    text = _task_text(task)
    decision = route(kind, text)

    bus.log_event(
        task_id,
        "worker claimed task",
        payload={"kind": kind, "route": decision},
    )

    if decision.get("target") != "ollama" or kind not in SYSTEM_PROMPTS:
        message = (
            f"worker 자동 처리 대상이 아닙니다: kind={kind}, route={decision}. "
            "Claude/HERMES 수동 처리 큐로 남겨야 하는 작업입니다."
        )
        bus.set_result(task_id, message, status="failed")
        bus.log_event(task_id, message, level="warn")
        return {"task_id": task_id, "status": "failed", "reason": "unsupported_kind"}

    result = ollama_run(kind, text)
    bus.set_result(task_id, result, status="done")
    bus.log_event(
        task_id,
        "worker completed task",
        payload={"kind": kind, "result_chars": len(result)},
    )

    if notify_done:
        from channel.notify import send

        send(
            f"작업 #{task_id} 완료\nkind: {kind}\n결과 길이: {len(result)}자",
            title="Hermes worker",
            level="ok",
        )

    return {"task_id": task_id, "status": "done", "kind": kind, "result_chars": len(result)}


def run_once(
    *,
    kinds: tuple[str, ...] | None = DEFAULT_KINDS,
    notify_done: bool = False,
) -> dict[str, Any]:
    """queued 작업 하나를 claim/처리한다. 처리할 작업이 없으면 idle 반환."""
    task = bus.claim_next_task(kinds)
    if task is None:
        return {"status": "idle"}

    try:
        return process_task(task, notify_done=notify_done)
    except Exception as exc:  # noqa: BLE001
        task_id = int(task["id"])
        message = f"[worker] 실패: {exc}"
        bus.set_result(task_id, message, status="failed")
        bus.log_event(task_id, message, level="error")
        if notify_done:
            from channel.notify import send

            send(message, title="Hermes worker", level="error")
        return {"task_id": task_id, "status": "failed", "error": str(exc)}


def run_loop(
    *,
    interval: float = 5.0,
    kinds: tuple[str, ...] | None = DEFAULT_KINDS,
    notify_done: bool = False,
) -> None:
    """계속 polling하는 상주 worker 루프."""
    while True:
        result = run_once(kinds=kinds, notify_done=notify_done)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("status") == "idle":
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes.worker", description="queued Ollama 작업 자동 소비자")
    p.add_argument("--loop", action="store_true", help="계속 실행하며 queued 작업을 polling")
    p.add_argument("--interval", type=float, default=5.0, help="--loop idle polling 간격(초)")
    p.add_argument(
        "--kinds",
        default=",".join(DEFAULT_KINDS),
        help="처리할 kind 쉼표 목록. 기본은 Ollama 안전 kind만. all은 필터 없음",
    )
    p.add_argument("--notify", action="store_true", help="작업 완료/실패를 Discord webhook으로 보고")
    args = p.parse_args(argv)

    kinds = _parse_kinds(args.kinds)
    if args.loop:
        run_loop(interval=args.interval, kinds=kinds, notify_done=args.notify)
        return 0

    result = run_once(kinds=kinds, notify_done=args.notify)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
