# 2026-06-14 무료툴 기반 쇼츠 파일럿 제작

## 요청

- 유료 영상 생성툴/유료 TTS를 배제하고 쇼츠 제작을 진행.
- 업로드 레퍼런스의 제작 문법을 참고하되, 외부 원본 프레임/자산을 복제하지 않고 로컬 생성 에셋으로 파일럿 제작.

## 사용한 무료/보유 도구

- Python + Pillow: 프레임/캐릭터/자막/브랜딩 렌더링
- FFmpeg: 1080x1920 MP4 조립 및 프리뷰 프레임 추출
- edge-tts: 한국어 TTS 합성
- 기존 `pipelines.shorts.produce_story --style dang_reference --motion` 파이프라인

## 실행

```bash
source .venv/bin/activate
python -m pipelines.shorts.produce_story \
  "무료툴 파일럿-검은 봉투-v2" \
  --story data/shorts/dang_reference_neighbor_note.json \
  --style dang_reference \
  --motion
```

## 산출물

- Episode: `data/shorts/20260614-122723-story-무료툴-파일럿-검은-봉투-v2/`
- Video: `data/shorts/20260614-122723-story-무료툴-파일럿-검은-봉투-v2/final.mp4`
- Previews:
  - `data/shorts/20260614-122723-story-무료툴-파일럿-검은-봉투-v2/preview_002s.png`
  - `data/shorts/20260614-122723-story-무료툴-파일럿-검은-봉투-v2/preview_022s.png`
  - `data/shorts/20260614-122723-story-무료툴-파일럿-검은-봉투-v2/preview_040s.png`

## 검증

- `ffprobe`: h264+aac, `1080x1920`, `30fps`, duration `43.819000`, size `4911366` bytes.
- `python -m compileall -q hermes channel pipelines tests`: 통과.
- `python -m unittest discover -v`: 18 tests 통과.
- 프리뷰 시각 점검: 흰 캔버스, 상단 로고/브랜드, 굵은 제목, 중앙 장면, 장면 내부 검정 자막 박스, 빨강 키워드 강조, 고정 캐릭터 문법 확인.

## 적용 패치

- `pipelines/shorts/dang_reference.py`
  - 상단 서브브랜드 `댕소리`가 강한 offset shadow 때문에 두 겹으로 번져 보이는 문제를 줄이기 위해 회색 단일 텍스트로 변경.

## 다음 개선 후보

1. 캐릭터를 Blender 3D 에셋으로 교체하면 레퍼런스 대비 캐릭터 품질/일관성이 더 올라간다.
2. 지금 버전은 무료 edge-tts라 음성 품질은 파일럿 수준이다. 유료 TTS는 아직 도입하지 않는다.
3. 장면별 배경/소품 라이브러리를 늘리면 같은 템플릿으로 더 많은 소재를 양산할 수 있다.
