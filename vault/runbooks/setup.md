# 런북: 초기 설치

```bash
cd agent-hub
bash scripts/bootstrap.sh        # Ollama 설치 + 모델 + venv + DB
# .env 채우기 (README의 Discord 봇 설정 절)
source .venv/bin/activate
python scripts/healthcheck.py    # 필수 항목 ✅ 확인 (n8n은 선택 경고 가능)
python -m channel.discord_bot    # 봇 기동 (별도 터미널 유지)
python -m hermes.worker --loop   # 선택: draft/summary/title 등 Ollama 큐 자동 처리
python -m memory.index_vault     # vault 인덱싱
```

트렌드 수집을 매일 09:00 자동 실행하려면 `.env`의 `TREND_RSS_FEEDS`를 채운 뒤:

```bash
python -m pipelines.shorts.trends --dry-run
bash scripts/install_launchd.sh
```

## 자주 겪는 문제

- `ollama: connection refused` → `/Applications/Ollama.app` 실행 또는 `ollama serve`
- 슬래시 커맨드가 안 보임 → 봇 재초대(applications.commands 스코프 포함) 또는 1~2분 대기
- 승인 카드가 안 올라옴 → `.env`의 `DISCORD_APPROVAL_CHANNEL_ID` 확인 + 봇의 채널 권한 확인
- Discord webhook이 없을 때 → `channel.notify`가 `data/logs/notifications.log`에 local log로 남김
