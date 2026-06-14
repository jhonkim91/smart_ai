# 2026-06-14 SoftBean 캐릭터 리디자인

## 요청

- 기존 쇼츠 파일럿의 캐릭터가 마음에 들지 않는다는 피드백.
- 쇼츠에 사용할 컨셉을 먼저 확인하고, 완전히 새롭게 디자인 계획을 수립한 뒤 진행.
- 유료 영상 생성툴/유료 TTS는 계속 배제.

## 컨셉 결정

- 장르: 사건 요약/실화 썰/반전형 쇼츠.
- 캐릭터 역할: 실제 인물 재현이 아니라, 사건 감정과 상황을 빠르게 전달하는 고정 마스코트.
- 새 방향: `SoftBean 2.5D`.
  - 큰 둥근 머리
  - 작은 젤리 몸통
  - 긴 누들형 팔다리
  - 볼터치와 검정 타원 눈
  - radial shading 기반 2.5D 젤리 질감
  - 얼굴을 가리지 않는 작은 소품

## 계획 문서

- `vault/runbooks/softbean-character-redesign-plan.md`

## 구현 변경

- `pipelines/shorts/dang_reference.py`
  - `_character()`를 기존 네모 블롭/큰 모자 캐릭터에서 SoftBean 2.5D 캐릭터로 전면 교체.
  - `numpy` + Pillow mask/radial shading으로 2.5D 광원 표현.
  - 다리/팔이 잘리지 않도록 몸통/다리 비율 수정.
  - 기존 story scale이 old blob 기준이라 SoftBean은 0.84배 보정.
  - 하단 자막 박스에 캐릭터가 묻히지 않도록 장면 배치를 기본 `raise_y=0.055`만큼 위로 올림.

## 산출물

### 캐릭터 시트

- `data/shorts/softbean_character_sheet.png`

### SoftBean 적용 파일럿 영상

- Episode: `data/shorts/20260614-124036-story-SoftBean-리디자인-파일럿-검은-봉투/`
- Video: `data/shorts/20260614-124036-story-SoftBean-리디자인-파일럿-검은-봉투/final.mp4`
- Previews:
  - `preview_002s.png`
  - `preview_022s.png`
  - `preview_040s.png`
  - `contact_sheet.jpg`

## 검증

- `ffprobe`: h264+aac, `1080x1920`, duration `43.819000`, size `4959966` bytes.
- `python -m compileall -q hermes channel pipelines tests`: 통과.
- `python -m unittest discover -v`: 18 tests 통과.
- 시각 점검:
  - 기존보다 머리/몸/팔다리/표정이 분리되어 캐릭터성이 개선됨.
  - 색상별 캐릭터 일관성 확인.
  - 일부 컷에서 하단 자막이 하체를 가리지만, 얼굴/표정/상체는 안정적으로 보임.
  - 다음 개선은 캐릭터를 장면별로 더 크게/작게 자동 조정하거나, 자막과 겹치지 않는 포즈 프리셋을 늘리는 것.

## 다음 개선 후보

1. 채널명과 캐릭터 이름을 정하면 색상/소품/표정 규칙을 `characters.json`에 고정.
2. `pose=phone`, `pose=fall`, `pose=lying`, `pose=cry`, `pose=walk` 추가.
3. Blender 3D 에셋화는 다음 단계. 현재는 무료 Pillow 렌더러로 빠르게 반복 검증.
