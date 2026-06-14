"""쇼츠 파이프라인 공유 유틸."""
import json
import re


def extract_json(text: str) -> dict:
    """모델 출력에서 첫 JSON 객체를 안전하게 추출."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"JSON 없음: {text[:200]}")
    return json.loads(m.group(0))
