# 쇼츠 자동화 파이프라인

목표: 트렌드 수집 → 스크립트 → 음성 → 영상 → 업로드 → 보고를 무인 운영.

## 단계 설계 (전 구간 무료 도구)

| 단계 | 도구 | 비고 |
|---|---|---|
| 1. 트렌드/소재 수집 | n8n (RSS, HTTP Request) | 스케줄 트리거 |
| 2. 스크립트 초안 | Ollama (`hermes.ollama_worker draft`) | 무료, 토큰 절약 |
| 3. 스크립트 다듬기 | Claude (forge/herald) | 품질 게이트 |
| 4. TTS | edge-tts (무료) 또는 로컬 TTS | `pip install edge-tts` |
| 5. 렌더링 | FFmpeg / MoviePy | 자막 + BGM 합성 |
| 6. 업로드 | YouTube Data API v3 | **HITL 승인 후** 실행 |
| 7. 보고 | `channel.notify` | Discord embed |

## 안전 규칙

- 업로드(외부 게시)는 반드시 승인 절차를 거친다:
  `bus add "ep042 업로드" --approve` → `bus wait` → approved일 때만 업로드.
- 저작권 소재(음원/영상/이미지) 사용 전 라이선스를 oracle로 확인하고 기록한다.

## 구현 현황 (2026-06-11, ADR-0002)

2~5단계 + 7단계 구현 완료. 한 줄로 에피소드가 나온다:

```bash
python -m pipelines.shorts.produce "주제" --notify
# → data/shorts/<일시-주제>/final.mp4 (1080x1920) + Discord 보고
python -m pipelines.shorts.produce "주제" --script refined.json   # Claude 수정본으로 재생산
```

| 모듈 | 역할 |
|---|---|
| `script_gen.py` | Ollama 초안 (JSON: title/hook/lines/outro) |
| `tts.py` | edge-tts 문장별 합성 + 자막 타이밍 + 오디오 연결 |
| `render.py` | Pillow 텍스트 PNG + ffmpeg overlay 합성 (libass 없는 빌드 대응) |
| `produce.py` | 전체 오케스트레이션 CLI |

미구현(의도적): 1단계 트렌드 수집(n8n, Docker 필요) · 6단계 업로드(YouTube OAuth + HITL 필수).

## 시작점 (n8n 스케줄 배선 — 선택)

1. `n8n_workflow.json`을 n8n에 import (워크플로우 메뉴 > Import from File)
2. Discord webhook URL을 본인 것으로 교체 후 활성화 — 6시간마다 tick 알림이 오면 배선 성공
