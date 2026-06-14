# 쇼츠 자동화 파이프라인

목표: 트렌드 수집 → 스크립트 → 음성 → 영상 → 승인 기반 업로드 → 보고를 안전하게 운영.

## 단계 설계

| 단계 | 도구 | 상태 | 비고 |
|---|---|---:|---|
| 1. 트렌드/소재 수집 | `pipelines.shorts.trends` + launchd | ✅ | RSS 필수, YouTube mostPopular 선택 |
| 2. 스크립트 초안 | Ollama (`hermes.worker`/`hermes.ollama_worker`) | ✅ | 무료, 토큰 절약 |
| 3. 스크립트 다듬기 | HERMES/Claude | ✅ | 발행 품질 게이트 |
| 4. TTS | edge-tts | ✅ | 문장별 합성 + 자막 타이밍 |
| 5. 렌더링 | FFmpeg + Pillow | ✅ | 그라디언트/썰 카툰 |
| 5a. BGM | `bgm.py` | 🟡 | 기능 구현됨. 실제 음원은 `assets/bgm/`에 사용자가 추가 |
| 5b. 모션 | `produce_story.py --motion` | ✅ | Ken Burns `zoompan` |
| 6. 업로드 | YouTube Data API v3 | 🟡 | Discord HITL 승인 후 `private/unlisted`만 |
| 7. 보고 | `channel.notify` | ✅ | Discord embed, webhook 없으면 local log |

## 안전 규칙

- 외부 게시는 반드시 Discord 승인 절차를 거친다.
- `public` API 업로드는 코드에서 차단한다. 최종 공개는 사람이 YouTube Studio에서 전환한다.
- 저작권 소재(음원/영상/이미지) 사용 전 라이선스를 확인하고 기록한다.
- 스케줄러(launchd/n8n)는 트리거만 담당한다. 판단 로직과 업로드 실행은 넣지 않는다.

## 사용 예

### 트렌드 후보 수집

```bash
python -m pipelines.shorts.trends --dry-run
python -m pipelines.shorts.trends            # 후보를 kind=draft로 bus 적재 + Discord 보고
python -m hermes.worker --once               # queued draft 1건을 Ollama로 처리
```

매일 09:00 자동 실행이 필요하면:

```bash
bash scripts/install_launchd.sh
```

### 영상 생성

```bash
python -m pipelines.shorts.produce "주제" --notify
python -m pipelines.shorts.produce "주제" --script refined.json
python -m pipelines.shorts.produce "주제" --bgm random

python -m pipelines.shorts.produce_story "주제" --notify
python -m pipelines.shorts.produce_story "주제" --story story.json --motion --bgm random
```

### 실사 합성 영상(댕소리 기법) — produce_real

실사 스톡영상 배경 + 긴 팔다리 스틱 캐릭터(부유 애니메이션) + UI 레이어를 ffmpeg
overlay로 합성한다. 원본 댕소리의 "실사 배경 위 2D 캐릭터" 구조를 재현한다.

```bash
# 1) Pexels 무료 API 키 발급(1분): https://www.pexels.com/api/ → .env에 추가
echo 'PEXELS_API_KEY=발급받은키' >> .env

# 2) 장면별 query(영어 검색어)·pose·chars를 담은 story JSON으로 실행
python -m pipelines.shorts.produce_real "제목" --story story.json --notify
```

- 키가 없으면 자동으로 2D 그라디언트 배경으로 폴백(스틱 캐릭터·UI는 동일).
- story scene 필드: `query`(스톡 검색어) > `bg`(매핑 키) 우선순위. `pose`는
  stand/spread/point/hold, `chars[]`는 color/x/scale/expr/prop/flip/foot_y.
- 다운로드 클립은 `data/stock/`에 캐시(같은 query 재다운로드 안 함).
- 저작권: Pexels License(무료·상업적 사용 가능). credits가 result.json에 기록됨.

| 모듈 | 역할 |
|---|---|
| `stock_bg.py` | Pexels 검색·다운로드·캐시, scene→영어쿼리 매핑 |
| `actor.py` | 긴 팔다리 스틱 캐릭터 투명 PNG(pose/expr/prop) |
| `produce_real.py` | 장면별 bg영상+캐릭터+UI overlay 합성 → concat → TTS mux |

### 원본 유사도 자동 개선 루프 (autotune + n8n)

"원본과 100% 동일"은 원본의 3D 캐릭터 리그·전용 스톡·정확한 타이밍 등 **소스 자산이
없어 픽셀 일치가 원리적으로 불가**하다. 대신 객관 지표(SSIM)를 측정하며 레이아웃을
자동 수렴시키고, 파라미터로 더 못 올리면 HERMES(세션)에 코드 개선을 인계한다.

```bash
# 1회 수동 실행(측정→좌표하강 튜닝→수렴 시 HITL 인계)
python -m pipelines.shorts.tune_cycle --iters 40 --target 0.85

# 유사도만 측정
python -m pipelines.shorts.compare gen.mp4 data/reference/reference_video.webm --frames 8
```

| 모듈 | 역할 |
|---|---|
| `compare.py` | 생성본 vs 원본 프레임 SSIM(전체/영역별: 헤더·제목·카드·자막) |
| `tuning.py` | 레이아웃 파라미터(카드/제목/자막) 저장소. reference_style이 import 시 반영 |
| `autotune.py` | SSIM을 목적함수로 좌표하강 탐색 → best 파라미터 영속화 + 이력 로깅 |
| `tune_cycle.py` | autotune 1사이클 + 수렴 시 bus HITL 인계(중복 방지) + 보고 |

**n8n 자동 트리거** (Docker 불필요, npm n8n):

```bash
bash scripts/install_n8n.sh          # n8n 설치 + 워크플로 import
bash scripts/install_n8n_launchd.sh  # 로그인 시 상주(스케줄 동작 전제)
# http://localhost:5678 에서 'shorts-autotune-loop' Active 토글 → 6시간마다 자동 실행
```

원칙1 준수: n8n은 `tune_cycle`을 **트리거/보고만** 한다. 측정·탐색·인계 판단은
세션 계층 코드(autotune/tune_cycle)에 있고, 코드 개선(판단)은 HERMES/사람이 한다.
파라미터 탐색은 layout SSIM ~0.65에서 수렴(구조적 상한) → bus에 `kind=autotune`
작업으로 인계되어 다음 세션이 렌더러 코드(폰트·자간·캐릭터 스타일)를 개선한다.

### YouTube 업로드

```bash
python -m pipelines.shorts.auth_youtube
python -m pipelines.shorts.upload data/shorts/<일시-주제> --privacy unlisted
```

업로드 CLI는 내부적으로:

1. `youtube_upload` 승인 task 생성
2. Discord 승인 버튼 대기
3. 승인된 경우에만 `videos.insert` 실행
4. `publish_history`로 중복 업로드 차단

순서로 동작한다.

## 주요 모듈

| 모듈 | 역할 |
|---|---|
| `trends.py` | RSS/YouTube 트렌드 수집 → 후보 생성 → bus/Discord 보고 |
| `script_gen.py` | Ollama 초안(JSON: title/hook/lines/outro) |
| `story_gen.py` | 썰 카툰용 story JSON 생성 |
| `tts.py` | edge-tts 문장별 합성 + 자막 타이밍 + 오디오 연결 |
| `render.py` | Pillow 텍스트 PNG + ffmpeg overlay 합성 |
| `cartoon.py` | 댕소리 스타일 장면 프레임 렌더링 |
| `produce.py` | 그라디언트 쇼츠 오케스트레이션 CLI |
| `produce_story.py` | 썰 카툰 쇼츠 오케스트레이션 CLI |
| `bgm.py` | BGM 반복/덕킹/믹싱 |
| `auth_youtube.py` | YouTube OAuth Desktop app 인증, token은 `data/`에 저장 |
| `upload.py` | HITL 승인 후 YouTube `videos.insert` 실행 |

## 현재 의도적으로 남겨둔 것

- n8n은 Docker 운영 부담 때문에 기본 경로에서 보류. 필요 시 `n8n_workflow.json`은 tick 검증용으로만 사용.
- YouTube 공개 전환은 자동화하지 않음.
- 실제 BGM 음원 파일은 저장소에 포함하지 않음(`assets/bgm/README.md` 참고).
