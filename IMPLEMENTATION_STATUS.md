# 구현 현황 (Implementation Status)

> 기준일: 2026-06-11 · 프로젝트: agent-hub (smart_ai)
> 범례: ✅ 구현+검증 완료 · 🟡 부분 구현 / 스텁 · ⬜ 미구현(설계만) · 🔒 의도적 미구현(안전장치)

## 1. 코어 오케스트레이션 (HERMES 골격)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 전역 설정 | `hermes/config.py` | ✅ | .env 단일 소스, 경로/모델/Discord/쇼츠 설정 |
| 작업 큐 (버스) | `hermes/bus.py` | ✅ | SQLite, HITL 승인 흐름 E2E 검증 |
| 비용 라우터 | `hermes/router.py` | ✅ | ollama(무료) vs claude(유료) 분기 |
| Ollama 워커 | `hermes/ollama_worker.py` | ✅ | 초안/요약/분류/번역, qwen2.5:7b |
| 서브에이전트 8종 | `.claude/agents/*.md` | ✅ | atlas/forge/probe/warden/oracle/scribe/augur/herald |

## 2. 채널 (Discord HITL)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| Discord 봇 | `channel/discord_bot.py` | ✅ | `hermes#4336` 온라인, 승인 버튼 → 큐 반영 E2E 검증 |
| 웹훅 알림 | `channel/notify.py` | ✅ | embed 알림, 레벨별 색상 |
| 승인 흐름 | (bus + bot) | ✅ | 카드 게시 → 클릭 → approved 수신 전 구간 검증 |

## 3. 메모리 (지식 계층)

| 구성요소 | 파일 | 상태 | 비고 |
|---|---|---|---|
| vault → Chroma 인덱서 | `memory/index_vault.py` | ✅ | nomic-embed-text 임베딩, 증분 인덱싱 |
| RAG 검색 | `memory/search.py` | ✅ | 코사인 유사도 검색 |
| Obsidian vault | `vault/` | ✅ | ADR 3건 + 런북, 기계 검색 동기화됨 |

## 4. 쇼츠 자동화 파이프라인

| 단계 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 1. 트렌드 수집 | `pipelines/shorts/n8n_workflow.json` | 🟡 | 스케줄 tick 스텁만. n8n 미기동(Docker) |
| 2. 스크립트 초안 | `script_gen.py` | ✅ | Ollama, JSON 강제 출력 |
| 3. 스크립트 다듬기 | (HERMES 위임) | ✅ | `--script` 수정본 투입 흐름 |
| 4. TTS | `tts.py` | ✅ | edge-tts, 문장별 합성 + 자막 타이밍 |
| 5a. 렌더링 (그라디언트) | `render.py` | ✅ | Pillow PNG overlay (libass 없는 ffmpeg 대응) |
| 5b. 렌더링 (썰 카툰) | `cartoon.py`+`story_gen.py`+`produce_story.py` | ✅ | 댕소리 스타일, ADR-0003. E2E 검증 |
| 6. 업로드 | — | 🔒 | YouTube Data API + HITL 승인 필요. 미구현이 곧 안전장치 |
| 7. 보고 | (notify) | ✅ | Discord embed |
| BGM 합성 | — | ⬜ | 저작권 무료 음원 조달 후 추가 |
| 장면 모션(Ken Burns) | — | ⬜ | 정적 슬라이드쇼 현재 |

**오케스트레이션 CLI**
- `produce.py` — 그라디언트 스타일 (`python -m pipelines.shorts.produce "주제"`)
- `produce_story.py` — 썰 카툰 스타일 (`python -m pipelines.shorts.produce_story "주제" [--story x.json]`)

## 5. 주식 자동매매 파이프라인

| 항목 | 상태 | 비고 |
|---|---|---|
| 설계 문서 | ✅ | `pipelines/trading/README.md` — 안전 불변식 + 이식 계획 |
| 실행 코드 | ⬜ | 미구현. 기존 `auto_trading` 리포 자산 이식 예정 |
| 안전 불변식 | 🔒 | **주문 실행 경로에 LLM 금지** (협상 불가). 모의투자 기본 |

이식 절차(예정): oracle(KIS 스펙) → atlas(설계) → forge(이식) → probe(모의검증) → warden(안전감사) → scribe(ADR).

## 6. 임베디드 개발 파이프라인

| 항목 | 상태 | 비고 |
|---|---|---|
| 설계 문서 | ✅ | `pipelines/embedded/README.md` — PlatformIO 워크플로 |
| 실행 코드 | ⬜ | 미구현. 빌드/테스트는 에이전트, 실기기 플래시는 HITL |

## 7. 인프라 / 셋업

| 항목 | 파일 | 상태 | 비고 |
|---|---|---|---|
| 부트스트랩 | `scripts/bootstrap.sh` | ✅ | macOS, 멱등 (단 brew python/ollama 결함은 uv/cask 우회 — 런북 참고) |
| 헬스체크 | `scripts/healthcheck.py` | ✅ | 6개 필수 구성요소 점검 |
| n8n | `docker-compose.yml` | 🟡 | 정의만. Docker 미기동 (선택 구성요소) |

## 8. 다음 우선순위 (제안)

1. **쇼츠 발행 자동화** — YouTube OAuth + HITL 업로드 (🔒 해제). BGM/모션 보강.
2. **트레이딩 이식** — 기존 auto_trading 자산을 안전 불변식 하에 이식 (모의투자부터).
3. **n8n 스케줄 배선** — 무인 트렌드 수집 → 자동 생산 루프.

## 알려진 환경 이슈 (재현/이전 시 주의)

- macOS 26.2에서 brew `python@3.12` 보틀이 libexpat 심볼 누락으로 깨짐 → **venv는 `uv venv --python 3.12 --seed`로 생성**.
- brew `ollama` 포뮬러(0.30.7)는 llama-server 바이너리 누락 결함 → **`ollama-app` cask(공식 앱) 사용**.
- 이 환경 ffmpeg는 슬림 빌드로 `drawtext`/`subtitles`(libass/freetype) 필터 없음 → **텍스트는 전부 Pillow PNG로 렌더 후 overlay**.
