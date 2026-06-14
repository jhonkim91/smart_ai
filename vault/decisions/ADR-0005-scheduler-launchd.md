# ADR-0005: 스케줄러는 launchd 채택, n8n 보류 — 트리거 전용 원칙 유지

- 날짜: 2026-06-12
- 상태: 채택 (단, "n8n 보류" 부분은 2026-06-14 [[ADR-0007-real-footage-pipeline]]에서 일부 갱신 — autotune 트리거 용도로 n8n 도입. 트리거 전용 원칙은 그대로 유지)

## 배경

무인 루프 트렌드 수집 단계(`pipelines/shorts/trends.py`)를 매일 09:00 KST에 자동 실행할
스케줄러가 필요하다. pytrends는 2025-04 GitHub 아카이브로 production 부적합이 확인됐고,
권고 소스는 RSS(안정·무료)와 YouTube `videos.list?chart=mostPopular`(1 unit/call)로
결론났다. 스케줄러 후보로 n8n(기존 아키텍처 구성 요소)과 macOS launchd가 검토됐다.

## 결정

1. 트렌드 수집 스케줄러는 **macOS launchd** (`com.agent-hub.trends`)를 채택한다.
2. n8n은 현 단계에서 **보류** — 스케줄러 역할로 도입하지 않는다.
3. launchd도 "트리거만, 판단 로직 금지" 원칙을 동일하게 적용한다.
   plist에는 실행 경로·시각·로그 경로만 명시한다.
   모든 판단(피드 파싱, Ollama 분류, bus 적재, Discord 보고)은 Python 스크립트가 담당한다.
4. 설치는 `scripts/install_launchd.sh`로 멱등 실행한다 (`launchctl bootstrap/bootout`).
5. 로그는 `data/logs/trends.log`에 stdout/stderr를 함께 append한다.
6. `TREND_RSS_FEEDS`(필수) / `YOUTUBE_API_KEY`(선택)는 `.env`에서 관리한다.

## 근거

- macOS launchd는 OS 기본 기능이다. Docker 컨테이너·n8n 서버 상주 없이 동작하므로
  배터리·메모리 부담이 없다.
- 솔로 Mac 환경에서 n8n은 Docker 컨테이너가 24시간 상주해야 하고, 단순 타이머 용도에
  비해 운영 비용이 과잉이다.
- n8n Workflow에 판단 로직을 넣고 싶어지는 구조적 유혹이 있어 ADR-0001의
  "n8n 멍청한 파이프" 원칙을 위반할 리스크가 있다.
- launchd는 동일 원칙("트리거만")을 더 강제하는 구조다:
  plist는 선언형이라 로직 삽입이 불가능하다.

## 대안과 기각 사유

| 대안 | 기각 사유 |
|---|---|
| n8n Schedule Trigger | Docker 상주 부담, 판단 로직 혼입 리스크, 솔로 Mac에 과잉 |
| cron (`crontab`) | macOS에서 launchd가 공식 권고 대안; 기능 동등하나 로그 관리가 번거롭다 |
| GitHub Actions scheduled | 외부 의존, 로컬 파일/Ollama 접근 불가 |
| APScheduler in-process | Discord 봇 프로세스에 결합 시 단일 장애점; 별도 상주 프로세스 필요 |

## 영향

- **신규 파일**:
  - `pipelines/shorts/trends.py` — RSS + YouTube 수집 → Ollama 분류/제목 → bus + Discord
  - `scripts/launchd/com.agent-hub.trends.plist` — launchd 서비스 정의 템플릿
  - `scripts/install_launchd.sh` — 멱등 설치 스크립트
- **변경 파일**:
  - `hermes/config.py` — `TREND_RSS_FEEDS`, `YOUTUBE_API_KEY` 추가
  - `.env.example` — 두 변수 항목 추가
  - `requirements.txt` — `feedparser>=6.0` 추가
- 로그인 후 09:00 KST에 트렌드 수집이 자동 실행된다.
  영상 생산·업로드는 자동 트리거되지 않는다 — 주제 **제안**까지만.
- `TREND_RSS_FEEDS` 미설정 또는 전체 피드 실패 시 Discord warn 알림으로 보고된다.
- 향후 스케줄러 기능이 복잡해지면 n8n 재검토 가능.
  단, 판단 로직은 여전히 Python/HERMES 계층에 머물러야 한다.
