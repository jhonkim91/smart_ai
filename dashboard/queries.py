"""대시보드 데이터 레이어 — 읽기 전용(read-only).

웹 서버(server.py)와 터미널 TUI(tui.py)가 공유하는 단일 소스.
DB는 SQLite `mode=ro` URI로 열어 쓰기를 물리적으로 차단한다(읽기 전용 불변식).
판단/라우팅 결정은 하지 않으며, 기존 hermes.router 매핑을 그대로 읽어 레인만 배정한다.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from hermes import config, router

# 이 시간(초) 안에 가동 이벤트가 있으면 레인을 "최근 가동(recent)"으로 점등
RECENT_WINDOW_SEC = 120

# 칸반 컬럼 순서 (DB status 값 기준)
BOARD_COLUMNS = ["pending", "queued", "running", "done"]

# 에이전트 레인 순서: Ollama 워커 + Claude 서브에이전트 8종
AGENT_LANES = [
    "ollama",
    "forge", "atlas", "probe", "warden",
    "oracle", "scribe", "augur", "herald",
]

# 쇼츠 파이프라인 단계 (n8n식 플로우)
PIPELINE_STAGES = [
    {"key": "trends", "label": "트렌드 수집"},
    {"key": "draft", "label": "스크립트 초안"},
    {"key": "refine", "label": "다듬기"},
    {"key": "tts", "label": "TTS"},
    {"key": "render", "label": "렌더"},
    {"key": "approve", "label": "승인(HITL)"},
    {"key": "upload", "label": "업로드"},
    {"key": "report", "label": "보고"},
]


@contextmanager
def _ro_conn():
    """읽기 전용 연결. DB가 없으면 빈 결과를 위해 None을 양보한다."""
    db = Path(config.DB_PATH)
    if not db.exists():
        yield None
        return
    uri = f"file:{db}?mode=ro"
    c = sqlite3.connect(uri, uri=True, timeout=5.0)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _ro_conn() as c:
        if c is None:
            return []
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        except sqlite3.OperationalError:
            return []


# --- 작업 / 칸반 -----------------------------------------------------------

def tasks(limit: int = 200) -> list[dict]:
    return _rows(
        "SELECT id, title, body, kind, status, needs_approval, result, "
        "created_at, updated_at FROM tasks ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def status_counts() -> dict[str, int]:
    out = {c: 0 for c in BOARD_COLUMNS}
    for r in _rows("SELECT status, COUNT(*) n FROM tasks GROUP BY status"):
        out[r["status"]] = r["n"]
    return out


def board(limit: int = 200) -> dict:
    """칸반 보드 모델: 컬럼별 작업 카드."""
    cols: dict[str, list[dict]] = {c: [] for c in BOARD_COLUMNS}
    extra: list[dict] = []
    for t in tasks(limit):
        card = {
            "id": t["id"],
            "title": t["title"],
            "kind": t["kind"],
            "needs_approval": bool(t["needs_approval"]),
            "updated_at": t["updated_at"] or t["created_at"],
        }
        if t["status"] in cols:
            cols[t["status"]].append(card)
        else:
            extra.append({**card, "status": t["status"]})
    return {"columns": BOARD_COLUMNS, "cards": cols, "counts": status_counts(), "other": extra}


# --- 에이전트 병렬 가동 ----------------------------------------------------

def _lane_for(task: dict) -> str:
    """router 매핑으로 작업이 배정될 레인 이름을 돌려준다(판단 아님, 조회)."""
    r = router.route(task.get("kind", "general"), task.get("title", ""))
    return r["agent"] if r["target"] == "claude" else "ollama"


def _age_sec(ts: str | None) -> float | None:
    if not ts:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return (datetime.now() - datetime.strptime(ts, fmt)).total_seconds()
        except (ValueError, TypeError):
            continue
    return None


def _recent_activity(window_sec: int = RECENT_WINDOW_SEC, scan: int = 300) -> dict[str, dict]:
    """run_events에서 에이전트별 가장 최근 가동을 뽑는다(payload.agent 기준)."""
    latest: dict[str, dict] = {}
    rows = _rows(
        "SELECT task_id, level, message, payload, created_at "
        "FROM run_events ORDER BY id DESC LIMIT ?", (scan,),
    )
    for r in rows:
        try:
            p = json.loads(r["payload"]) if r["payload"] else {}
        except (ValueError, TypeError):
            p = {}
        agent = p.get("agent")
        if not agent or agent in latest:
            continue  # 이미 더 최근 이벤트를 잡음
        age = _age_sec(r["created_at"])
        latest[agent] = {
            "task_id": r["task_id"], "stage": p.get("stage"), "kind": p.get("kind"),
            "at": r["created_at"], "age_sec": age,
            "fresh": age is not None and age <= window_sec,
        }
    return latest


def agents() -> dict:
    """에이전트 레인 모델.

    state 우선순위: active(현재 running 작업) > recent(window 내 가동 이벤트) > idle.
    running은 tasks.status 기준, recent는 run_events.payload.agent 기준(계측 Phase 4).
    """
    lanes = {
        name: {"agent": name, "running": [], "queued": 0,
               "active": False, "state": "idle", "last": None}
        for name in AGENT_LANES
    }
    for t in tasks(500):
        lane = _lane_for(t)
        if lane not in lanes:
            continue
        if t["status"] == "running":
            lanes[lane]["running"].append(
                {"id": t["id"], "title": t["title"], "kind": t["kind"],
                 "since": t["updated_at"] or t["created_at"]}
            )
            lanes[lane]["active"] = True
        elif t["status"] == "queued":
            lanes[lane]["queued"] += 1

    recent = _recent_activity()
    for name, lane in lanes.items():
        info = recent.get(name)
        if info:
            lane["last"] = info
        if lane["active"]:
            lane["state"] = "active"
        elif info and info["fresh"] and info["stage"] == "claimed":
            lane["state"] = "active"   # 계측상 잡았지만 status 갱신 전 — 가동으로 본다
        elif info and info["fresh"]:
            lane["state"] = "recent"
        else:
            lane["state"] = "idle"
        lane["active"] = lane["state"] == "active"

    return {
        "order": AGENT_LANES,
        "lanes": lanes,
        "parallel": sum(1 for l in lanes.values() if l["state"] == "active"),
        "recent": sum(1 for l in lanes.values() if l["state"] == "recent"),
        "running_total": sum(len(l["running"]) for l in lanes.values()),
    }


# --- 쇼츠 파이프라인 플로우 -------------------------------------------------

def _episode_stage_flags(ep: Path) -> dict[str, bool]:
    names = {p.name for p in ep.iterdir()} if ep.is_dir() else set()
    has_script = "script.json" in names or "story.json" in names
    has_tts = "voice.m4a" in names or "tts_manifest.json" in names
    has_render = "final.mp4" in names
    return {"script": has_script, "tts": has_tts, "render": has_render}


def pipeline() -> dict:
    """파이프라인 단계별 상태(done/active/idle)를 집계해 노드 플로우로 반환."""
    counts = status_counts()
    draft_q = sum(1 for t in tasks(500) if t["kind"] == "draft" and t["status"] == "queued")
    draft_done = sum(1 for t in tasks(500) if t["kind"] == "draft" and t["status"] == "done")

    shorts_dir = Path(config.SHORTS_DIR)
    eps = [d for d in shorts_dir.iterdir() if d.is_dir()] if shorts_dir.exists() else []
    n_script = n_tts = n_render = 0
    latest = None
    for ep in eps:
        f = _episode_stage_flags(ep)
        n_script += f["script"]
        n_tts += f["tts"]
        n_render += f["render"]
    if eps:
        latest = max(eps, key=lambda d: d.stat().st_mtime)

    uploaded = len(_rows("SELECT 1 FROM publish_history WHERE video_id IS NOT NULL"))
    pending = counts.get("pending", 0)

    def st(done: int, active: int) -> str:
        if active:
            return "active"
        return "done" if done else "idle"

    stage_state = {
        "trends": st(draft_q + draft_done, 0),
        "draft": st(draft_done, draft_q),
        "refine": st(n_script, 0),
        "tts": st(n_tts, 0),
        "render": st(n_render, 0),
        "approve": "active" if pending else ("done" if uploaded else "idle"),
        "upload": st(uploaded, 0),
        "report": st(uploaded, 0),
    }
    nodes = [
        {**s, "state": stage_state.get(s["key"], "idle")} for s in PIPELINE_STAGES
    ]
    return {
        "nodes": nodes,
        "metrics": {
            "episodes": len(eps),
            "rendered": n_render,
            "drafts_queued": draft_q,
            "uploaded": uploaded,
            "latest": latest.name if latest else None,
        },
    }


# --- 이벤트 타임라인 -------------------------------------------------------

def events(limit: int = 50) -> list[dict]:
    out = _rows(
        "SELECT id, task_id, level, message, payload, created_at "
        "FROM run_events ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    for e in out:
        try:
            p = json.loads(e.pop("payload")) if e.get("payload") else {}
        except (ValueError, TypeError):
            p = {}
        e["agent"] = p.get("agent")
        e["stage"] = p.get("stage")
    return out


# --- 통합 스냅샷 (SSE/TUI 공용) -------------------------------------------

def snapshot() -> dict:
    import time
    return {
        "ts": time.strftime("%H:%M:%S"),
        "board": board(),
        "agents": agents(),
        "pipeline": pipeline(),
        "events": events(20),
    }


def fingerprint() -> str:
    """변경 감지용 경량 지문. tasks의 최신 updated_at + 행수 기반."""
    row = _rows(
        "SELECT COUNT(*) n, COALESCE(MAX(updated_at), '') u, "
        "COALESCE(MAX(id), 0) m FROM tasks"
    )
    if not row:
        return "0"
    r = row[0]
    ev = _rows("SELECT COALESCE(MAX(id),0) e FROM run_events")
    e = ev[0]["e"] if ev else 0
    return f"{r['n']}:{r['u']}:{r['m']}:{e}"
