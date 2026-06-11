# ADR-0002: 쇼츠 파이프라인 MVP 구현 방식

- 날짜: 2026-06-11
- 상태: 채택

## 배경

쇼츠 자동화 1차 목표는 "주제 → 완성 MP4"를 무료 도구만으로 무인 생산하는 것.
설계(README)의 7단계 중 2(초안)~5(렌더링)+7(보고)를 `pipelines/shorts/`에 구현했다.

## 결정

1. **스크립트 초안은 Ollama(qwen2.5:7b)** — JSON 강제 출력(title/hook/lines/outro).
   다듬기는 HERMES(Claude)가 수정본 JSON을 `produce --script`로 넘기는 2단계 구조.
2. **TTS는 edge-tts(무료)** — 문장별 개별 합성 후 ffmpeg concat.
   문장별 실측 길이로 자막 타이밍을 계산(SubMaker 단어 단위보다 단순·정확).
   기본 음성 `ko-KR-InJoonNeural` (.env `EDGE_TTS_VOICE`로 교체 가능).
3. **자막/제목은 Pillow로 투명 PNG 렌더 → ffmpeg overlay 합성.**
   사유: 이 환경의 brew ffmpeg 8.1.1 보틀에는 libass·freetype이 빠져 있어
   `subtitles`/`drawtext` 필터가 없다. Pillow 방식은 폰트(AppleSDGothicNeo) 직접
   제어가 가능해 오히려 견고하다.
4. **업로드(6단계)는 미구현이 곧 안전장치** — 외부 게시는 HITL 승인
   (`bus add --approve`) 이후 별도 모듈로만 추가한다. YouTube Data API OAuth
   credential이 선행 조건.
5. n8n(1단계 트렌드 수집·스케줄)은 보류 — Docker 미기동. 수동 주제 입력으로 시작.

## 사용

```bash
python -m pipelines.shorts.produce "주제" --notify
# → data/shorts/<일시-주제>/final.mp4 (1080x1920, h264+aac)
```

## 결과

- E2E 검증 2회 통과 (22.8초/37.5초 에피소드, 렌더 산출물 프레임 검수 완료)
- Ollama 초안 품질은 거친 편 → 발행용은 반드시 Claude 다듬기 단계를 거칠 것
