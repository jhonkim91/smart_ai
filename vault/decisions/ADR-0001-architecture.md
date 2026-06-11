# ADR-0001: agent-hub 초기 아키텍처

- 날짜: 2026-06-11
- 상태: 채택

## 배경

멀티 에이전트 시스템 구축에서 오케스트레이션 후보가 3중으로 겹쳤다
(Hermes, LangGraph/CrewAI, n8n). 솔로 운영 + Claude 외 전부 무료 조건.

## 결정

1. 오케스트레이션은 **Claude Code 세션(=HERMES) 단일 계층**. LangGraph/CrewAI 도입 보류.
2. n8n은 스케줄/웹훅/업로드/알림 전용 "멍청한 파이프"로 역할 한정.
3. 채널은 **Discord** (봇 + webhook). 승인은 버튼 UI(HITL).
4. 벡터 DB는 **Chroma** (PersistentClient, 파일 기반 — 서버 데몬 불요).
   Qdrant 기각 사유: 솔로 환경에 서버 운영 부담 과잉.
5. 임베딩/저비용 작업은 **Ollama** (qwen2.5:7b + nomic-embed-text, 둘 다 Apache-2.0
   — 상업적 사용 가능. EXAONE 기각 사유: 비상업 라이선스).
6. 상태/큐/로그는 **SQLite** 단일 파일 (data/hermes.db).
7. 자동매매: 주문 실행 경로 LLM 금지. 에이전트는 개발·분석·리포트까지.

## 영향

- 기존 미완성 구축물은 삭제하지 않고 참조 자산으로 보존, 검증 후 선별 이식.
- 모든 신규 결정은 ADR로 기록 후 인덱싱.
