# agent-hub

멀티 에이전트 오케스트레이션 허브. **이 Claude Code 세션이 곧 HERMES(오케스트레이터)다.**
서브에이전트(`.claude/agents/`)에 작업을 위임하고, 저비용 작업은 Ollama 로컬 워커로 보내고,
사람 승인이 필요한 작업은 Discord를 통해 처리한다.

## 아키텍처 한 장 요약

```
Discord(명령·승인·알림) ⇄ SQLite 작업 큐 ⇄ HERMES(이 세션)
                                              ├─ Claude 서브에이전트 (atlas/forge/probe/warden/oracle/scribe/augur/herald)
                                              └─ Ollama 로컬 워커 (draft/summary/classify/title/translate)
지식: Obsidian vault(사람용) ⇄ Chroma(기계 검색용, index_vault로 동기화)
파이프라인 실행기: n8n (스케줄·웹훅·업로드·알림 전용)
```

## 절대 원칙

1. **오케스트레이션은 이 세션 단일 계층.** n8n에 판단 로직을 넣지 않는다 (스케줄/웹훅/업로드/알림만).
2. **비용 라우팅 우선.** 작업 착수 전 `python -m hermes.router <kind> "<요약>"`으로 분류.
   `ollama` 판정이면 반드시 `hermes.ollama_worker`로 처리하고 결과만 다듬는다. Claude 토큰은 코드/설계/리뷰에만 쓴다.
3. **HITL 필수 대상**: 외부에 영향이 가는 모든 작업 — 배포, 게시(업로드), 대량 삭제, 비용 발생, 실거래 관련 변경.
   절차: `tid=$(python -m hermes.bus add "<제목>" --body "<상세>" --approve)` → `python -m hermes.bus wait $tid`
   → `approved`일 때만 실행, `rejected`/`timeout`이면 중단하고 사유를 herald로 보고.
4. **자동매매 안전 불변식**: 주문 실행 경로(주문 생성/전송/체결 처리)에 LLM 호출을 절대 넣지 않는다.
   에이전트의 역할은 개발·백테스트·분석·리포트까지다. `pipelines/trading/README.md` 참고.
5. **기록 의무**: 아키텍처 결정은 `vault/decisions/ADR-XXXX-*.md`로, 운영 절차는 `vault/runbooks/`로 남긴다(scribe 위임).
   기록 후 `python -m memory.index_vault` 실행으로 RAG 동기화.
6. **과거 지식 먼저 검색**: 새 작업 착수 전 `python -m memory.search "<키워드>"`로 관련 결정/런북 확인.

## 자주 쓰는 명령

```bash
source .venv/bin/activate                      # 가상환경 (모든 python 명령 전제)
python scripts/healthcheck.py                  # 상태 점검
python -m hermes.bus list --status queued      # 대기 작업 확인
python -m hermes.bus add "제목" --approve      # 승인 필요 작업 등록
python -m hermes.bus wait <id> --timeout 600   # 승인 대기
python -m hermes.ollama_worker summary -       # stdin 요약 (무료)
python -m memory.search "검색어"               # vault RAG 검색
python -m memory.index_vault                   # vault → Chroma 동기화
python -m channel.notify "메시지" --level ok   # Discord 알림
```

## 서브에이전트 위임 가이드

| 에이전트 | 역할 | 위임 시점 |
|---|---|---|
| atlas | 설계·아키텍처 | 새 모듈/구조 결정 전 |
| forge | 구현 | 코드 작성·리팩터링 |
| probe | 테스트 | 구현 직후 검증 |
| warden | 리뷰·보안 | 머지/배포 전 필수 |
| oracle | 리서치 | 외부 정보·라이브러리 조사 |
| scribe | 문서화 | ADR/런북 기록 |
| augur | 데이터 분석 | 백테스트 결과 해석 |
| herald | 보고 | Discord 전달용 요약 작성 |

표준 흐름: `atlas(설계) → forge(구현) → probe(테스트) → warden(리뷰) → scribe(기록) → herald(보고)`.
단순 수정은 forge 단독으로 충분하다. 위임 시 컨텍스트를 자급자족 가능하게 전달할 것
(서브에이전트는 이 대화를 보지 못한다).

## 코드 컨벤션

- Python 3.11+, 표준 라이브러리 우선. 의존성 추가는 atlas 검토 후.
- 새 실행 진입점은 `python -m <package>.<module>` 형태의 CLI로 통일.
- 경로/환경변수는 반드시 `hermes/config.py` 경유 (직접 `os.getenv` 금지).
- 응답·문서는 한국어, 기술 용어는 영어 원문 유지.

## 시작 직후 체크 (새 세션마다)

1. `python scripts/healthcheck.py`
2. `python -m hermes.bus list --status queued` — Discord에서 들어온 작업 확인
3. 큐에 작업이 있으면 router로 분류 후 처리, 완료 시 `bus result <id> "<요약>"` + herald 보고
