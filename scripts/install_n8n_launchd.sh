#!/usr/bin/env bash
# n8n을 launchd 상주 서비스로 등록(로그인 시 기동, 죽으면 재시작).
# 워크플로의 6시간 스케줄이 동작하려면 n8n이 떠 있어야 한다.
# 사용: bash scripts/install_n8n_launchd.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

N8N_BIN="$(command -v n8n || true)"
if [ -z "$N8N_BIN" ]; then
    echo "✗ n8n 미설치 — 먼저 bash scripts/install_n8n.sh 실행" >&2
    exit 1
fi
NODE_BIN_DIR="$(dirname "$(command -v node)")"

PLIST_TEMPLATE="$SCRIPT_DIR/launchd/com.agent-hub.n8n.plist"
LABEL="com.agent-hub.n8n"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/data/logs"

sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__N8N_BIN__|$N8N_BIN|g" \
    -e "s|__NODE_BIN_DIR__|$NODE_BIN_DIR|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

echo "▶ plutil -lint ..."
plutil -lint "$PLIST_DEST"

DOMAIN="gui/$(id -u)"
if launchctl list 2>/dev/null | grep -qF "$LABEL"; then
    echo "▶ 기존 서비스 bootout 후 재등록…"
    launchctl bootout "$DOMAIN" "$PLIST_DEST" 2>/dev/null || true
fi
launchctl bootstrap "$DOMAIN" "$PLIST_DEST"

echo ""
echo "✓ n8n 상주 등록 완료: $PLIST_DEST"
echo "✓ UI: http://localhost:5678 (워크플로 'Active' 토글 필요)"
echo "✓ 로그: $PROJECT_DIR/data/logs/n8n.log"
echo ""
echo "제거: launchctl bootout $DOMAIN/$LABEL"
