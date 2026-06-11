"""쇼츠 스크립트 생성기 (1단계 초안: Ollama 무료).

주제를 받아 60~75초 분량의 한국어 쇼츠 스크립트를 만든다.
출력은 JSON(제목, 훅, 본문 문장 리스트, 아웃트로)으로 강제해 후속 단계(TTS/자막)가
문장 단위로 소비할 수 있게 한다.

사용:
    python -m pipelines.shorts.script_gen "아이폰 숨은 기능 3가지"
"""
import argparse
import json
import re
import sys

from hermes.config import OLLAMA_HOST, OLLAMA_MODEL

SYSTEM = (
    "너는 유튜브 쇼츠 전문 작가다. 주어진 주제로 60~75초 분량(공백 포함 350~450자)의 "
    "한국어 쇼츠 대본을 작성한다.\n"
    "반드시 아래 JSON 형식으로만 출력한다. 설명/마크다운 금지.\n"
    '{"title": "영상 제목(25자 이내)", "hook": "첫 3초 훅 한 문장", '
    '"lines": ["본문 문장1", "본문 문장2", "..."], "outro": "마무리+구독 유도 한 문장"}\n'
    "규칙: 문장은 짧게(20자 내외), lines는 6~10개, 과장·허위 금지, 구어체."
)


def _extract_json(text: str) -> dict:
    """모델 출력에서 첫 JSON 객체를 안전하게 추출."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"JSON 없음: {text[:200]}")
    return json.loads(m.group(0))


def generate(topic: str) -> dict:
    import ollama

    client = ollama.Client(host=OLLAMA_HOST)
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"주제: {topic}"},
        ],
        options={"temperature": 0.7},
    )
    script = _extract_json(resp["message"]["content"])
    for key in ("title", "hook", "lines", "outro"):
        if not script.get(key):
            raise ValueError(f"스크립트 필드 누락: {key}")
    return script


def sentences(script: dict) -> list[str]:
    """TTS/자막용 문장 시퀀스 (훅 → 본문 → 아웃트로)."""
    return [script["hook"], *script["lines"], script["outro"]]


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.script_gen")
    p.add_argument("topic")
    args = p.parse_args()
    try:
        print(json.dumps(generate(args.topic), ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[script_gen] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
