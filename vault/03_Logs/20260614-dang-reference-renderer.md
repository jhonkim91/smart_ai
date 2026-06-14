# 2026-06-14 Dang_sound reference-grammar renderer

## 요청

사용자가 `data/reference/reference_video.webm` 내용을 보고 원본과 같은 구조로 제작하라고 요청. 현재 구조 변경 허용.

## 분석 근거

- Reference metadata: `1080x1920`, `30fps`, `44.601s`, video `av1`, audio `opus`.
- Extracted frames: `data/reference/frames/ref_000s.png`, `ref_002s.png`, `ref_010s.png`, `ref_020s.png`, `ref_035s.png`.
- Measured scene plate: approx `x=18..1065`, `y=537..1359`.
- Header/title grammar: large top white margin, left-aligned dog logo + `Dang_sound` + gray `댕소리`, big centered Korean title, hard rectangular scene plate, black subtitle box inside plate, red/yellow keyword highlights.

## Boundary

Third-party YouTube reference를 frame-for-frame 복제하지 않고, 제작 문법/레이아웃/타이밍을 맞춘 원본 각색 영상으로 제작했다.

## Code changes

- Added `pipelines/shorts/dang_reference.py`:
  - hard rectangular plate matching measured coordinates
  - left Dang_sound branding
  - big title y-position matching reference
  - black subtitle box inside plate
  - red/yellow phrase highlights
  - reference-like blob characters with camo hats
  - procedural backgrounds/props for hall/cabin/field/skyfall, black bag, note, CCTV, packs
- Updated `pipelines/shorts/produce_story.py`:
  - added `--style dang_reference`
  - style-specific brand defaults `Dang_sound / 댕소리`
- Added `data/shorts/dang_reference_neighbor_note.json`:
  - 10-scene original adapted true-story style script, duration close to reference.

## Final artifact

- Episode: `data/shorts/20260614-121553-story-Dang-reference-neighbor-note-v2/`
- Video: `data/shorts/20260614-121553-story-Dang-reference-neighbor-note-v2/final_bgm.mp4`
- Previews:
  - `preview_0s.png`
  - `preview_2s.png`
  - `preview_10s.png`
  - `preview_20s.png`
  - `preview_35s.png`

## Verification

- `ffprobe`: output video `h264`, `aac`, `1080x1920`, `30fps`, duration `43.800000s`, size `1139715` bytes.
- `python -m compileall -q hermes channel pipelines tests`: passed.
- `python -m unittest discover -v`: 18 tests passed.
- Visual review of 0s/10s/35s previews: layout plate/header/title/subtitle grammar now much closer to reference than rounded-card renderer. Remaining difference: procedural vector art is not a photoreal/AI-rendered duplicate of the source.
