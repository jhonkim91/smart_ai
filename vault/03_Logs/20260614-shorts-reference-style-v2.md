# 2026-06-14 쇼츠 레퍼런스 스타일 개선 및 각색 영상 제작

## 요청

- 레퍼런스: `https://youtube.com/shorts/oVCpTGDASeU?si=mRNToFQgqb`
- 목표: 레퍼런스와 같은 쇼츠 제작 문법을 기준으로 품질 개선 후, 실화이야기 각색 영상 제작.

## 경계

외부 YouTube 영상을 100% 복제/재현하지 않고, 레이아웃·리듬·자막·캐릭터 문법을 참고한 **원본 각색 영상**으로 제작했다.

## 적용 변경

- `pipelines/shorts/reference_style.py`
  - night/room/alert/street 장면 디테일 강화.
  - `sound_mark`, `cane`, `medicine_bags`, `black_bag`, `note`, `milk`, `cctv` props 지원.
  - 캐릭터 accessory: `gray_hair`, `tear`, `cane`.
  - phrase 기반 자막 highlight 지원.
  - 불투명 검은 그림자 문제를 배경색 기반 그림자로 보정.
- `pipelines/shorts/produce_story.py`
  - reference 스타일 기본 브랜딩을 `댕소리 / 오늘의 실화 썰`로 설정.
  - full-frame Ken Burns zoom을 미세하게 낮춰 상단 브랜딩/제목 crop 방지.
- `data/shorts/original_true_story_neighbor_note.json`
  - 신규 각색 스토리: `새벽 3시, 문 앞의 검은 봉투`.
- `vault/runbooks/reference-style-production-plan.md`
  - 2차 품질 개선 계획 기록.

## 산출물

### Reference-style 기준 샘플

- Episode: `data/shorts/20260614-084305-story-원본-스타일-기준-샘플-v3/`
- Video: `data/shorts/20260614-084305-story-원본-스타일-기준-샘플-v3/final_bgm.mp4`
- Preview:
  - `preview_002s.png`
  - `preview_030s.png`

### 신규 각색 영상

- Episode: `data/shorts/20260614-085130-story-새벽-3시-문-앞의-검은-봉투-v2/`
- Video: `data/shorts/20260614-085130-story-새벽-3시-문-앞의-검은-봉투-v2/final_bgm.mp4`
- Preview:
  - `preview_002s.png`
  - `preview_030s.png`
  - `preview_050s.png`

## 검증

- `ffprobe`: 신규 각색 영상 `h264`, `1080x1920`, `30fps`, duration `60.500000`, size `6182819` bytes.
- `python -m compileall -q hermes channel pipelines tests`: 통과.
- `python -m unittest discover -v`: 18 tests 통과.
- preview frame 시각 검수: 상단 브랜딩/제목 잘림 없음, 검정 자막 박스 가독성 양호, 주요 props 및 red/yellow highlight 확인.

## 남은 개선

- 원본과 더 가까운 동적 캐릭터 포즈/컷 전환은 card-layer 애니메이션으로 별도 구현 필요.
- 실제 발행 전 BGM은 사용 라이선스/크레딧을 다시 확인해야 한다.
