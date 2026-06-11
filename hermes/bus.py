"""SQLite 작업 큐 (버스).

Discord 봇과 Hermes(Claude Code 세션)가 이 큐를 통해 통신한다.

상태 흐름:
    queued    : 바로 실행 가능
    pending   : 사람 승인 대기 (Discord 카드 게시 대상)
    approved  : 승인됨 -> Hermes가 집어가서 실행
    rejected  : 거부됨 -> 실행 금지
    running   : 실행 중
    done      : 완료
    failed    : 실패

CLI 사용 (Hermes/Claude Code가 Bash로 호출):
    python -m hermes.bus init
    python -m hermes.bus add "제목" [--body "내용"] [--kind code] [--approve]
    python -m hermes.bus list [--status pending]
    python -m hermes.bus get 3
    python -m hermes.bus set-status 3 running
    python -m hermes.bus result 3 "결과 요약"
    python -m hermes.bus wait 3 --timeout 600   # 승인/거부될 때까지 폴링
"""
import argparse
import json
import sqlite3
import sys
import time
from contextlib import contextmanager

from hermes.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    body            TEXT DEFAULT '',
    kind            TEXT DEFAULT 'general',
    status          TEXT DEFAULT 'queued',
    needs_approval  INTEGER DEFAULT 0,
    posted          INTEGER DEFAULT 0,          -- 승인 카드가 Discord에 게시됐는지
    result          TEXT,
    created_at      TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT
);
CREATE TABLE IF NOT EXISTS vault_index (
    path   TEXT PRIMARY KEY,
    mtime  REAL NOT NULL
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def add_task(title: str, body: str = "", kind: str = "general",
             needs_approval: bool = False) -> int:
    init_db()
    status = "pending" if needs_approval else "queued"
    with conn() as c:
        cur = c.execute(
            "INSERT INTO tasks (title, body, kind, status, needs_approval) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, body, kind, status, int(needs_approval)),
        )
        return cur.lastrowid


def get_task(task_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(status: str | None = None, limit: int = 20) -> list[dict]:
    q = "SELECT * FROM tasks"
    args: tuple = ()
    if status:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY id DESC LIMIT ?"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args + (limit,)).fetchall()]


def set_status(task_id: int, status: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE tasks SET status = ?, updated_at = datetime('now','localtime') "
            "WHERE id = ?",
            (status, task_id),
        )


def set_result(task_id: int, result: str, status: str = "done") -> None:
    with conn() as c:
        c.execute(
            "UPDATE tasks SET result = ?, status = ?, "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (result, status, task_id),
        )


def unposted_approvals() -> list[dict]:
    """Discord 봇이 폴링: 승인 필요 + 아직 카드 미게시."""
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE needs_approval = 1 "
            "AND status = 'pending' AND posted = 0 ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_posted(task_id: int) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET posted = 1 WHERE id = ?", (task_id,))


def wait_for_decision(task_id: int, timeout: int = 600, interval: float = 3.0) -> str:
    """승인/거부가 날 때까지 블로킹 폴링. 최종 status 반환."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = get_task(task_id)
        if t is None:
            return "missing"
        if t["status"] != "pending":
            return t["status"]
        time.sleep(interval)
    return "timeout"


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes.bus", description="작업 큐 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--body", default="")
    a.add_argument("--kind", default="general")
    a.add_argument("--approve", action="store_true",
                   help="사람 승인 필요 작업으로 등록 (Discord 카드 게시)")

    ls = sub.add_parser("list")
    ls.add_argument("--status", default=None)
    ls.add_argument("--limit", type=int, default=20)

    g = sub.add_parser("get")
    g.add_argument("id", type=int)

    s = sub.add_parser("set-status")
    s.add_argument("id", type=int)
    s.add_argument("status")

    r = sub.add_parser("result")
    r.add_argument("id", type=int)
    r.add_argument("text")

    w = sub.add_parser("wait")
    w.add_argument("id", type=int)
    w.add_argument("--timeout", type=int, default=600)

    args = p.parse_args(argv)

    if args.cmd == "init":
        init_db()
        print(f"ok: {DB_PATH}")
    elif args.cmd == "add":
        tid = add_task(args.title, args.body, args.kind, args.approve)
        print(tid)
    elif args.cmd == "list":
        _print(list_tasks(args.status, args.limit))
    elif args.cmd == "get":
        _print(get_task(args.id))
    elif args.cmd == "set-status":
        set_status(args.id, args.status)
        print("ok")
    elif args.cmd == "result":
        set_result(args.id, args.text)
        print("ok")
    elif args.cmd == "wait":
        print(wait_for_decision(args.id, args.timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
