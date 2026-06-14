#!/usr/bin/env bash
# n8n(자동 개선 루프 트리거) 설치/등록 — Docker 없이 npm n8n 사용.
# 1) n8n 미설치면 전역 설치  2) 워크플로 import  3) launchd로 상주 등록(선택)
# 사용: bash scripts/install_n8n.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
N8N_HOME="$PROJECT_DIR/data/n8n"        # n8n DB/설정을 프로젝트 안에 격리
WF_SRC="$PROJECT_DIR/pipelines/shorts/n8n_workflow.json"
WF_TMP="$PROJECT_DIR/data/n8n/workflow.import.json"

mkdir -p "$N8N_HOME"
export N8N_USER_FOLDER="$N8N_HOME"

# 1) 설치 확인
if ! command -v n8n >/dev/null 2>&1; then
    echo "▶ n8n 전역 설치(npm)…"
    npm install -g n8n
fi
echo "✓ n8n: $(command -v n8n)"

# 2) __PROJECT_DIR__ 치환 후 워크플로 import
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$WF_SRC" > "$WF_TMP"
echo "▶ 워크플로 import…"
n8n import:workflow --input="$WF_TMP"

echo ""
echo "✓ 워크플로 import 완료 (shorts-autotune-loop)"
echo ""
echo "다음 단계:"
echo "  • n8n 수동 기동:    N8N_USER_FOLDER=$N8N_HOME n8n start"
echo "    → http://localhost:5678 에서 워크플로 'Active' 토글 후 6시간마다 자동 튜닝"
echo "  • 상주(로그인 시 자동) 등록: bash scripts/install_n8n_launchd.sh"
echo "  • n8n 없이 즉시 1회 트리거:  ./.venv/bin/python -m pipelines.shorts.tune_cycle --iters 40"
