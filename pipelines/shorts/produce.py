"""쇼츠 에피소드 생산 오케스트레이션: 주제 → 스크립트 → TTS → 렌더링 → 보고.

비용 라우팅: 스크립트 초안은 Ollama(무료). 다듬기가 필요하면 HERMES(Claude)가
--script 로 수정본 JSON을 넘겨 재생산한다. 업로드는 이 모듈에 없다 —
외부 게시는 반드시 HITL 승인(bus add --approve) 후 별도 단계로 실행한다.

사용:
    python -m pipelines.shorts.produce "아이폰 숨은 기능 3가지"
    python -m pipelines.shorts.produce "주제" --script refined.json   # 수정본으로 재렌더
    python -m pipelines.shorts.produce "주제" --notify                # 완료 시 Discord 보고
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from hermes.config import SHORTS_DIR
from pipelines.shorts import bgm as bgm_mod
from pipelines.shorts import render as render_mod
from pipelines.shorts import script_gen, tts


def _slug(topic: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", topic).strip("-")
    return s[:40] or "episode"


def produce(topic: str, script_file: str | None = None, notify: bool = False,
            bgm: str | None = None) -> dict:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ep_dir = SHORTS_DIR / f"{stamp}-{_slug(topic)}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    # 1) 스크립트 (초안=Ollama, 수정본이 있으면 그것을 사용)
    if script_file:
        script = json.loads(Path(script_file).read_text(encoding="utf-8"))
        print(f"▸ 스크립트: 수정본 사용 ({script_file})")
    else:
        print("▸ 스크립트 초안 생성 (Ollama)…")
        script = script_gen.generate(topic)
    (ep_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  제목: {script['title']} / 문장 {len(script_gen.sentences(script))}개")

    # 2) TTS + 자막
    print("▸ TTS 합성 (edge-tts)…")
    manifest = tts.synthesize(script_gen.sentences(script), ep_dir)
    print(f"  오디오 {manifest['duration']:.1f}초")

    # 3) 렌더링
    print("▸ 렌더링 (FFmpeg)…")
    out = render_mod.render(ep_dir)
    size_mb = out.stat().st_size / 1e6
    print(f"  완료: {out} ({size_mb:.1f}MB)")

    result = {"episode_dir": str(ep_dir), "video": str(out),
              "title": script["title"], "duration": round(manifest["duration"], 1)}

    # 4) BGM 합성 (선택)
    if bgm:
        bgm_path, credits = bgm_mod.resolve_track(bgm)
        mixed = ep_dir / "final_bgm.mp4"
        print(f"▸ BGM 합성 ({bgm_path.name})…")
        out = bgm_mod.mix(out, bgm_path, mixed)
        result["video"] = str(out)
        result["bgm"] = {"file": bgm_path.name, "credits": credits}
        print(f"  완료: {out}")

    (ep_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) 보고 (단방향 webhook — 승인 아님. 업로드는 별도 HITL)
    if notify:
        from channel.notify import send
        send(f"🎬 쇼츠 렌더링 완료\n제목: {script['title']}\n"
             f"길이: {result['duration']}초\n파일: {out}",
             title="shorts", level="ok")
    return result


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.produce")
    p.add_argument("topic")
    p.add_argument("--script", default=None, help="다듬은 스크립트 JSON 경로")
    p.add_argument("--notify", action="store_true", help="완료 시 Discord 알림")
    p.add_argument("--bgm", default=None,
                   help="assets/bgm 파일명 또는 random. 생략 시 기존 무BGM 경로")
    args = p.parse_args()
    try:
        result = produce(args.topic, args.script, args.notify, args.bgm)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[produce] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
