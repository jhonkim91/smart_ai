#!/bin/bash
# HERMES 대시보드 — 더블클릭 설치+기동 런처 (macOS)
# 이 창을 닫거나 Ctrl-C 하면 대시보드가 종료됩니다.
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  HERMES 대시보드 설치/기동"
echo "  $(pwd)"
echo "============================================"

# 1) 가상환경 준비
if [ ! -d ".venv" ]; then
  echo "▶ .venv 생성 중..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) 의존성 설치 (대시보드: fastapi/uvicorn/rich)
echo "▶ 의존성 확인/설치 중... (최초 1회만 시간이 걸립니다)"
python -m pip install -q --upgrade pip >/dev/null 2>&1 || true
python -m pip install -q -r requirements.txt

# 3) 기동 후 브라우저 자동 오픈
PORT="${DASHBOARD_PORT:-8765}"
( sleep 3; open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 ) &

echo ""
echo "✅ 대시보드 시작: http://127.0.0.1:${PORT}"
echo "   (종료하려면 이 창에서 Ctrl-C 또는 창 닫기)"
echo ""
exec python -m dashboard.server
