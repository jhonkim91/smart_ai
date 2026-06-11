#!/usr/bin/env bash
# agent-hub 부트스트랩 (macOS, 멱등 — 여러 번 실행해도 안전)
# 사용: bash scripts/bootstrap.sh
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1;36m▸ %s\033[0m\n' "$1"; }

step "1/6 Homebrew 확인"
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew가 없습니다. https://brew.sh 에서 먼저 설치하세요."
  exit 1
fi
echo "ok: $(brew --version | head -1)"

step "2/6 Ollama 설치 및 기동"
if ! command -v ollama >/dev/null 2>&1; then
  brew install ollama
fi
brew services start ollama >/dev/null 2>&1 || true
sleep 2
echo "ok: $(ollama --version 2>/dev/null || echo 'ollama 설치됨')"

step "3/6 로컬 모델 다운로드 (최초 1회, 수 GB — 시간 소요)"
ollama pull qwen2.5:7b          # 범용 워커 (Apache-2.0, 한국어 무난)
ollama pull nomic-embed-text    # 임베딩 (Apache-2.0)

step "4/6 Python 가상환경 + 의존성"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "ok: $(./.venv/bin/python --version)"

step "5/6 .env 및 DB 초기화"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  .env 생성됨 — Discord 토큰/채널 ID를 채워 넣으세요 (README 참고)"
else
  echo "ok: .env 존재"
fi
./.venv/bin/python -m hermes.bus init

step "6/6 헬스체크"
./.venv/bin/python scripts/healthcheck.py || true

cat << 'NEXT'

다음 단계
  1) .env에 Discord 값 입력 (README의 'Discord 봇 설정' 절 참고)
  2) 봇 실행:        ./.venv/bin/python -m channel.discord_bot
  3) vault 인덱싱:   ./.venv/bin/python -m memory.index_vault
  4) (선택) n8n:     docker compose up -d   ->  http://localhost:5678
  5) Claude Code로 이 폴더를 열면 CLAUDE.md가 자동 로드됨
NEXT
