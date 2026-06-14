# 런북: 모니터링 대시보드

읽기 전용 관찰 도구. 작업 실행/승인은 하지 않는다(Discord HITL 유지).

## 기동

```bash
source .venv/bin/activate
pip install -r requirements.txt        # fastapi, uvicorn, rich 추가됨

# 웹 대시보드 (브라우저)
python -m dashboard.server             # http://127.0.0.1:8765
bash scripts/run_dashboard.sh          # 동일(헬퍼)

# 터미널 TUI (에이전트 병렬 가동)
python -m dashboard.tui                # rich 자동갱신(2초)
python -m dashboard.tui --once         # 1회 출력
watch -n2 'python -m dashboard.tui --once'   # rich 없이 watch로
```

## 3개 뷰

- **칸반 보드**: status별 컬럼(대기승인/대기/진행/완료) + 작업 카드(kind 배지, 🔒 승인필요).
- **에이전트 병렬**: ollama + 서브에이전트 8종 레인. running이면 green 점등 → 병렬 가동 한눈에.
  배정은 `hermes.router` 매핑 기반(조회만). queued는 레인별 대기 큐 깊이.
- **파이프라인 플로우**: 트렌드→초안→다듬기→TTS→렌더→승인→업로드→보고. 산출물/큐 기준 done/active/idle.

## 자동 갱신

웹은 `/stream`(SSE)로 DB 변경 시 푸시, 실패하면 3초 폴링 폴백. TUI는 2초 주기 재조회.

## 모바일 / 외부 노출 (선택)

기본은 `127.0.0.1` 단독·무인증. 폰에서 보려면 인증 토큰 + 바인딩 변경:

```bash
DASHBOARD_HOST=0.0.0.0 DASHBOARD_TOKEN=$(openssl rand -hex 16) python -m dashboard.server
# 접속: http://<맥-LAN-IP>:8765/?token=<토큰>
```

외부 어디서나는 포트 직개방 대신 Tailscale / Cloudflare Tunnel 권장. 읽기 전용은 유지.

## 에이전트 가동 계측 (Phase 4 — 완료)

병렬 뷰 레인은 `run_events`의 구조화 이벤트(`{agent,stage,kind}`)로 점등된다.
- **Ollama 워커**: `hermes.worker`가 claim/done/fail을 자동 기록 → 워커만 돌리면 ollama 레인 자동 점등.
- **Claude 서브에이전트**: HERMES가 위임할 때 직접 기록한다.
  ```bash
  python -m hermes.activity start <task_id> <agent> --kind <kind>
  python -m hermes.activity done  <task_id> <agent> --kind <kind>
  ```

레인 상태: `active`(현재 running 또는 방금 claim) > `recent`(최근 120초 내 가동) > `idle`.
윈도는 `dashboard/queries.py`의 `RECENT_WINDOW_SEC`로 조정한다. 이벤트 타임라인은
파이프라인 탭 하단에 agent 배지와 함께 표시된다.

## 검증

```bash
python -m unittest tests.test_dashboard   # 7 tests OK (읽기전용·스키마)
python -m dashboard.tui --once            # 실제 DB 레인 출력
```
