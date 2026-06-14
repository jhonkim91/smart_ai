"""반전 썰 스토리 생성기 (댕댕스토리 스타일, 2단계: Ollama 무료).

주제를 받아 반전 있는 실화풍 썰 스토리(제목 + 자막 문장 8~12개)를 만든다.
텍스트는 Ollama에 맡기되, 장면 연출(scene dict)은 파이썬 휴리스틱으로
결정론적으로 입혀 렌더 단계(cartoon.py)가 흔들림 없이 소비할 수 있게 한다.

scene dict 형식 (cartoon.py 입력):
    {"bg": "sky",                          # 배경 프리셋 이름
     "bg_colors": ["#AEE3FF", "#F3FBFF"],  # 세로 그라디언트 (위, 아래)
     "characters": [
         {"color": "#7CE577",      # 젤리 몸통 단색
          "x": 0.3,                # 장면 카드 안 가로 위치 비율(0~1)
          "expression": "smile",   # smile|sad|shock|angry|neutral
          "flip": False,           # True면 왼쪽을 바라봄
          "prop": "none"},         # hat|helmet|bag|none
     ]}

사용:
    python -m pipelines.shorts.story_gen "엘리베이터에 갇힌 날 생긴 일"
"""
import argparse
import json
import sys

from hermes.config import OLLAMA_HOST, OLLAMA_MODEL
from pipelines.shorts._utils import extract_json as _extract_json

SYSTEM = (
    "너는 유튜브 썰 쇼츠 전문 작가다. 주어진 주제로 실화 느낌의 반전 스토리를 쓴다.\n"
    "반드시 아래 JSON 형식으로만 출력한다. 설명/마크다운 금지.\n"
    '{"title": "제목(24자 이내, 호기심 자극형)", '
    '"scenes": [{"text": "자막 문장(40자 이내)", '
    '"highlight_red": "강조 단어(없으면 빈 문자열)", '
    '"highlight_yellow": "강조 단어(없으면 빈 문자열)"}]}\n'
    "규칙: scenes는 8~12개, 문장은 짧은 구어체(40자 이내), 1인칭 썰 톤, "
    "highlight 단어는 반드시 그 문장 안에 있는 단어만, "
    "마지막 1~2 문장은 반전 + 여운으로 끝낸다. 과장은 좋지만 혐오/실명 금지."
)

# --- 고정 캐스트 (에피소드 내내 색 유지) ---
CAST_MAIN = "#7CE577"    # 주인공 민트
CAST_PARTNER = "#F48FB1"  # 상대 핑크
CAST_EXTRA = "#81D4FA"   # 조연 하늘

# --- 배경 프리셋: 세로 그라디언트 (위, 아래) ---
BG_PRESETS = {
    "sky": ("#AEE3FF", "#F3FBFF"),
    "sunset": ("#FFD9A0", "#FFF3E0"),
    "night": ("#3E4A7B", "#1E2440"),
    "office": ("#DDE7F2", "#F7FAFD"),
    "room": ("#FFE9C7", "#FFF8EC"),
    "park": ("#C9F0C4", "#F0FFF0"),
    "alert": ("#FFC4C4", "#FFEDED"),
}

# 장면 텍스트/주제 → 배경 키워드 매핑 (앞에 올수록 우선)
_BG_KEYWORDS = [
    ("sky", ("하늘", "비행", "낙하", "공중", "점프", "구름", "번지", "스카이")),
    ("night", ("밤", "잠", "꿈", "새벽", "야간", "어둠", "캄캄")),
    ("office", ("회사", "직장", "상사", "출근", "사무", "면접", "알바", "업무")),
    ("park", ("공원", "숲", "산책", "나무", "캠핑", "산에")),
    ("alert", ("사고", "위험", "비상", "경보", "사이렌", "갇혔", "갇힌")),
]

# 텍스트 감성 키워드 → 표정 (앞에 올수록 우선)
_EXPR_KEYWORDS = [
    ("shock", ("놀라", "충격", "갑자기", "깜짝", "헐", "황당", "어이없", "뭐지", "?!", "!")),
    ("sad", ("슬프", "눈물", "죽", "울었", "울고", "아프", "무서", "두려", "절망", "포기", "혼자")),
    ("angry", ("화가", "화났", "화를", "분노", "빡", "짜증", "소리쳤", "소리 질", "욕", "열받")),
]

# 텍스트/주제 → 소품 매핑
_PROP_KEYWORDS = [
    ("bag", ("배낭", "가방", "낙하산", "여행", "등산", "비행")),
    ("helmet", ("군대", "군인", "헬멧", "훈련", "공사", "오토바이", "전쟁")),
    ("hat", ("모자", "신사", "마술", "중절모", "멋쟁이")),
]

_DEFAULT_ROTATION = ["room", "office", "sky", "sunset", "park", "night"]



def _match_keyword(text: str, table: list[tuple[str, tuple[str, ...]]]) -> str | None:
    """키워드 테이블에서 첫 매칭 라벨 반환 (없으면 None)."""
    for label, words in table:
        if any(w in text for w in words):
            return label
    return None


def _build_rotation(topic: str) -> list[str]:
    """주제 키워드 기반 배경 로테이션. 테마가 있으면 그 배경 비중을 높인다."""
    theme = _match_keyword(topic, _BG_KEYWORDS)
    if not theme:
        return list(_DEFAULT_ROTATION)
    fillers = [b for b in ("room", "office", "sunset", "park") if b != theme]
    return [theme, fillers[0], theme, fillers[1], theme, fillers[2]]


def _expression(text: str, i: int, n: int) -> str:
    """텍스트 감성 키워드 매칭. 기본 smile, 중반 이후엔 neutral을 섞는다."""
    matched = _match_keyword(text, _EXPR_KEYWORDS)
    if matched:
        return matched
    if i >= n // 2 and i % 2 == 1:
        return "neutral"
    return "smile"


def _scene_dict(text: str, i: int, n: int, rotation: list[str],
                topic_prop: str, use_extra: bool) -> dict:
    """i번째 장면의 연출(scene dict)을 결정론적으로 구성."""
    bg = _match_keyword(text, _BG_KEYWORDS) or rotation[i % len(rotation)]
    expr = _expression(text, i, n)
    prop = _match_keyword(text, _PROP_KEYWORDS) or topic_prop

    # 상대 표정: 감정 장면이면 같이 반응, 평상시엔 부드럽게
    if expr in ("shock", "sad"):
        partner_expr = expr
    elif expr == "angry":
        partner_expr = "shock"
    else:
        partner_expr = "neutral" if i >= n // 2 else "smile"

    if i % 3 == 0:  # 솔로 컷: 주인공 가운데
        characters = [{"color": CAST_MAIN, "x": 0.5, "expression": expr,
                       "flip": False, "prop": prop}]
    else:  # 2인 컷: 좌우 교대 + 마주보기(flip)
        partner_color = CAST_EXTRA if (use_extra and i % 4 == 2) else CAST_PARTNER
        if i % 2 == 0:
            characters = [
                {"color": CAST_MAIN, "x": 0.3, "expression": expr,
                 "flip": False, "prop": prop},
                {"color": partner_color, "x": 0.7, "expression": partner_expr,
                 "flip": True, "prop": "none"},
            ]
        else:
            characters = [
                {"color": partner_color, "x": 0.3, "expression": partner_expr,
                 "flip": False, "prop": "none"},
                {"color": CAST_MAIN, "x": 0.7, "expression": expr,
                 "flip": True, "prop": prop},
            ]

    return {"bg": bg, "bg_colors": list(BG_PRESETS[bg]), "characters": characters}


def _highlights(text: str, raw: dict) -> dict:
    """highlight_red/yellow → highlights dict. 실제 text에 없는 단어는 무시."""
    out: dict[str, str] = {}
    for key, color in (("highlight_yellow", "yellow"), ("highlight_red", "red")):
        word = str(raw.get(key) or "").strip()
        if word and word in text:
            out[word] = color  # 같은 단어면 red가 우선(나중에 덮어씀)
    return out


def _request_story(topic: str) -> dict:
    """Ollama로 스토리 텍스트 생성 + 필드 검증."""
    import ollama

    client = ollama.Client(host=OLLAMA_HOST)
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"주제: {topic}"},
        ],
        options={"temperature": 0.8},
    )
    story = _extract_json(resp["message"]["content"])
    if not story.get("title"):
        raise ValueError("스토리 필드 누락: title")
    scenes = [s for s in story.get("scenes") or []
              if isinstance(s, dict) and str(s.get("text") or "").strip()]
    if len(scenes) < 6:
        raise ValueError(f"장면 수 부족: {len(scenes)}개 (최소 6개)")
    story["scenes"] = scenes[:12]
    return story


def generate_story(topic: str) -> dict:
    """반전 있는 썰 스토리 생성. 반환:
    {"title": "...(24자 이내, 호기심 자극형)",
     "brand": "댕댕스토리", "brand_sub": "AI 실화 썰",
     "scenes": [{"text": "자막 문장(40자 이내)",
                 "highlights": {"단어": "red"|"yellow"},
                 "scene": {cartoon.py의 scene dict}}, ...]}  # 8~12개
    """
    last_err: Exception | None = None
    for _ in range(2):  # 로컬 모델 JSON 흔들림 대비 1회 재시도
        try:
            story = _request_story(topic)
            break
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    else:
        raise ValueError(f"스토리 생성 실패: {last_err}")

    raw_scenes = story["scenes"]
    n = len(raw_scenes)
    rotation = _build_rotation(topic)
    topic_prop = _match_keyword(topic, _PROP_KEYWORDS) or "none"
    use_extra = n >= 9  # 장면이 많으면 조연(하늘)까지 3인 캐스트

    scenes = []
    for i, raw in enumerate(raw_scenes):
        text = str(raw["text"]).strip()[:40]
        scenes.append({
            "text": text,
            "highlights": _highlights(text, raw),
            "scene": _scene_dict(text, i, n, rotation, topic_prop, use_extra),
        })

    return {
        "title": str(story["title"]).strip()[:24],
        "brand": "댕댕스토리",
        "brand_sub": "AI 실화 썰",
        "scenes": scenes,
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.story_gen")
    p.add_argument("topic")
    args = p.parse_args()
    try:
        print(json.dumps(generate_story(args.topic), ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[story_gen] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
