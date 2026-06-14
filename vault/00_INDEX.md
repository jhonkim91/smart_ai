# agent-hub vault

HERMES와 사람이 공유하는 지식 저장소. Obsidian으로 열어서 사용.
모든 노트는 현재 프로젝트(agent-hub)와 유튜브 쇼츠 파이프라인 범위다.

## 구조

- `decisions/` — 아키텍처 결정 기록 (ADR). 번호 순 증가.
- `runbooks/` — 운영 절차. 복붙 가능한 명령 중심.
- `03_Logs/` — 작업 로그(날짜별).
- `retro/` — 회고. 실패에서 배운 것.

## 결정 (ADR)

| # | 제목 | 상태 |
|---|---|---|
| [[ADR-0001-architecture]] | 초기 아키텍처(HERMES 단일 오케스트레이션) | 채택 |
| [[ADR-0002-shorts-mvp]] | 쇼츠 파이프라인 MVP(무료 도구 무인 생산) | 채택 |
| [[ADR-0003-story-style]] | 댕소리 스타일 썰 쇼츠 생성기(2D) | 채택 |
| [[ADR-0004-youtube-upload-operating-model]] | 업로드: API는 초안 적재, 공개는 사람 | 채택 |
| [[ADR-0005-scheduler-launchd]] | 스케줄러 launchd(n8n 보류 → 0007서 일부 갱신) | 채택 |
| [[ADR-0006-worker-scope]] | 안전 범위 큐 worker(Ollama만 자동 소비) | 채택 |
| [[ADR-0007-real-footage-pipeline]] | 실사 합성 파이프라인 + 유사도 자동튜닝(n8n 트리거) | 채택 |

## 런북 (운영 절차)

- [[setup]] — 초기 설치(bootstrap → .env → healthcheck)
- [[discord-bot]] — Discord 봇 기동·HITL 승인 카드
- [[youtube-oauth]] — YouTube OAuth 업로드 준비
- [[security-check]] — 공개 리포 정기 보안 점검
- [[reference-style-production-plan]] — (완료·대체됨) 레퍼런스 스타일 개선 계획 히스토리

## 쇼츠 파이프라인 한눈에

- 2D 썰 카툰: `produce_story.py --style reference` (ADR-0003)
- 실사 합성: `produce_real.py --story <json>` (ADR-0007) — Pexels 실사 배경 + 연속
  애니메이션 캐릭터 + xfade 전환
- 원본 유사도 자동튜닝: `tune_cycle.py`(n8n 6h 트리거) → SSIM 수렴 → 한계 시 HITL 인계
- 상세 모듈 표는 `pipelines/shorts/README.md` 참조

## 규칙

- 모든 기록은 scribe 에이전트 형식을 따른다.
- 기록 후 `python -m memory.index_vault`로 RAG 동기화 (자동화 전까지 수동).
