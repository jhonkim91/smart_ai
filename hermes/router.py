"""비용 라우터: 작업을 어디로 보낼지 결정한다.

원칙
  - 초안 / 요약 / 분류 / 번역 / 태깅 등 반복적이고 품질 허용폭이 큰 작업 -> ollama (무료)
  - 코드 작성 / 설계 / 리뷰 / 디버깅 등 정확성이 중요한 작업 -> claude (유료, 서브에이전트)
  - 애매하면 ollama 초안 -> claude 다듬기 2단계 (kind="draft_then_refine")

Hermes(Claude Code 세션)는 작업을 받으면 먼저 이 라우터로 분류한 뒤,
ollama면 `python -m hermes.ollama_worker ...`를 Bash로 실행하고,
claude면 해당 서브에이전트(forge, atlas 등)에 위임한다.
"""

OLLAMA_KINDS = {
    "draft",       # 초안 작성 (쇼츠 스크립트 등)
    "summary",     # 요약 (로그, 기사, 회의)
    "classify",    # 분류 / 태깅
    "translate",   # 번역
    "title",       # 제목 / 해시태그 후보 생성
}

CLAUDE_KINDS = {
    "code": "forge",        # 구현
    "design": "atlas",      # 설계
    "review": "warden",     # 리뷰 / 보안
    "test": "probe",        # 테스트
    "research": "oracle",   # 리서치
    "docs": "scribe",       # 문서화 / vault 기록
    "analysis": "augur",    # 데이터 / 백테스트 분석
    "report": "herald",     # Discord 보고문 작성
}

# 키워드 휴리스틱 (kind 미지정 시 보조 판단)
_CHEAP_HINTS = ("요약", "초안", "분류", "번역", "제목", "태그", "draft", "summarize")


def route(kind: str = "general", text: str = "") -> dict:
    """{"target": "ollama"|"claude", "agent": 서브에이전트명|None} 반환."""
    if kind in OLLAMA_KINDS:
        return {"target": "ollama", "agent": None}
    if kind in CLAUDE_KINDS:
        return {"target": "claude", "agent": CLAUDE_KINDS[kind]}
    lowered = text.lower()
    if any(h in lowered for h in _CHEAP_HINTS):
        return {"target": "ollama", "agent": None}
    # 기본값: 판단이 필요한 작업은 Claude로 (안전한 쪽)
    return {"target": "claude", "agent": "forge"}


if __name__ == "__main__":
    import json
    import sys

    kind = sys.argv[1] if len(sys.argv) > 1 else "general"
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(route(kind, text), ensure_ascii=False))
