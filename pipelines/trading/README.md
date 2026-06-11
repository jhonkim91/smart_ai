# 주식 자동매매 파이프라인

## 안전 불변식 (협상 불가)

1. **주문 실행 경로(주문 생성·전송·체결 처리)에 LLM 호출 금지.**
   실행은 결정적(deterministic) Python 코드만 담당한다.
   이유: LLM은 지연·비결정성·비용 모두 실거래에 부적합하다.
2. 에이전트의 허용 범위: 전략 코드 **개발**, 백테스트, 결과 **분석**(augur),
   일일 **리포트**(herald), 이상 감지 **알림**까지.
3. 실거래 전환·전략 파라미터 변경·자금 한도 변경은 HITL 승인 대상.
4. `orders_count == 0` / no-real-orders 상태가 항상 검증·표시 가능해야 한다
   (모의투자 모드 기본).

## 기존 자산 이식 계획 (참조용 — 복붙 금지, warden 리뷰 후 이식)

기존 `auto_trading` / `Stock-Analist-auto-trading` 리포에서 검증된 조각:

- KIS API 인증/토큰 관리 (24h 토큰, 재발급 로직)
- rate limiter (20 calls/sec) — 기존 리포의 불일치 버그 수정본 기준
- 잔고 조회 / 주문 모듈 (국내·해외 분리)
- 백테스트 모듈: costs(거래세 0.20%, 수수료 0.015%) / metrics / slippage

이식 절차: oracle(현행 KIS 스펙 재확인) → atlas(새 구조 설계) →
forge(이식) → probe(모의투자 검증) → warden(안전 불변식 감사) → scribe(ADR 기록).

## 에이전트 운영 루프 (실거래와 분리된 바깥 고리)

```
장 마감 후: n8n 스케줄 → 일일 데이터 수집(결정적 코드)
          → augur 분석 → herald 리포트 → Discord
이상 감지:  결정적 모니터(임계값) → notify --level error → 사람 판단
```
