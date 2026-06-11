# ADR-0003: 댕소리 스타일 썰 쇼츠 생성기

- 날짜: 2026-06-11
- 상태: 채택

## 배경

사용자가 레퍼런스(유튜브 댕소리 채널, youtube.com/shorts/oVCpTGDASeU)와 같은
"실화 썰 스토리텔링" 스타일을 요청. 레퍼런스 분석 결과: 흰 프레임 + 상단 채널
브랜딩/검정 제목 + 중앙 장면 카드(단순 젤리 캐릭터 + 소품) + 검정 라운드 박스
자막(키워드 빨강/노랑 강조) + TTS 내레이션 + 장면 컷 전환.

## 결정

1. 기존 그라디언트 스타일(produce.py)과 별도로 **story 모드 3모듈** 추가:
   - `cartoon.py` — Pillow 장면 렌더러. 젤리 캐릭터(5표정/3소품/flip), 배경 7종
     +bg_colors 오버라이드, 2x 슈퍼샘플링 안티앨리어싱, 키워드 색상 자막.
   - `story_gen.py` — Ollama가 텍스트(제목/문장/강조 단어)만 생성, **장면 연출은
     파이썬 휴리스틱**(고정 캐스트, 표정 감성 매칭, bg 키워드 매핑)으로 결정론화.
   - `produce_story.py` — 오케스트레이션: 스토리 → tts.synthesize 재사용 →
     장면별 완성 프레임 PNG → ffmpeg concat demuxer 슬라이드쇼.
2. 멀티에이전트 워크플로(병렬 forge 3 + warden 검증)로 구현. warden이 모듈 간
   스키마 불일치 7건(chars/characters, expr/expression, bg_colors 무시 등)을
   통합 전에 수정 — 계약 명세를 프롬프트에 넣어도 키 이름 드리프트는 발생하니
   **교차 검증 단계는 필수**.

## 사용

```bash
python -m pipelines.shorts.produce_story "주제" --notify        # Ollama 초안
python -m pipelines.shorts.produce_story "주제" --story 다듬은스토리.json  # 발행 품질
```

## 결과

- E2E 2회 통과: Ollama 초안(62.5초/10장면), Claude 다듬은 썰(58.4초/12장면).
- Ollama(qwen2.5:7b) 스토리는 플롯이 어색함 → **발행용은 반드시 HERMES(Claude)가
  스토리 JSON을 집필/다듬어 --story로 투입**할 것 (refined 예시:
  data/shorts/refined_story_1.json).
- 잔여 과제: BGM(저작권 무료 음원 조달 필요), 장면 모션(Ken Burns), 업로드(HITL).
