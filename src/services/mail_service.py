import base64
import json
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

GMAIL_TOKEN_PATH = Path("data/gmail_token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class MailService:
    """Gmail API를 통해 메일을 발송한다."""

    def __init__(self, credentials_path: str) -> None:
        self._credentials_path = credentials_path
        self._service = None

    def is_ready(self) -> bool:
        return GMAIL_TOKEN_PATH.exists()

    def _get_service(self):
        if self._service:
            return self._service

        if not GMAIL_TOKEN_PATH.exists():
            raise RuntimeError(
                "Gmail 토큰이 없습니다. "
                "venv/bin/python3 scripts/gmail_auth.py 를 먼저 실행하세요."
            )

        token_data = json.loads(GMAIL_TOKEN_PATH.read_text())
        cred_data = json.loads(Path(self._credentials_path).read_text())
        client_info = cred_data.get("installed") or cred_data.get("web", {})

        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=GMAIL_SCOPES,
        )
        if not creds.valid:
            creds.refresh(Request())
            GMAIL_TOKEN_PATH.write_text(json.dumps({
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
            }))
            logger.info("[메일] access_token 갱신 완료")

        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def send(self, to: str, subject: str, body: str) -> None:
        service = self._get_service()

        msg = MIMEMultipart()
        msg["To"] = to
        msg["From"] = "me"
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info("[메일] 전송 완료: %s → %s", subject[:50], to)
