"""쇼츠 6단계: YouTube 업로드.

CLI는 반드시 HITL 승인 요청 -> 승인 대기 -> 승인된 경우에만 insert 실행 순서로 동작한다.
실제 공개 전환은 코드가 아니라 사람이 YouTube Studio에서 수행한다.

사용:
    python -m pipelines.shorts.upload <episode_dir>
    python -m pipelines.shorts.upload <episode_dir> --privacy private
    python -m pipelines.shorts.upload <episode_dir> --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from hermes import bus

ALLOWED_PRIVACY = {"private", "unlisted"}
DEFAULT_CATEGORY_ID = "22"  # People & Blogs
TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 5000


class DuplicateUploadError(RuntimeError):
    """동일 episode_dir가 이미 업로드됐거나 업로드 예약 중이다."""


class UploadApprovalError(RuntimeError):
    """승인되지 않은 업로드 실행 시도."""


def _canonical_episode_dir(episode_dir: str | Path) -> str:
    return str(Path(episode_dir).expanduser().resolve())


def validate_privacy(privacy: str) -> str:
    privacy = privacy.strip().lower()
    if privacy == "public":
        # 2020-07-28 이후 생성된 미인증 API 프로젝트는 public 요청도 private으로 잠긴다.
        # 공개는 사람이 YouTube Studio에서 최종 전환한다.
        raise ValueError("privacy='public'은 금지됩니다. API 업로드는 private/unlisted만 허용합니다.")
    if privacy not in ALLOWED_PRIVACY:
        raise ValueError("privacy는 private 또는 unlisted만 허용됩니다.")
    return privacy


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _episode_files(episode_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _read_json(episode_dir / "result.json")
    script = _read_json(episode_dir / "script.json")
    if not script:
        script = _read_json(episode_dir / "story.json")
    if not result:
        raise FileNotFoundError(f"{episode_dir / 'result.json'} 없음")
    if not script:
        raise FileNotFoundError(f"{episode_dir / 'script.json'} 또는 story.json 없음")
    return result, script


def _video_path(episode_dir: Path, result: dict[str, Any]) -> Path:
    raw = result.get("video") or "final.mp4"
    video = Path(raw)
    if not video.is_absolute():
        video = episode_dir / video
    if not video.exists():
        raise FileNotFoundError(f"업로드할 영상 파일 없음: {video}")
    return video


def _title(result: dict[str, Any], script: dict[str, Any]) -> str:
    title = str(result.get("title") or script.get("title") or "Untitled Short").strip()
    return title[:TITLE_LIMIT]


def _text_lines(script: dict[str, Any]) -> list[str]:
    if isinstance(script.get("lines"), list):
        return [str(x).strip() for x in script["lines"] if str(x).strip()]
    if isinstance(script.get("scenes"), list):
        lines = []
        for scene in script["scenes"]:
            if isinstance(scene, dict):
                text = scene.get("text") or scene.get("subtitle")
                if text:
                    lines.append(str(text).strip())
        return lines
    return []


def _bgm_attribution(result: dict[str, Any], script: dict[str, Any]) -> str:
    flat_keys = (
        "bgm_attribution",
        "bgm_source",
        "music_attribution",
        "music_source",
    )
    for source in (result, script):
        for key in flat_keys:
            value = source.get(key)
            if value:
                return str(value).strip()

        bgm = source.get("bgm") or source.get("music")
        if isinstance(bgm, dict):
            credits = bgm.get("credits")
            if credits:
                return str(credits).strip()
            parts = []
            for key in ("title", "artist", "source", "license", "url"):
                value = bgm.get(key)
                if value:
                    parts.append(str(value).strip())
            if parts:
                return " / ".join(parts)
        elif bgm:
            return str(bgm).strip()
    return ""


def build_description(result: dict[str, Any], script: dict[str, Any]) -> str:
    parts: list[str] = []
    explicit = result.get("description") or script.get("description")
    if explicit:
        parts.append(str(explicit).strip())
    else:
        hook = script.get("hook")
        if hook:
            parts.append(str(hook).strip())
        lines = _text_lines(script)
        if lines:
            parts.append("\n".join(lines))
        outro = script.get("outro")
        if outro:
            parts.append(str(outro).strip())

    bgm = _bgm_attribution(result, script)
    if bgm:
        parts.append(f"BGM 출처: {bgm}")

    description = "\n\n".join(p for p in parts if p)
    return description[:DESCRIPTION_LIMIT]


def build_video_resource(
    episode_dir: str | Path,
    privacy: str = "unlisted",
) -> tuple[dict[str, Any], Path, str, str]:
    privacy = validate_privacy(privacy)
    ep_dir = Path(episode_dir).expanduser().resolve()
    result, script = _episode_files(ep_dir)
    video = _video_path(ep_dir, result)
    title = _title(result, script)
    body = {
        "snippet": {
            "title": title,
            "description": build_description(result, script),
            "categoryId": str(result.get("category_id") or script.get("category_id") or DEFAULT_CATEGORY_ID),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    tags = result.get("tags") or script.get("tags")
    if isinstance(tags, list) and tags:
        body["snippet"]["tags"] = [str(tag) for tag in tags]
    return body, video, title, str(ep_dir)


def request_upload_approval(episode_dir: str | Path, privacy: str) -> int:
    body, video, title, ep_dir = build_video_resource(episode_dir, privacy)
    request_body = (
        f"YouTube Shorts 업로드 승인 요청\n"
        f"- 제목: {title}\n"
        f"- privacy: {body['status']['privacyStatus']}\n"
        f"- episode_dir: {ep_dir}\n"
        f"- video: {video}\n"
        f"- 공개 전환: API 금지, YouTube Studio에서 사람이 수행"
    )
    return bus.add_task(
        title=f"YouTube 업로드 승인 · {title}",
        body=request_body,
        kind="youtube_upload",
        needs_approval=True,
    )


def _approval_allows_execution(task_id: int, episode_dir: str, privacy: str) -> bool:
    task = bus.get_task(task_id)
    if not task:
        return False
    if task.get("kind") != "youtube_upload" or task.get("status") != "approved":
        return False
    body = task.get("body") or ""
    return episode_dir in body and f"privacy: {privacy}" in body


def _build_youtube_service():
    from googleapiclient.discovery import build

    from pipelines.shorts.auth_youtube import get_credentials

    return build("youtube", "v3", credentials=get_credentials())


def _execute_insert(youtube, body: dict[str, Any], video: Path) -> dict[str, Any]:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response


def execute_approved_upload(
    episode_dir: str | Path,
    *,
    privacy: str = "unlisted",
    approval_task_id: int,
    youtube_service=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    body, video, title, ep_dir = build_video_resource(episode_dir, privacy)
    privacy = body["status"]["privacyStatus"]

    if not _approval_allows_execution(approval_task_id, ep_dir, privacy):
        raise UploadApprovalError("승인된 youtube_upload task가 아니므로 업로드를 실행하지 않습니다.")

    existing = bus.get_publish_history(ep_dir)
    if existing:
        raise DuplicateUploadError(f"이미 업로드됐거나 예약된 episode_dir입니다: {ep_dir}")

    if dry_run:
        return {
            "dry_run": True,
            "episode_dir": ep_dir,
            "video": str(video),
            "title": title,
            "privacy_status": privacy,
            "request_body": body,
        }

    if not bus.begin_publish(ep_dir, title, privacy):
        raise DuplicateUploadError(f"이미 업로드됐거나 예약된 episode_dir입니다: {ep_dir}")

    uploaded = False
    try:
        youtube = youtube_service or _build_youtube_service()
        response = _execute_insert(youtube, body, video)
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(f"YouTube 응답에 video id가 없습니다: {response}")
        uploaded = True
        bus.complete_publish(ep_dir, video_id)
        return {
            "episode_dir": ep_dir,
            "video_id": video_id,
            "title": title,
            "privacy_status": privacy,
        }
    except Exception:
        if not uploaded:
            bus.clear_publish_reservation(ep_dir)
        raise


def upload(
    episode_dir: str | Path,
    privacy: str = "unlisted",
    *,
    dry_run: bool = False,
    wait_timeout: int = 600,
    wait_interval: float = 3.0,
) -> dict[str, Any]:
    """HITL 승인 후에만 업로드를 실행하는 안전 오케스트레이터."""
    privacy = validate_privacy(privacy)
    ep_dir = _canonical_episode_dir(episode_dir)
    if bus.get_publish_history(ep_dir):
        raise DuplicateUploadError(f"이미 업로드됐거나 예약된 episode_dir입니다: {ep_dir}")

    task_id = request_upload_approval(ep_dir, privacy)
    decision = bus.wait_for_decision(task_id, timeout=wait_timeout, interval=wait_interval)
    if decision != "approved":
        raise UploadApprovalError(f"업로드 미실행: 승인 결과가 {decision}입니다.")

    return execute_approved_upload(
        ep_dir,
        privacy=privacy,
        approval_task_id=task_id,
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.upload")
    p.add_argument("episode_dir")
    p.add_argument("--privacy", default="unlisted",
                   help="private 또는 unlisted만 허용. public은 코드에서 차단")
    p.add_argument("--dry-run", action="store_true",
                   help="승인은 받되 YouTube insert는 호출하지 않고 요청 바디만 출력")
    p.add_argument("--timeout", type=int, default=600,
                   help="Discord 승인 대기 초")
    args = p.parse_args(argv)

    try:
        result = upload(
            args.episode_dir,
            privacy=args.privacy,
            dry_run=args.dry_run,
            wait_timeout=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[upload] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
