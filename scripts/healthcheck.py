"""구성요소 헬스체크. 설치 직후와 문제 발생 시 첫 번째로 실행하는 스크립트.

사용:
    python scripts/healthcheck.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from hermes.config import (  # noqa: E402
    CHROMA_PATH,
    DB_PATH,
    DISCORD_BOT_TOKEN,
    DISCORD_WEBHOOK_URL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    VAULT_PATH,
)

OK, BAD, WARN = "✅", "❌", "⚠️ "


def check(label: str, fn) -> bool:
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, str(e)
    print(f"{OK if ok else BAD} {label}: {detail}")
    return ok


def ollama_up():
    r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
    r.raise_for_status()
    names = [m["name"] for m in r.json().get("models", [])]
    missing = [m for m in (OLLAMA_MODEL, OLLAMA_EMBED_MODEL)
               if not any(n.startswith(m.split(":")[0]) for n in names)]
    if missing:
        return False, f"서버 OK, 모델 누락 {missing} -> ollama pull로 설치"
    return True, f"서버 OK, 모델 {len(names)}개 (필수 모델 설치됨)"


def sqlite_up():
    from hermes import bus
    bus.init_db()
    with sqlite3.connect(DB_PATH) as c:
        n = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    return True, f"{DB_PATH} (tasks {n}건)"


def chroma_up():
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    cols = [c.name for c in client.list_collections()]
    return True, f"{CHROMA_PATH} (collections: {cols or '없음 — index_vault 실행 필요'})"


def vault_up():
    if not VAULT_PATH.exists():
        return False, f"{VAULT_PATH} 없음 (.env VAULT_PATH 확인)"
    n = len(list(VAULT_PATH.rglob("*.md")))
    return True, f"{VAULT_PATH} (.md {n}개)"


def discord_token():
    if not DISCORD_BOT_TOKEN:
        return False, ".env DISCORD_BOT_TOKEN 비어 있음"
    return True, f"토큰 설정됨 (길이 {len(DISCORD_BOT_TOKEN)})"


def discord_webhook():
    if not DISCORD_WEBHOOK_URL:
        return False, ".env DISCORD_WEBHOOK_URL 비어 있음 (notify/n8n 알림용)"
    return True, "웹후크 URL 설정됨"


def n8n_up():
    r = requests.get("http://localhost:5678/healthz", timeout=3)
    return r.ok, f"http://localhost:5678 ({r.status_code})"


def main() -> int:
    print("── agent-hub healthcheck ─────────────────────────")
    results = [
        check("Ollama", ollama_up),
        check("SQLite 작업 큐", sqlite_up),
        check("Chroma 벡터 DB", chroma_up),
        check("Obsidian vault", vault_up),
        check("Discord 봇 토큰", discord_token),
        check("Discord 웹후크", discord_webhook),
    ]
    # n8n은 현 단계 보류/선택 구성요소라 실패해도 경고만
    try:
        ok, detail = n8n_up()
        print(f"{OK if ok else WARN}n8n(선택/보류): {detail}")
    except Exception:  # noqa: BLE001
        print(f"{WARN}n8n(선택/보류): 미기동 — 기본 스케줄러는 launchd")

    failed = results.count(False)
    print("──────────────────────────────────────────────────")
    print("모든 필수 구성요소 정상" if failed == 0 else f"실패 {failed}건 — 위 항목 확인")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
