"""Gmail API 인증 공통 모듈.

mail_service(봇 내부 !mail 커맨드)와 mail_server(MCP 서버, 별도 프로세스)가
동일한 토큰 로드·갱신 로직을 공유한다. 토큰 갱신 실패(네트워크 오류,
refresh_token 만료)를 명확한 RuntimeError로 변환해 호출부가 크래시 없이
사용자에게 안내할 수 있게 한다.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GMAIL_TOKEN_PATH = PROJECT_ROOT / "data" / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def build_gmail_service(credentials_path: str):
    """토큰을 로드(필요 시 갱신)해 Gmail API service 객체를 반환한다."""
    if not GMAIL_TOKEN_PATH.exists():
        raise RuntimeError(
            "Gmail 토큰이 없습니다. venv/bin/python3 scripts/gmail_auth.py 를 먼저 실행하세요."
        )

    token_data = json.loads(GMAIL_TOKEN_PATH.read_text())
    cred_data = json.loads(Path(credentials_path).read_text())
    client_info = cred_data.get("installed") or cred_data.get("web", {})

    expiry = None
    expiry_str = token_data.get("expiry")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
        except ValueError:
            logger.warning("[Gmail] 토큰 expiry 형식 오류(%s) — 즉시 갱신 시도", expiry_str)

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_info["client_id"],
        client_secret=client_info["client_secret"],
        scopes=GMAIL_SCOPES,
        expiry=expiry,
    )
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:
            raise RuntimeError(
                f"Gmail 토큰 갱신 실패({e}). refresh_token이 만료되었으면 "
                "venv/bin/python3 scripts/gmail_auth.py 를 다시 실행하세요."
            ) from e
        tmp = GMAIL_TOKEN_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }))
        tmp.replace(GMAIL_TOKEN_PATH)
        logger.info("[Gmail] access_token 갱신 완료")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)
