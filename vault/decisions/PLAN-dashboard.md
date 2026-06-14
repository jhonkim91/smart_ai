# agent-hub 모니터링 대시보드 구현 계획

> 작성일: 2026-06-14 · 대상: agent-hub (HERMES) · 형태: 로컬 FastAPI 웹 대시보드
> 목적: 작업 큐 · 서브에이전트 병렬 가동 · 쇼츠 파이프라인 플로우를 한 화면에서 관찰

## 0. 한 줄 요약

`data/hermes.db`(tasks / run_events / publish_history)를 **읽기 전용**으로 노출하는
FastAPI 서버 + 단일 HTML 프론트엔드. 칸반 / 에이전트 병렬 / n8n식 플로우 3개 뷰를 제공하고
SSE(폴링 폴백)로 자동 갱신한다. 판단 로직은 넣지 않는다(원칙 1: 오케스트레이션은 HERMES 단일 계층).
같은 백엔드(`queries.py` + `/api/*`)를 **웹 · 터미널 TUI · 향후 모바일**이 공유한다 —
화면 추가는 출력 어댑터만 추가하면 된다.

## 1. 설계 원칙 (CLAUDE.md 준수)

1. **읽기 전용 우선.** v1 대시보드는 DB를 조회만 한다. 승인·실행은 기존 Discord HITL 경로 유지
   (원칙 2: 채널은 Discord만). 대시보드에서 직접 작업을 실행/승인하지 않는다.
2. **판단 로직 금지.** 대시보드는 상태를 보여줄 뿐, 라우팅·승인·실행 결정을 하지 않는다.
3. **기존 컨벤션 준수.** 새 패키지 `dashboard/`, 진입점 `python -m dashboard.server`,
   경로/설정은 `hermes/config.py` 경유, DB 접근은 `hermes/bus.py` 헬퍼 재사용.
4. **의존성 추가는 atlas 검토 후.** FastAPI·uvicorn 2개 추가. 무의존 대안(stdlib `http.server`)도
   문서화하되 사용자가 FastAPI 선택.

## 2. 아키텍처

```
브라우저 (localhost:8765)
   │  단일 HTML + vanilla JS (빌드 불필요)
   │   ├─ 칸반 뷰        ─┐
   │   ├─ 에이전트 병렬 뷰 ├─ 탭 전환
   │   └─ 파이프라인 플로우 ┘
   │  ▲ SSE(/stream) 실시간 푸시, 실패 시 3s 폴링 폴백
   ▼
FastAPI (dashboard/server.py)
   ├─ GET /            대시보드 HTML
   ├─ GET /api/tasks   tasks 전체(칸반·병렬 뷰용)
   ├─ GET /api/agents  kind→agent 라우팅 + 가동 상태 집계
   ├─ GET /api/pipeline 쇼츠 단계별 진행(에피소드 디렉터리 + publish_history)
   ├─ GET /api/events  run_events 타임라인
   └─ GET /stream      SSE: DB 변경 감지 시 push
   │  ▲ 읽기 전용 SELECT (hermes.bus 헬퍼 재사용)
   ▼
data/hermes.db (SQLite)  ← 기존 워커/봇이 기록, 대시보드는 read-only
```

## 3. 데이터 매핑 (이미 존재하는 것 / 보강 필요한 것)

### 그대로 쓸 수 있는 것
- `tasks(id, title, body, kind, status, needs_approval, result, created_at, updated_at)`
  → 칸반 컬럼 = status(`pending`/`queued`/`running`/`done`), 카드 = 각 row.
- `router.route(kind)` → 각 작업이 어느 에이전트/Ollama로 가는지(에이전트 병렬 뷰 레인 배정).
- `publish_history(episode_dir, video_id, privacy_status, uploaded_at)` → 파이프라인 업로드 단계.
- `data/shorts/<episode>/` 디렉터리의 산출물(script.txt, *.mp3, *.mp4 등) → 파이프라인 단계별 진척.

### 보강 필요 (Phase 2, 병렬 뷰의 정밀도용)
- 현재 `run_events`는 비어 있음(0건). `hermes/worker.py`의 claim/처리 지점과
  서브에이전트 위임 시 `log_event(task_id, agent=..., stage=...)`를 남기도록 **경량 계측** 추가.
  → 이게 있어야 "지금 forge가 #12, probe가 #15를 동시에 잡고 있다"가 정확히 보임.
- 임시 대안: `run_events` 없이도 status=`running` + `router` 매핑으로 근사 레인 표시 가능(v1).

## 4. 3개 뷰 설계

### 4-1. 칸반 보드 (작업 큐)
- 컬럼: `대기승인(pending)` · `대기(queued)` · `진행(running)` · `완료(done)`.
- 카드: 제목, kind 배지(draft/code/design...), 승인필요 🔒 표시, 경과시간.
- 색상: kind별 컬러 토큰. 클릭 시 body/result 상세 패널.
- 현재 데이터: queued 16 / done 4 → 즉시 의미 있는 화면.

### 4-2. 에이전트 병렬 처리 뷰 (핵심)
- 레인: `ollama-worker` + 8 서브에이전트(atlas/forge/probe/warden/oracle/scribe/augur/herald) + `HERMES`.
- 각 레인에 현재 잡은 작업 카드 표시 → 동시에 여러 레인이 활성이면 "병렬 가동" 한눈에.
- 레인 헤더에 가동/대기 상태등(green=running). draft 류는 ollama 레인으로 몰림이 보이도록.
- 라우팅 근거: `router.OLLAMA_KINDS` / `CLAUDE_KINDS` 매핑 그대로 사용.

### 4-3. n8n식 파이프라인 플로우
- 노드: 트렌드수집 → 스크립트초안(ollama) → 다듬기(claude) → TTS → 렌더 → (HITL 승인) → 업로드 → 보고.
- 각 노드 상태: 산출물/이벤트 기준 대기/진행/완료/차단 색상. 노드 간 엣지 애니메이션.
- HITL 승인 노드는 별도 강조(사람 개입 지점). publish_history로 업로드 완료 판정.

## 5. 파일 구조 (신규)

```
dashboard/
  __init__.py
  server.py        # FastAPI 앱 + API 라우트 + SSE (웹·모바일 공용 백엔드)
  queries.py       # 읽기 전용 SELECT (bus 헬퍼 래핑) — 모든 프런트가 공유하는 단일 소스
  tui.py           # 터미널 TUI (python -m dashboard.tui) — queries.py 재사용
  static/
    index.html     # 반응형 단일 페이지: 탭 + 3개 뷰 + JS(빌드 없음). 모바일 폭 대응
requirements.txt   # + fastapi, uvicorn[standard], rich(TUI용)
scripts/
  run_dashboard.sh # uvicorn 기동 헬퍼 (선택)
tests/
  test_dashboard.py # API 응답 스키마/읽기전용 보장 테스트
```

> 핵심 분리: **출력 레이어(웹 HTML / 터미널 TUI / 향후 모바일)** 가 달라도
> **데이터 레이어(`queries.py`)** 는 하나. 새 화면 추가 = 출력 어댑터만 추가.

## 6. 단계별 구현 (서브에이전트 위임 흐름)

| 단계 | 담당 | 산출물 |
|---|---|---|
| 1. 설계 확정 | atlas | dashboard 모듈 경계·API 스키마·SSE 방식 ADR |
| 2. 백엔드 | forge | `dashboard/queries.py`, `server.py` (read-only API + /stream) |
| 3. 프론트(웹) | forge | `static/index.html` 3개 뷰 + 탭 + 자동갱신 (반응형, 모바일 폭 대응) |
| 3b. 터미널 TUI | forge | `dashboard/tui.py` — `rich.live`로 에이전트 레인 2초 갱신 (`queries.py` 재사용) |
| 4. 계측 ✅완료 | forge | `hermes/activity.py` + `worker.py` 연동 → 병렬 뷰 점등(active/recent), 이벤트 타임라인 |
| 5. 테스트 | probe | API 스키마·읽기전용·빈DB/대용량 케이스 |
| 6. 리뷰 | warden | DB 쓰기 경로 없음·로컬 바인딩(127.0.0.1)·입력 검증 확인 |
| 7. 기록 | scribe | ADR + `vault/runbooks/dashboard.md` 기동 절차 |
| 8. 보고 | herald | Discord 완료 보고 |

표준 흐름: atlas → forge → probe → warden → scribe → herald.

## 7. 기술 선택 근거

- **FastAPI + uvicorn**: 비동기 SSE 간단, 자동 문서화, 단일 파일로 충분. (사용자 선택)
- **단일 HTML + vanilla JS**: 빌드 도구 없이 `static/`만 서빙. 플로우는 경량 SVG/CSS로 직접 그림
  (외부 노드 에디터 라이브러리 미도입 → 의존성 최소화).
- **SSE > WebSocket**: 단방향 푸시면 충분, 폴링 폴백 단순.
- **보안**: `127.0.0.1`만 바인딩, 읽기 전용, 인증 불필요(로컬 단독 운영 전제). warden 확인 항목.

## 8. 검증 기준

1. `python -m dashboard.server` 기동 → `http://127.0.0.1:8765` 3개 뷰 렌더.
2. `python -m unittest tests.test_dashboard` 통과 (API 스키마 + 쓰기 경로 부재 확인).
3. 현재 DB(20건)로 칸반에 queued 16/done 4 정확 표시.
4. 새 작업 추가(`bus add`) 시 SSE로 3초 내 자동 반영.
5. `scripts/healthcheck.py` 영향 없음(대시보드는 선택 구성요소).

## 9. 모바일 확장성 (향후, 설계만 선반영)

지금 구조가 모바일 확장을 싸게 만드는 이유: 백엔드가 **JSON API + SSE**이고 프런트가
**반응형 단일 HTML**이라, 모바일은 "새 백엔드"가 아니라 "기존 API의 새 화면"이다.

확장 경로(권장 순):
1. **반응형 웹 (0 추가비용)** — `index.html`을 처음부터 모바일 폭(`@media`, flex-wrap)으로 설계.
   폰 브라우저로 접속하면 그대로 동작. 칸반은 가로 스크롤, 레인은 세로 스택으로 재배치.
2. **PWA (소규모)** — `manifest.json` + service worker 추가로 홈 화면 설치·전체화면.
   네이티브 앱 없이 앱처럼 사용. 같은 API 그대로.
3. **네이티브 앱 (선택)** — 정말 필요할 때만. 동일 `/api/*`를 소비하므로 백엔드 재작업 없음.

모바일 접속의 전제(보안) — **127.0.0.1 단독 + 무인증** 전제가 깨진다. 폰에서 보려면 서버가
LAN/외부에서 닿아야 하므로 다음 중 하나 + **인증 추가**가 필수다(warden 검토 항목):
- 같은 와이파이: `0.0.0.0` 바인딩 + 토큰 인증 (가장 단순).
- 외부 어디서나: Tailscale / Cloudflare Tunnel 같은 보안 터널 (포트 직접 개방 금지).
- 어느 경우든 **읽기 전용 유지**. 모바일에서 작업 실행/승인은 여전히 Discord HITL.

→ 결론: 지금은 ①을 기본으로 깔고(반응형 마크업), 인증은 토글 가능한 미들웨어 자리만 비워둔다.
   실제 폰 노출(②③)은 별도 작업으로 분리, 노출 시점에 인증·터널을 함께 적용한다.

## 10. 범위 밖 (명시적 제외)

- 대시보드에서의 작업 승인/실행/삭제 (Discord HITL 유지, 원칙 2).
- 인증/멀티유저/원격 노출 (로컬 단독).
- 주식·임베디드 파이프라인 시각화 (현재 스코프 제외).
- n8n 실제 연동 (현 단계 보류, 플로우는 시각화 전용).
