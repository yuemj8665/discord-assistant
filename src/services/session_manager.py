import logging
from typing import Optional

from src.core.config import config
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class SessionManager:
    """채널 ID에 따라 적절한 LLMService 인스턴스를 반환한다."""

    def __init__(self) -> None:
        self._infra_llm = LLMService(role="infra")
        self._news_llm = LLMService(role="news")
        self._services: dict[int, LLMService] = {
            config.GENERAL_CHANNEL_ID: LLMService(role="general"),
            config.CALENDAR_CHANNEL_ID: LLMService(role="calendar"),
            config.NEWS_CHANNEL_ID: self._news_llm,
        }
        for channel_id, service in self._services.items():
            logger.info("[SessionManager] 채널 %d → 역할 '%s' 등록", channel_id, service._role)

    def get(self, channel_id: int) -> Optional[LLMService]:
        """채널 ID에 맞는 LLMService 반환. 등록되지 않은 채널은 None."""
        return self._services.get(channel_id)

    def get_by_role(self, role: str) -> Optional[LLMService]:
        """역할명으로 LLMService 반환."""
        if role == "infra":
            return self._infra_llm
        if role == "news":
            return self._news_llm
        for service in self._services.values():
            if service._role == role:
                return service
        return None

    def reset(self, channel_id: int) -> bool:
        """해당 채널의 세션만 초기화. 성공 여부 반환."""
        service = self._services.get(channel_id)
        if service:
            service.reset_session()
            return True
        return False
