"""agent-hub 모니터링 대시보드.

읽기 전용(read-only)으로 data/hermes.db와 쇼츠 산출물을 관찰한다.
출력 레이어(웹/터미널 TUI/모바일)가 달라도 데이터 레이어(queries.py)는 하나다.

진입점:
    python -m dashboard.server     # FastAPI 웹 대시보드 (localhost:8765)
    python -m dashboard.tui        # 터미널 TUI (에이전트 병렬 가동)

원칙: 판단 로직 없음. 작업 실행/승인은 Discord HITL 경로 유지 (CLAUDE.md 원칙 1·2).
"""
