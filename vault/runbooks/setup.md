# 런북: 초기 설치

```bash
cd agent-hub
bash scripts/bootstrap.sh        # Ollama 설치 + 모델 + venv + DB
# .env 채우기 (README의 Discord 봇 설정 절)
source .venv/bin/activate
python scripts/healthcheck.py    # 전부 ✅ 확인
python -m channel.discord_bot    # 봇 기동 (별도 터미널 유지)
python -m memory.index_vault     # vault 인덱싱
docker compose up -d             # (선택) n8n
```

## 자주 겪는 문제

- `ollama: connection refused` → `brew services start ollama`
- 슬래시 커맨드가 안 보임 → 봇 재초대(applications.commands 스코프 포함) 또는 1~2분 대기
- 승인 카드가 안 올라옴 → .env의 DISCORD_APPROVAL_CHANNEL_ID 확인 + 봇의 채널 권한 확인
