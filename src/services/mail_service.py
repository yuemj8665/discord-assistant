import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.services.gmail_client import GMAIL_TOKEN_PATH, build_gmail_service

logger = logging.getLogger(__name__)


class MailService:
    """Gmail API를 통해 메일을 발송한다."""

    def __init__(self, credentials_path: str) -> None:
        self._credentials_path = credentials_path
        self._service = None

    def is_ready(self) -> bool:
        return GMAIL_TOKEN_PATH.exists()

    def _get_service(self):
        if self._service is None:
            self._service = build_gmail_service(self._credentials_path)
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
