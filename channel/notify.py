"""Discord webhook 단방향 알림. 봇 프로세스 없이도 어디서든 호출 가능.

사용:
    python -m channel.notify "✅ 쇼츠 렌더링 완료: ep042.mp4"
    python -m channel.notify "❌ 백테스트 실패" --title "trading" --level error

n8n에서는 HTTP Request 노드로 같은 webhook URL에 직접 POST해도 된다.
"""
import argparse
import datetime
import json
import sys

import requests

from hermes.config import DATA_DIR, DISCORD_WEBHOOK_URL

LEVEL_COLOR = {"info": 0x5865F2, "ok": 0x57F287, "warn": 0xFEE75C, "error": 0xED4245}


def _write_local_log(message: str, title: str = "", level: str = "info") -> None:
    """Discord webhook 미설정 시 알림을 로컬 로그에 남긴다."""
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "title": title,
        "message": message,
        "delivery": "local_log",
    }
    with (log_dir / "notifications.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def send(message: str, title: str = "", level: str = "info") -> bool:
    if not DISCORD_WEBHOOK_URL:
        _write_local_log(message, title, level)
        print("[notify] DISCORD_WEBHOOK_URL 미설정 — data/logs/notifications.log에 기록", file=sys.stderr)
        print(f"[{level}] {title}: {message}" if title else f"[{level}] {message}")
        return False
    embed: dict = {
        "description": message[:3900],
        "color": LEVEL_COLOR.get(level, LEVEL_COLOR["info"]),
    }
    if title:
        embed["title"] = title
    payload: dict = {"embeds": [embed]}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    r.raise_for_status()
    return True


def main() -> int:
    p = argparse.ArgumentParser(prog="channel.notify")
    p.add_argument("message")
    p.add_argument("--title", default="")
    p.add_argument("--level", default="info", choices=sorted(LEVEL_COLOR.keys()))
    args = p.parse_args()
    try:
        send(args.message, args.title, args.level)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[notify] 발송 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
