"""FastAPI 웹 대시보드 서버 (읽기 전용).

    python -m dashboard.server                 # 127.0.0.1:8765
    DASHBOARD_HOST=0.0.0.0 python -m dashboard.server   # LAN 노출(인증 토큰 필수)

엔드포인트
    GET /                대시보드 HTML (반응형, 모바일 폭 대응)
    GET /api/snapshot    통합 스냅샷 (board+agents+pipeline+events)
    GET /api/board       칸반
    GET /api/agents      에이전트 병렬 가동
    GET /api/pipeline    쇼츠 파이프라인 플로우
    GET /api/events      run_events 타임라인
    GET /stream          SSE: 변경 감지 시 snapshot push (폴링 폴백 가능)

보안: 기본 127.0.0.1 단독·무인증(로컬 전제). 외부/모바일 노출 시 DASHBOARD_TOKEN을
설정하면 모든 요청에 ?token= 또는 X-Dashboard-Token 헤더를 강제한다(읽기 전용 유지).
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pathlib import Path

from dashboard import queries

STATIC = Path(__file__).resolve().parent / "static"
TOKEN = os.getenv("DASHBOARD_TOKEN", "")

app = FastAPI(title="agent-hub dashboard", docs_url=None, redoc_url=None)


def _check_token(request: Request) -> None:
    """토큰이 설정된 경우에만 검사(로컬 무인증 기본값 유지)."""
    if not TOKEN:
        return
    supplied = request.query_params.get("token") or request.headers.get("x-dashboard-token", "")
    if supplied != TOKEN:
        raise HTTPException(status_code=401, detail="invalid dashboard token")


@app.get("/")
def index(request: Request):
    _check_token(request)
    return FileResponse(STATIC / "index.html")


@app.get("/api/snapshot")
def api_snapshot(request: Request):
    _check_token(request)
    return JSONResponse(queries.snapshot())


@app.get("/api/board")
def api_board(request: Request):
    _check_token(request)
    return JSONResponse(queries.board())


@app.get("/api/agents")
def api_agents(request: Request):
    _check_token(request)
    return JSONResponse(queries.agents())


@app.get("/api/pipeline")
def api_pipeline(request: Request):
    _check_token(request)
    return JSONResponse(queries.pipeline())


@app.get("/api/events")
def api_events(request: Request):
    _check_token(request)
    return JSONResponse(queries.events(50))


@app.get("/stream")
async def stream(request: Request):
    _check_token(request)

    async def gen():
        last = None
        # 최초 1회 즉시 전송
        snap = queries.snapshot()
        yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
        last = queries.fingerprint()
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(2.0)
            fp = queries.fingerprint()
            if fp != last:
                last = fp
                snap = queries.snapshot()
                yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
            else:
                # keep-alive 코멘트 (프록시 타임아웃 방지)
                yield ": ping\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:
    import uvicorn

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8765"))
    if host != "127.0.0.1" and not TOKEN:
        print("⚠️  외부 바인딩인데 DASHBOARD_TOKEN이 없습니다. 인증 없이 노출됩니다.")
    print(f"▶ agent-hub dashboard: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
