import os
import subprocess
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from src.core.config import config

KST = timezone(timedelta(hours=9))
_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("data/sessions")

ROLE_CONFIGS = {
    "general": {
        "system_prompt": (
            "당신은 명재의 개인 비서입니다. "
            "웹 검색 등 도구 사용 시 사전에 확인을 구하지 말고 즉시 실행하세요. "
            "모든 도구 사용 권한은 이미 허가되어 있습니다.\n\n"
            "세션 시작 시 반드시 data/sessions/general/memory.md를 읽어 명재에 대한 맥락을 파악하세요. "
            "오늘 날짜의 data/sessions/general/daily/YYYY-MM-DD.md 파일이 있으면 함께 읽어 이전 대화 흐름을 이어가세요."
        ),
        "mcp": False,
        "allowed_tools": "WebSearch,WebFetch",
    },
    "infra": {
        "system_prompt": (
            "당신은 명재의 홈서버 모니터링 전담 비서입니다. "
            "서버 상태 분석 요청이 오면 즉시 get_server_resources와 get_docker_containers 도구를 호출하여 데이터를 수집하세요. "
            "응답은 반드시 Discord 채팅에 최적화된 형식으로 작성하세요: "
            "표는 마크다운 테이블(|---|) 대신 코드블록(```) 안에 고정폭 텍스트로 작성하고, "
            "섹션 구분은 **굵은 글씨**와 이모지를 사용하세요. "
            "확인 없이 즉시 도구를 실행하며, 모든 도구 사용 권한은 이미 허가되어 있습니다."
        ),
        "mcp": True,
        "allowed_tools": "mcp__infra__get_server_resources,mcp__infra__get_docker_containers",
    },
    "news": {
        "system_prompt": (
            "당신은 명재의 IT 뉴스 큐레이터입니다. "
            "GeekNews, Hacker News, 요즘IT의 최신 뉴스 목록을 받으면 각 항목을 한국어로 간결하게 요약하세요. "
            "응답은 Discord 채팅에 최적화된 형식으로 작성하세요: "
            "사이트별로 섹션을 나누고, 각 뉴스는 **제목** + 한 줄 요약 + 링크 형식으로 작성하세요. "
            "이모지로 가독성을 높이고, 마크다운 테이블은 사용하지 마세요."
        ),
        "mcp": False,
        "allowed_tools": "WebFetch",
    },
    "calendar": {
        "system_prompt": (
            "당신은 명재의 일정 관리 전담 비서입니다. "
            "Google Calendar 일정 조회, 등록, 수정, 삭제 및 웹 검색을 즉시 실행하세요. "
            "확인 없이 바로 실행하며, 일정 관련 정보는 memory.md에 기억해두세요. "
            "모든 도구 사용 권한은 이미 허가되어 있습니다.\n\n"
            "일정 등록 시 내용에 따라 아래 캘린더 ID를 사용하세요:\n"
            f"- 업무 관련: {config.CALENDAR_ID_WORK}\n"
            f"- 운동 관련: {config.CALENDAR_ID_EXERCISE}\n"
            f"- 개인 관련: {config.CALENDAR_ID_PERSONAL}\n"
            f"- 분류 불명확: {config.CALENDAR_ID_DEFAULT}\n"
            "calendarId 파라미터에 위 ID를 반드시 지정하세요."
        ),
        "mcp": True,
        "allowed_tools": (
            "mcp__google-calendar__list-events,"
            "mcp__google-calendar__create-event,"
            "mcp__google-calendar__update-event,"
            "mcp__google-calendar__delete-event,"
            "mcp__google-calendar__get-current-time,"
            "mcp__google-calendar__list-calendars,"
            "WebSearch,"
            "WebFetch"
        ),
    },
}


class LLMService:
    """Claude CLI subprocess 래퍼. 역할별 세션을 유지하며 대화를 이어간다."""

    def __init__(self, role: str = "general") -> None:
        self._role = role
        self._session_file = SESSIONS_DIR / role / "session.json"
        self._memory_dir = str(SESSIONS_DIR / role)
        self._session_id: Optional[str] = self._load_session()
        if self._session_id:
            logger.info("[LLM:%s] 저장된 세션 복원: %s", self._role, self._session_id)

    def ask(self, message: str) -> str:
        cmd = self._build_command(message)
        logger.debug("[LLM:%s] Claude CLI 실행: %s", self._role, " ".join(cmd[:6]) + " ...")

        try:
            env = os.environ.copy()
            env["GOOGLE_OAUTH_CREDENTIALS"] = config.GOOGLE_OAUTH_CREDENTIALS
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except subprocess.TimeoutExpired:
            logger.error("[LLM:%s] 응답 시간 초과", self._role)
            raise RuntimeError("Claude CLI 응답 시간이 초과되었습니다.")
        except FileNotFoundError:
            logger.error("[LLM:%s] claude CLI를 찾을 수 없습니다.", self._role)
            raise RuntimeError("claude CLI가 설치되지 않았거나 PATH에 없습니다.")

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if self._session_id and "No conversation found" in stderr:
                logger.warning("[LLM:%s] 세션 만료. 새 세션으로 재시도", self._role)
                self._session_id = None
                return self.ask(message)
            logger.error("[LLM:%s] Claude CLI 오류: %s", self._role, stderr)
            raise RuntimeError(f"Claude CLI 오류: {stderr}")

        try:
            data = json.loads(result.stdout)
            response_text = data.get("result", "").strip()
            if self._session_id is None:
                self._session_id = data.get("session_id")
                logger.info("[LLM:%s] 세션 시작: %s", self._role, self._session_id)
            else:
                logger.info("[LLM:%s] 세션 유지: %s", self._role, self._session_id)
            self._save_session()
        except json.JSONDecodeError:
            response_text = result.stdout.strip()

        logger.info("[LLM:%s] 응답: %s", self._role, response_text[:200])
        return response_text

    def log_conversation(self, user_msg: str, assistant_msg: str) -> None:
        now = datetime.now(KST)
        daily_dir = SESSIONS_DIR / self._role / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / f"{now.strftime('%Y-%m-%d')}.md"

        if not daily_file.exists():
            daily_file.write_text(
                f"## {now.strftime('%Y-%m-%d')} ({_WEEKDAYS[now.weekday()]})\n\n",
                encoding="utf-8",
            )

        entry = (
            f"### [{now.strftime('%H:%M')}] 명재\n{user_msg}\n\n"
            f"### [{now.strftime('%H:%M')}] Claude\n{assistant_msg}\n\n"
        )
        with daily_file.open("a", encoding="utf-8") as f:
            f.write(entry)

    @property
    def daily_dir(self) -> Path:
        return SESSIONS_DIR / self._role / "daily"

    def reset_session(self) -> None:
        self._session_id = None
        self._session_file.unlink(missing_ok=True)
        logger.info("[LLM:%s] 세션 초기화됨", self._role)

    def _save_session(self) -> None:
        self._session_file.parent.mkdir(parents=True, exist_ok=True)
        self._session_file.write_text(json.dumps({"session_id": self._session_id}))

    def _load_session(self) -> Optional[str]:
        try:
            return json.loads(self._session_file.read_text()).get("session_id")
        except Exception:
            return None

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    def _build_command(self, message: str) -> list[str]:
        role_cfg = ROLE_CONFIGS.get(self._role, ROLE_CONFIGS["general"])
        cmd = [
            "claude", "-p", message,
            "--output-format", "json",
            "--system-prompt", role_cfg["system_prompt"],
            "--dangerously-skip-permissions",
        ]
        if self._session_id:
            cmd += ["--resume", self._session_id]
        for d in config.ALLOWED_DIRS:
            cmd += ["--add-dir", d.strip()]
        cmd += ["--add-dir", self._memory_dir]
        if role_cfg["mcp"]:
            cmd += ["--mcp-config", config.MCP_CONFIG_PATH]
        cmd += ["--allowedTools", role_cfg["allowed_tools"]]
        return cmd
