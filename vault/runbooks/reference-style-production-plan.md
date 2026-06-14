# 계획: 원본 레퍼런스풍 쇼츠 스타일 개선

> **상태: 완료·대체됨 (2026-06-14)** — 이 계획은 모두 구현됐고, 이후 실사 합성
> 파이프라인으로 크게 확장됐다. 현재 기준은 [[ADR-0007-real-footage-pipeline]]를 따른다.
> 아래는 당시 계획 기록(히스토리)으로 보존한다.

## 목표

현재 `cartoon.py` 기반 썰 쇼츠는 레이아웃은 맞지만 캐릭터·장면 디테일이 단순해서 원본 레퍼런스 대비 퀄리티가 낮다. 먼저 **미래 제작 기준으로 삼을 reference MP4**를 만들고, 사용자가 확인한 뒤 이 스타일을 기본 쇼츠 제작 스타일로 확장한다.

## 범위

- 포함:
  - 흰 배경 + 상단 브랜딩 + 굵은 제목 + 중앙 rounded scene card + 검정 자막 박스 구조 유지
  - 더 정교한 mascot/캐릭터, 장면 소품, 자막 강조색, 카드 질감 개선
  - `produce_story.py`에서 `--style reference`로 선택 가능하게 연결
  - 레퍼런스용 story JSON + MP4 + preview PNG 생성
- 제외:
  - Telegram
  - 주식 실행 코드
  - 임베디드 실행 코드
  - YouTube 실제 업로드/public 공개

## 구현 파일

1. 신규 `pipelines/shorts/reference_style.py`
   - 고품질 레퍼런스 프레임 렌더러
   - 캐릭터: 외곽선, 하이라이트, 표정, 그림자, 간단 소품
   - 장면: night/room/street/sky 카드 배경 소품 추가
   - 자막: 검정 rounded box, red/yellow 강조 유지
2. 수정 `pipelines/shorts/produce_story.py`
   - `--style cartoon|reference` 옵션 추가
   - 기본값은 기존 호환을 위해 `cartoon`
3. 신규 `data/shorts/reference_style_story.json`
   - 사용자가 확인할 원본 스타일 기준 스토리 고정본
4. 테스트/검증
   - `python -m unittest discover -v`
   - `python -m compileall -q hermes channel pipelines tests`
   - `ffprobe`로 1080x1920/30fps/길이 확인
   - preview frame 추출 후 시각 확인

## 롤백

- `produce_story.py`의 기본값은 `cartoon`이라 기존 생성 경로는 유지된다.
- 문제가 있으면 `--style reference` 사용을 중단하고 신규 `reference_style.py`만 되돌리면 된다.

## 완료 기준

- `final_bgm.mp4` 생성
- `preview_002s.png`, `preview_030s.png` 생성
- 테스트 통과
- 사용자가 눈으로 확인 가능한 경로 보고

## 2차 품질 개선 계획 (2026-06-14)

참조 영상 기준과 기존 preview frame을 대조한 결과, “레이아웃은 맞지만 카드 내부가 비고 캐릭터/소품 식별성이 약한 것”이 가장 큰 품질 저하 요인이다. 다음 순서로 개선한다.

1. **스토리 JSON을 시각 지시 포함 형식으로 보강**
   - 각 scene에 `props`를 추가해 `sound_mark`, `cane`, `medicine_bags` 같은 핵심 소품을 텍스트 감지가 아닌 구조화 데이터로 전달한다.
   - 캐릭터에 `scale`, `foot_y`, `accessory`를 넣어 자막 박스에 가리지 않게 하고 할머니/주인공을 한눈에 구분한다.
2. **reference renderer 디테일 강화**
   - `night`: 윗집/천장선, 창문, `쿵!` 효과선 추가.
   - `room`: 벽 장식, 조명, 바닥/가구/약봉지/지팡이 추가.
   - `alert`: 붉은 spotlight, 경고 아이콘, shock lines 추가.
   - 캐릭터: 흰머리, 눈물, 지팡이 accessory, 더 큰 그림자/발 위치 제어.
3. **자막 품질 보강**
   - 공백 포함 highlight phrase(`한 달째`)도 색상 강조가 적용되도록 token 기반이 아닌 substring span 기반 렌더링으로 수정한다.
4. **브랜딩 기본값 정리**
   - `--style reference`는 story에 brand가 없더라도 `댕소리 / 오늘의 실화 썰`을 기본값으로 사용한다.
5. **검증**
   - `python -m compileall -q hermes channel pipelines tests`
   - `python -m unittest discover -v`
   - `python -m pipelines.shorts.produce_story "원본 스타일 기준 샘플 v2" --story data/shorts/reference_style_story.json --style reference --motion --bgm reference-soft-loop.m4a`
   - `ffprobe`로 1080x1920/30fps/duration 확인 후 `preview_002s.png`, `preview_030s.png`를 추출해 시각 검수한다.
