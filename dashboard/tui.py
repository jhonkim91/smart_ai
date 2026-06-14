"""터미널 TUI — 에이전트 병렬 가동을 터미널에서 본다.

    python -m dashboard.tui            # rich.live 자동 갱신(2초)
    python -m dashboard.tui --once     # 1회 스냅샷 출력 (watch -n2 와 함께 쓰기 좋음)
    python -m dashboard.tui --interval 1

queries.py를 그대로 재사용한다(읽기 전용). rich가 없으면 stdlib ANSI 폴백으로 동작한다.
"""
from __future__ import annotations

import argparse
import time

from dashboard import queries


# --- 공용: 한 프레임의 텍스트 구성 (폴백/테스트 공용) -----------------------

def _plain_frame(snap: dict) -> str:
    ag = snap["agents"]
    c = snap["board"]["counts"]
    lines = [
        f"HERMES · 에이전트 병렬 가동            {snap['ts']}",
        "-" * 60,
    ]
    for name in ag["order"]:
        lane = ag["lanes"][name]
        state = lane.get("state", "active" if lane["active"] else "idle")
        mark = {"active": "●", "recent": "◐", "idle": "○"}.get(state, "○")
        if lane["running"]:
            job = lane["running"][0]
            desc = f'{job["kind"]:<8} #{job["id"]} {job["title"][:30]}'
        elif state == "active" and lane.get("last"):
            desc = f'{lane["last"].get("kind","")} #{lane["last"]["task_id"]} 처리중'
        elif state == "recent" and lane.get("last"):
            desc = f'방금 {lane["last"].get("stage")} #{lane["last"]["task_id"]}'
        else:
            desc = "idle"
        q = f'(큐 {lane["queued"]})' if lane["queued"] else ""
        lines.append(f"{mark} {name:<8} {desc} {q}")
    lines.append("-" * 60)
    lines.append(
        f'큐 queued {c.get("queued",0)}  running {c.get("running",0)}  '
        f'done {c.get("done",0)}  대기승인 {c.get("pending",0)}  '
        f'· 병렬 {ag["parallel"]}  최근 {ag.get("recent",0)}'
    )
    return "\n".join(lines)


# --- rich 렌더 ------------------------------------------------------------

def _rich_table(snap: dict):
    from rich.table import Table
    from rich.text import Text

    ag = snap["agents"]
    t = Table(title=f"HERMES · 에이전트 병렬 가동   {snap['ts']}",
              expand=True, title_style="bold cyan")
    t.add_column("●", width=2)
    t.add_column("에이전트", style="bold", width=9)
    t.add_column("작업", overflow="ellipsis")
    t.add_column("큐", justify="right", width=4)
    for name in ag["order"]:
        lane = ag["lanes"][name]
        state = lane.get("state", "active" if lane["active"] else "idle")
        if state == "active":
            mark = Text("●", style="green")
            if lane["running"]:
                job = lane["running"][0]
                work = Text(f'{job["kind"]} #{job["id"]} {job["title"][:34]}', style="green")
            else:
                last = lane.get("last") or {}
                work = Text(f'{last.get("kind","")} #{last.get("task_id")} 처리중', style="green")
            agent = Text(name, style="green bold")
        elif state == "recent":
            last = lane.get("last") or {}
            mark = Text("◐", style="yellow")
            work = Text(f'방금 {last.get("stage")} #{last.get("task_id")}', style="yellow")
            agent = Text(name, style="yellow bold")
        else:
            mark = Text("○", style="grey50")
            work = Text("idle", style="grey50")
            agent = Text(name, style="grey50")
        q = str(lane["queued"]) if lane["queued"] else ""
        t.add_row(mark, agent, work, q)
    return t


def _rich_footer(snap: dict):
    from rich.text import Text
    c = snap["board"]["counts"]
    ag = snap["agents"]
    return Text.assemble(
        ("queued ", "default"), (str(c.get("queued", 0)), "yellow bold"),
        ("   running ", "default"), (str(c.get("running", 0)), "green bold"),
        ("   done ", "default"), (str(c.get("done", 0)), "cyan bold"),
        ("   대기승인 ", "default"), (str(c.get("pending", 0)), "magenta bold"),
        ("   · 병렬 ", "default"), (str(ag["parallel"]), "green bold"),
        ("   (q: ctrl-c 종료)", "grey50"),
    )


def _run_rich(interval: float) -> None:
    from rich.console import Console, Group
    from rich.live import Live

    console = Console()
    with Live(console=console, refresh_per_second=4, screen=False) as live:
        while True:
            snap = queries.snapshot()
            live.update(Group(_rich_table(snap), _rich_footer(snap)))
            time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="agent-hub 터미널 TUI")
    ap.add_argument("--once", action="store_true", help="1회 출력 후 종료")
    ap.add_argument("--interval", type=float, default=2.0, help="갱신 주기(초)")
    ap.add_argument("--plain", action="store_true", help="rich 없이 ANSI 텍스트")
    args = ap.parse_args()

    if args.once:
        print(_plain_frame(queries.snapshot()))
        return

    if not args.plain:
        try:
            _run_rich(args.interval)
            return
        except ImportError:
            print("(rich 미설치 → 텍스트 폴백. `pip install rich` 권장)\n")
        except KeyboardInterrupt:
            return

    # stdlib 폴백: 화면 클리어 + 재출력 루프
    try:
        while True:
            print("\033[2J\033[H", end="")
            print(_plain_frame(queries.snapshot()))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
