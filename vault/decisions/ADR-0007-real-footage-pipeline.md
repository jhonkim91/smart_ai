# ADR-0007: 실사 합성 쇼츠 파이프라인 + 유사도 자동튜닝(n8n 트리거)

- 날짜: 2026-06-14
- 상태: 채택
- 관련: ADR-0003(썰 스타일), ADR-0005(스케줄러 — n8n 보류 부분을 일부 갱신)

## 배경

ADR-0003의 2D 카툰(`cartoon.py`/`reference_style.py`)은 레이아웃은 원본 댕소리와 맞지만,
원본의 (1) 실사/3D 배경, (2) 연속 캐릭터 모션, (3) 부드러운 3D풍 캐릭터를 재현하지 못했다.
"로컬에서 원본 100% 동일"은 원본의 3D 캐릭터 리그·전용 스톡·정확한 타이밍 등 소스 자산이
없어 픽셀 일치가 원리적으로 불가하다. 대신 같은 제작 문법으로 근접시키는 것을 목표로 한다.

## 결정

1. **실사 합성 파이프라인 신설** (`pipelines/shorts/produce_real.py`).
   장면별 `실사 배경(Pexels) + 스틱 캐릭터 투명PNG + UI 레이어`를 ffmpeg overlay 3단 합성.
   - 배경: `stock_bg.py` — Pexels 무료 API로 장면 키워드별 실사영상 검색·다운로드·캐시
     (`data/stock/`). `PEXELS_API_KEY`(.env) 필요, 없으면 2D 그라디언트 자동 폴백.
   - 캐릭터: `actor.py` — 큰 머리+달걀형 몸의 부드러운 3D풍 렌더(numpy 그라디언트 셰이딩,
     광택, 베레모). `render_actors_anim`이 20프레임 루프 → ffmpeg `loop`으로 연속 모션.
   - 장면 전환: `xfade`(0.4s 크로스페이드). 클립을 전환시간만큼 길게 빼 누적 offset으로
     체인 → 오디오 싱크 유지(영상 길이 = 오디오 길이).
2. **원본 유사도 자동 개선 루프**. SSIM(생성본 vs 원본 프레임)을 객관 지표로 측정·수렴.
   - `compare.py`(SSIM 영역별), `tuning.py`(레이아웃 파라미터 저장), `autotune.py`(좌표하강),
     `tune_cycle.py`(1사이클 + 수렴 시 HITL 인계).
3. **n8n을 autotune 트리거로 도입**(Docker 없이 npm n8n). ADR-0005의 "n8n 보류"를 이 용도에
   한해 갱신하되, **원칙은 그대로**: n8n은 `tune_cycle`을 스케줄로 트리거·보고만 하고,
   측정/탐색/인계 판단은 세션 계층 코드(autotune/tune_cycle)에 둔다. 이는 ADR-0005의
   "향후 복잡해지면 n8n 재검토 가능, 단 판단 로직은 Python/HERMES 계층" 단서에 부합한다.

## 근거

- 실사 배경 + 2D 캐릭터 overlay는 원본 댕소리의 실제 제작 기법과 같다.
- 파라미터 자동 탐색은 레이아웃 정합을 무인으로 수렴시키되, 한계(파라미터로 못 올리는
  렌더러 코드 개선)는 SSIM plateau 감지로 HITL 인계해 사람/HERMES가 이어받는다.
- 100% 픽셀 동일은 불가임을 명시하고, "측정 가능한 정합 상한 수렴 + 한계 시 인계"를 목표로 둔다.

## 영향

- 신규: `produce_real.py`, `stock_bg.py`, `actor.py`, `compare.py`, `tuning.py`,
  `autotune.py`, `tune_cycle.py`, `render_one.py`, `scripts/install_n8n*.sh`,
  `scripts/launchd/com.agent-hub.n8n.plist`.
- 변경: `hermes/config.py`(`PEXELS_API_KEY`, `STOCK_DIR`), `reference_style.py`
  (튜닝 파라미터 연동 + night 스카이라인), `pipelines/shorts/n8n_workflow.json`.
- 안전: 외부 게시는 여전히 HITL 승인 후 별도 단계. 배경 저작권은 Pexels License(무료·상업적
  사용 가능)이며 `result.json`에 credits 기록.

## 한계 / 후속

- 남은 격차: 배경-캐릭터 조명 통합(평면 합성), 소품 디테일.
- `kind=autotune` bus 작업이 쌓이면 렌더러 코드(폰트/자간/캐릭터)를 개선해 SSIM 상한을 올린다.
