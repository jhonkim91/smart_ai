"""YouTube 업로드용 OAuth 인증.

최초 1회 브라우저 인증으로 refresh token을 받아 data/youtube_token.json에 저장한다.
업로드 scope만 요청해 권한을 최소화한다.

사용:
    python -m pipelines.shorts.auth_youtube
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hermes.config import DATA_DIR

SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)
CLIENT_SECRET_PATH = DATA_DIR / "client_secret.json"
TOKEN_PATH = DATA_DIR / "youtube_token.json"


def get_credentials(
    client_secret_path: Path = CLIENT_SECRET_PATH,
    token_path: Path = TOKEN_PATH,
):
    """저장된 credential을 읽고, 만료 시 refresh하며, 없으면 브라우저 인증을 수행한다."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not client_secret_path.exists():
            raise FileNotFoundError(
                f"{client_secret_path} 없음. vault/runbooks/youtube-oauth.md 절차를 먼저 수행하세요."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.auth_youtube")
    p.parse_args()
    try:
        get_credentials()
        print(f"ok: {TOKEN_PATH}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[auth_youtube] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
