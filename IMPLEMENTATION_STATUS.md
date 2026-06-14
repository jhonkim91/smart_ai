# 구현 현황 (Implementation Status)

> 기준일: 2026-06-14 · 프로젝트: agent-hub (smart_ai)  
> 범례: ✅ 구현+검증 완료 · 🟡 구현됨/운영 설정 필요 · ⬜ 미구현(설계만) · 🔒 의도적 미구현/수동 처리

## 이번 재점검 스코프

- **채널은 Discord로 확정**. Telegram은 사용하지 않으며 구현 대상에서 제외.
- **주식 실행 코드**와 **임베디드 실행 코드**는 현재 단계에서 제외. 문서/설계만 유지.
- 현재 집중 범위: HERMES 코어, Discord HITL, 메모리, 쇼츠 자동화, 안전한 스케줄/업로드 보조.

## 1. 코어 오케스트레이션 (HERMES 골격)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 전역 설정 | `hermes/config.py` | ✅ | `.env` 단일 소스, 경로/모델/Discord/쇼츠/트렌드 설정 |
| 작업 큐 (버스) | `hermes/bus.py` | ✅ | SQLite `tasks`, `publish_history`, `run_events`; 승인 작업 CLI 강제승인 차단 |
| 작업 claim/이벤트 로그 | `hermes/bus.py` | ✅ | `claim_next_task()`, `log_event()`, `bus events <id>` 추가 |
| 비용 라우터 | `hermes/router.py` | ✅ | Ollama vs Claude/subagent 분기 |
| Ollama 워커 | `hermes/ollama_worker.py` | ✅ | `draft/summary/classify/title/translate` |
| 큐 자동 소비자 | `hermes/worker.py` | ✅ | 안전한 Ollama kind만 자동 처리. 코드/리뷰/배포/업로드는 claim하지 않음 |
| 서브에이전트 8종 | `.claude/agents/*.md` | ✅ | atlas/forge/probe/warden/oracle/scribe/augur/herald |

## 2. 채널 (Discord HITL)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| Discord 봇 | `channel/discord_bot.py` | ✅ | `/ping`, `/task`, `/tasks`, 승인 카드 게시 |
| 재시작 안전 승인 버튼 | `channel/discord_bot.py` | ✅ | `discord.ui.DynamicItem` custom_id 기반으로 봇 재시작 후에도 callback 복원 |
| 승인 경합 방지 | `hermes/bus.py` | ✅ | `set_status_if_pending()` 원자 전환, 중복 클릭 방지 |
| 웹훅 알림 | `channel/notify.py` | ✅ | Discord embed 전송, webhook 없으면 `data/logs/notifications.log`에 local fallback |
| Telegram | — | 🔒 | 사용자 결정에 따라 사용하지 않음 |

## 3. 메모리 (지식 계층)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| Obsidian vault | `vault/` | ✅ | ADR/런북 저장소 |
| vault → Chroma 인덱서 | `memory/index_vault.py` | ✅ | Ollama `nomic-embed-text` 임베딩, 증분 인덱싱 |
| RAG 검색 | `memory/search.py` | ✅ | 코사인 유사도 검색 |

## 4. 쇼츠 자동화 파이프라인

| 단계 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 1. 트렌드 수집 | `pipelines/shorts/trends.py` | ✅ | RSS + 선택 YouTube mostPopular → 후보 생성 → `kind=draft` bus 적재 + Discord 보고 |
| 1a. 스케줄러 | `scripts/install_launchd.sh`, `scripts/launchd/com.agent-hub.trends.plist` | 🟡 | macOS `launchd` 템플릿 구현. 설치는 운영자 선택 |
| n8n | `docker-compose.yml`, `pipelines/shorts/n8n_workflow.json` | 🔒 | 현 단계 보류. Docker/n8n 없이 launchd로 트리거만 수행 |
| 2. 스크립트 초안 | `script_gen.py`, `hermes/worker.py` | ✅ | Ollama 기반 draft 생성/큐 처리 |
| 3. 스크립트 다듬기 | HERMES/Claude | ✅ | `--script`/`--story` 수정본 투입 흐름 |
| 4. TTS | `tts.py` | ✅ | edge-tts, 문장별 합성 + 자막 타이밍 |
| 5a. 렌더링(그라디언트) | `render.py`, `produce.py` | ✅ | Pillow PNG overlay + FFmpeg |
| 5b. 렌더링(썰 카툰) | `cartoon.py`, `story_gen.py`, `produce_story.py` | ✅ | 댕소리 스타일 story mode |
| BGM 합성 | `bgm.py`, `assets/bgm/` | 🟡 | 기능 구현/테스트 완료. 실제 음원 파일은 사용자가 YouTube Audio Library에서 추가 |
| 장면 모션(Ken Burns) | `produce_story.py --motion` | ✅ | `zoompan` 기반 선택 모션 |
| 6. YouTube 업로드 | `auth_youtube.py`, `upload.py` | 🟡 | `private/unlisted`만 허용, Discord HITL 승인 후 `videos.insert`; OAuth credential 필요 |
| 공개 전환 | YouTube Studio | 🔒 | API `public` 업로드는 코드에서 차단. 최종 공개는 사람이 수동 전환 |
| 7. 보고 | `channel/notify.py` | ✅ | Discord embed 또는 local log fallback |

## 5. 주식 자동매매 파이프라인 — 현재 제외

| 항목 | 상태 | 비고 |
|---|---|---|
| 설계 문서 | ✅ | `pipelines/trading/README.md` — 안전 불변식 + 이식 계획 |
| 실행 코드 | ⬜ | **현재 구현하지 않음**. 사용자 요청에 따라 스코프 제외 |
| 안전 불변식 | 🔒 | 주문 실행 경로에 LLM 금지, 실거래/주문 작업 금지 |

## 6. 임베디드 개발 파이프라인 — 현재 제외

| 항목 | 상태 | 비고 |
|---|---|---|
| 설계 문서 | ✅ | `pipelines/embedded/README.md` — PlatformIO 워크플로 |
| 실행 코드 | ⬜ | **현재 구현하지 않음**. 사용자 요청에 따라 스코프 제외 |

## 7. 인프라 / 셋업

| 항목 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 부트스트랩 | `scripts/bootstrap.sh` | ✅ | macOS, 멱등 설치 |
| 헬스체크 | `scripts/healthcheck.py` | ✅ | 필수 구성요소 점검, n8n은 선택 경고 |
| 테스트 | `tests/` | ✅ | Discord approval, upload safety, BGM, worker, notify fallback |
| 보안 ignore | `.gitignore` | ✅ | `.env`, `.venv`, `data/`, BGM 실제 음원 파일 ignore |

## 남은 운영 설정 / 사용자 액션

1. `TREND_RSS_FEEDS`를 `.env`에 넣고 `python -m pipelines.shorts.trends --dry-run`으로 후보 품질 확인.
2. 매일 자동 실행이 필요하면 `bash scripts/install_launchd.sh`로 launchd 등록.
3. BGM 사용 시 `assets/bgm/README.md` 절차대로 음원 파일을 추가.
4. YouTube 업로드 사용 시 `data/client_secret.json`을 배치하고 `python -m pipelines.shorts.auth_youtube`로 OAuth 토큰 생성.
5. 실제 공개는 YouTube Studio에서 사람이 최종 확인 후 수동 전환.

## 최근 검증

```bash
.venv/bin/python scripts/healthcheck.py
.venv/bin/python -m unittest discover -v
```

두 명령 모두 통과해야 현재 프로젝트를 정상 상태로 본다.
