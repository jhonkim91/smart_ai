"""Ollama 로컬 워커: 초안 / 요약 / 분류를 무료로 처리.

Hermes(Claude Code)가 Bash로 호출하는 CLI:
    python -m hermes.ollama_worker draft "주제: 아이폰 숨은 기능 3가지 쇼츠 스크립트"
    python -m hermes.ollama_worker summary "<긴 텍스트>"
    python -m hermes.ollama_worker classify "<텍스트>" --labels "버그,기능요청,질문"
    echo "<긴 텍스트>" | python -m hermes.ollama_worker summary -
"""
import argparse
import sys

from hermes.config import OLLAMA_HOST, OLLAMA_MODEL

SYSTEM_PROMPTS = {
    "draft": (
        "너는 한국어 콘텐츠 초안 작성자다. 요청받은 주제로 간결하고 구조적인 "
        "초안을 작성한다. 과장 없이, 바로 다듬어 쓸 수 있는 품질로."
    ),
    "summary": (
        "너는 요약 전문가다. 입력 텍스트의 핵심을 한국어 불릿 5개 이내로 요약한다. "
        "수치와 고유명사는 보존한다."
    ),
    "classify": (
        "너는 분류기다. 입력 텍스트를 주어진 라벨 중 정확히 하나로 분류하고, "
        "라벨명만 출력한다. 설명을 덧붙이지 않는다."
    ),
    "title": (
        "너는 카피라이터다. 입력 내용에 어울리는 한국어 제목 후보 5개와 "
        "해시태그 5개를 제안한다."
    ),
    "translate": "너는 번역가다. 입력을 자연스러운 한국어로 번역한다.",
}


def run(kind: str, text: str, labels: str = "") -> str:
    import ollama  # 지연 임포트: ollama 미설치 환경에서도 다른 모듈 사용 가능

    client = ollama.Client(host=OLLAMA_HOST)
    system = SYSTEM_PROMPTS.get(kind, SYSTEM_PROMPTS["summary"])
    user = text if not labels else f"라벨 후보: {labels}\n\n텍스트:\n{text}"
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp["message"]["content"].strip()


def main() -> int:
    p = argparse.ArgumentParser(prog="hermes.ollama_worker")
    p.add_argument("kind", choices=sorted(SYSTEM_PROMPTS.keys()))
    p.add_argument("text", help="입력 텍스트. '-' 이면 stdin에서 읽음")
    p.add_argument("--labels", default="", help="classify용 라벨 목록 (쉼표 구분)")
    args = p.parse_args()

    text = sys.stdin.read() if args.text == "-" else args.text
    try:
        print(run(args.kind, text, args.labels))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[ollama_worker] 실패: {e}", file=sys.stderr)
        print("Ollama가 실행 중인지 확인: /Applications/Ollama.app 실행 또는 ollama serve",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
