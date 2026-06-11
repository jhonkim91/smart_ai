# agent-hub vault

HERMES와 사람이 공유하는 지식 저장소. Obsidian으로 열어서 사용.

## 구조

- `decisions/` — 아키텍처 결정 기록 (ADR). 번호 순 증가.
- `runbooks/` — 운영 절차. 복붙 가능한 명령 중심.
- `retro/` — 회고. 실패에서 배운 것.

## 규칙

- 모든 기록은 scribe 에이전트 형식을 따른다.
- 기록 후 `python -m memory.index_vault`로 RAG 동기화 (자동화 전까지 수동).
