#!/bin/bash
# HERMES Ollama 워커 — 큐의 draft/summary 등을 자동 처리하며 대시보드 ollama 레인을 점등시킨다.
# 전제: Ollama가 실행 중이어야 함 (ollama serve). 이 창을 닫으면 워커가 멈춥니다.
set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo "▶ Ollama 연결 확인..."
if ! curl -s "${OLLAMA_HOST:-http://127.0.0.1:11434}/api/tags" >/dev/null 2>&1; then
  echo "⚠️  Ollama에 연결할 수 없습니다. 다른 터미널에서 'ollama serve'를 먼저 실행하세요."
  echo "    (대시보드는 워커 없이도 동작합니다 — 이 창은 닫아도 됩니다)"
fi

echo "▶ 워커 루프 시작 (큐를 5초마다 폴링). 종료: Ctrl-C"
exec python -m hermes.worker --loop --interval 5
