#!/usr/bin/env bash
# agent-hub 웹 대시보드 기동 헬퍼.
#   bash scripts/run_dashboard.sh              # 127.0.0.1:8765
#   DASHBOARD_HOST=0.0.0.0 DASHBOARD_TOKEN=secret bash scripts/run_dashboard.sh  # LAN/모바일(인증)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && source .venv/bin/activate
exec python -m dashboard.server
