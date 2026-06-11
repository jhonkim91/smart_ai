# agent-hub

Hermes(Claude Code) 오케스트레이터 + Discord HITL + Ollama 로컬 워커 + Obsidian/Chroma 메모리로
구성된 멀티 에이전트 허브. **Claude 구독을 제외한 전 구성요소 무료.**

```
Discord(명령·승인·알림) ⇄ SQLite 큐 ⇄ HERMES(Claude Code 세션)
                                        ├─ 서브에이전트 8종 (.claude/agents/)
                                        └─ Ollama 워커 (초안·요약·분류, 무료)
지식: Obsidian vault ⇄ Chroma RAG    실행기: n8n (스케줄·웹훅·업로드)
목표: ① 쇼츠 자동화  ② 주식 자동매매(결정적 실행)  ③ 임베디드 개발
```

## 요구 사항

- macOS + Homebrew, Python 3.11+, Docker Desktop(선택, n8n용), Claude Code 설치
- Discord 계정과 본인 서버(길드) 1개

## 설치 (10분 + 모델 다운로드 시간)

```bash
unzip agent-hub.zip && cd agent-hub
bash scripts/bootstrap.sh          # Ollama + 모델 + venv + DB 자동 구성
```

이후 아래 **Discord 봇 설정**으로 .env를 채우고:

```bash
source .venv/bin/activate
python scripts/healthcheck.py      # 전 항목 ✅ 확인
python -m channel.discord_bot      # 봇 기동 (터미널 하나 점유)
python -m memory.index_vault       # vault → Chroma 인덱싱
docker compose up -d               # (선택) n8n → http://localhost:5678
```

## Discord 봇 설정 (최초 1회, 5분)

1. https://discord.com/developers/applications → **New Application** → 이름 `hermes`
2. 좌측 **Bot** 탭 → **Reset Token** → 토큰 복사 → `.env`의 `DISCORD_BOT_TOKEN`
3. 좌측 **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`
   - 생성된 URL로 본인 서버에 초대
4. Discord 앱 설정 → 고급 → **개발자 모드** 켜기 → 서버 우클릭 →
   **ID 복사** → `.env`의 `DISCORD_GUILD_ID`
5. 승인용/로그용 채널을 각각 우클릭 → ID 복사 → `.env`의
   `DISCORD_APPROVAL_CHANNEL_ID`, `DISCORD_LOG_CHANNEL_ID`
6. 로그 채널 설정 → 연동 → **웹후크 만들기** → URL 복사 → `.env`의 `DISCORD_WEBHOOK_URL`

검증: 서버에서 `/ping` → "Hermes 채널 온라인" 응답,
`/task title:테스트 needs_approval:True` → 승인 카드에 버튼이 뜨면 성공.

## Claude Code 인계 (핵심)

```bash
cd agent-hub
claude        # CLAUDE.md가 자동 로드되어 이 세션이 HERMES가 된다
```

첫 세션에서 그대로 붙여넣기:

> healthcheck를 실행해 환경을 점검하고, 실패 항목이 있으면 고쳐줘.
> 그다음 `python -m hermes.bus list`로 큐를 확인하고 CLAUDE.md의
> "시작 직후 체크" 절차대로 진행해줘.

## 디렉토리 지도

| 경로 | 역할 |
|---|---|
| `CLAUDE.md` | HERMES 운영 규칙 (Claude Code가 자동 로드) |
| `SOUL.md` | HERMES 헌장 — 판단 우선순위와 금지 사항 |
| `.claude/agents/` | 서브에이전트 8종 (atlas·forge·probe·warden·oracle·scribe·augur·herald) |
| `hermes/` | 큐(bus)·라우터·Ollama 워커 |
| `channel/` | Discord 봇 + webhook 알림 |
| `memory/` | vault→Chroma 인덱서, RAG 검색 |
| `pipelines/` | 쇼츠 / 트레이딩 / 임베디드 가이드 |
| `vault/` | Obsidian으로 여는 지식 저장소 (ADR·런북·회고) |
| `scripts/` | bootstrap, healthcheck |
| `data/` | SQLite·Chroma·n8n 데이터 (git 제외) |

## HITL 승인 흐름 (이 시스템의 심장)

```bash
tid=$(python -m hermes.bus add "v0.2 배포" --body "변경: ..." --approve)
python -m hermes.bus wait $tid --timeout 600
# Discord 승인 채널에 카드가 뜨고, [승인]/[거부] 버튼 클릭 결과가 반환됨
# approved → 실행 / rejected·timeout → 중단
```

## 설계 원칙 (요약)

1. 오케스트레이션은 HERMES 단일 계층 — n8n에 판단 로직 금지
2. 비용 라우팅: 초안·요약·분류는 Ollama, 코드·설계·리뷰는 Claude
3. 외부 영향 작업(배포·게시·실거래 변경)은 전부 Discord 승인 경유
4. **주문 실행 경로에 LLM 금지** — `pipelines/trading/README.md`
5. 결정은 ADR로 기록하고 인덱싱 — 미래의 HERMES가 검색해 쓴다

상세 결정 배경: `vault/decisions/ADR-0001-architecture.md`
