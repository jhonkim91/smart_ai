# ADR-0006: 안전 범위 큐 worker — Ollama 작업만 자동 소비

- 날짜: 2026-06-14
- 상태: 채택

## 배경

Discord, 트렌드 수집, launchd가 `hermes.bus`에 작업을 쌓을 수 있지만, 기존 구조는
Claude Code 세션이 직접 큐를 보고 처리해야 했다. 이 때문에 `kind=draft`처럼 Ollama로
충분한 저위험 작업도 수동 처리 대기 상태로 남을 수 있었다.

동시에 코드 작성, 리뷰, 배포, 업로드, 승인 대기 작업은 자동 worker가 임의로 실행하면
안전 원칙을 깨뜨릴 수 있다.

## 결정

1. `hermes.worker`를 추가해 `draft/summary/classify/title/translate` 같은 Ollama 안전 kind만
   자동 소비한다.
2. worker는 `bus.claim_next_task()`로 가장 오래된 `queued` 작업을 원자적으로 `running`으로
   전환한 뒤 처리한다.
3. 처리 결과는 `tasks.result`와 `tasks.status`에 저장하고, 단계별 이벤트는
   `run_events` append-only 로그에 남긴다.
4. 기본 실행은 1건 처리(`python -m hermes.worker --once`)이고, 상주 실행은
   `python -m hermes.worker --loop`로 명시한다.
5. 기본 kind 필터는 Ollama kind만이다. `code/design/review/test/research/docs/analysis/report`,
   업로드, 승인 대기 작업은 자동 claim하지 않는다.
6. 주식 실행 코드와 임베디드 실행 코드는 현재 스코프에서 제외한다.
7. 채널은 Discord만 사용한다. Telegram 구현은 하지 않는다.

## 영향

- 트렌드 수집이 만든 `kind=draft` 후보를 worker가 비용 낮게 처리할 수 있다.
- 작업별 실행 이벤트는 `python -m hermes.bus events <id>`로 확인할 수 있다.
- 외부 영향 작업과 Claude 판단이 필요한 작업은 여전히 HERMES/사람의 명시 처리 대상이다.

## 검증

- `tests/test_worker.py`에서 kind 필터, claim 상태 전환, result 저장, 이벤트 기록, 실패 처리 확인.
- 전체 회귀: `.venv/bin/python -m unittest discover -v`.
