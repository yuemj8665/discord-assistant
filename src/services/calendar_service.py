import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from src.core.config import config
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

MCP_TOKEN_PATH = Path.home() / ".config" / "google-calendar-mcp" / "tokens.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarService:
    """Google Calendar API 직접 조회 서비스."""

    def __init__(self) -> None:
        self._service = self._build_service()

    def _build_service(self):
        token_data = json.loads(MCP_TOKEN_PATH.read_text())["normal"]
        cred_data = json.loads(Path(config.GOOGLE_OAUTH_CREDENTIALS).read_text())
        client_info = cred_data.get("installed") or cred_data.get("web", {})
        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=SCOPES,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def get_upcoming_events(self, minutes: int = 30) -> list[dict]:
        """지금부터 minutes분 이내의 일정을 반환한다."""
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(minutes=minutes)

        result = self._service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        logger.debug("[캘린더] %d분 이내 일정 %d건 조회", minutes, len(events))
        return events
