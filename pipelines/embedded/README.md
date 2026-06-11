# 임베디드 개발 워크플로우

## 도구 체인

- PlatformIO CLI: `brew install platformio` 또는 `pip install platformio`
- 대상 프레임워크: ESP-IDF / Zephyr / FreeRTOS (프로젝트별 platformio.ini로 관리)

## 에이전트 활용 패턴

| 작업 | 담당 | 명령 예 |
|---|---|---|
| 보드/프레임워크 조사 | oracle | 최신 보드 지원 현황, 핀맵 |
| 펌웨어 구현 | forge | 소스 작성 후 `pio run` |
| 단위 테스트 | probe | `pio test -e native` |
| 정적 점검 | warden | `pio check` |
| 플래시 (실기기) | **사람** | `pio run -t upload` — 승인 후 직접 |

## 규칙

- 빌드(`pio run`)·네이티브 테스트는 에이전트가 자유롭게 실행 가능.
- 실기기 플래시/시리얼 제어는 HITL 승인 대상 (하드웨어 손상 방지).
- 보드별 설정은 `pipelines/embedded/<프로젝트>/platformio.ini`로 격리.
