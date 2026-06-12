#!/usr/bin/env bash
# 멱등 launchd 서비스 설치 — 이미 로드돼 있으면 bootout 후 재등록한다.
# 사용: bash scripts/install_launchd.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PLIST_TEMPLATE="$SCRIPT_DIR/launchd/com.agent-hub.trends.plist"
PLIST_NAME="com.agent-hub.trends.plist"
LABEL="com.agent-hub.trends"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCHAGENTS_DIR/$PLIST_NAME"
LOG_DIR="$PROJECT_DIR/data/logs"

# 필요 디렉터리 생성
mkdir -p "$LAUNCHAGENTS_DIR" "$LOG_DIR"

# PROJECT_DIR 치환 후 LaunchAgents에 저장
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PLIST_TEMPLATE" > "$PLIST_DEST"

# 문법 검증
echo "▶ plutil -lint ..."
plutil -lint "$PLIST_DEST"

# 이미 로드된 서비스는 bootout 후 재등록 (멱등 보장)
DOMAIN="gui/$(id -u)"
if launchctl list 2>/dev/null | grep -qF "$LABEL"; then
    echo "▶ 기존 서비스 발견 — bootout 후 재등록..."
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
fi

launchctl bootstrap "$DOMAIN" "$PLIST_DEST"

echo ""
echo "✓ 설치 완료: $PLIST_DEST"
echo "✓ 스케줄: 매일 09:00 KST (시스템 시간대 KST 전제)"
echo "✓ 로그:   $LOG_DIR/trends.log"
echo ""
echo "수동 1회 실행:"
echo "  launchctl kickstart $DOMAIN/$LABEL"
echo ""
echo "서비스 제거:"
echo "  launchctl bootout $DOMAIN/$LABEL"
