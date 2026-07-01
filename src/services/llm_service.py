import os
import subprocess
import json
import logging
import threading
from pathlib import Path
from typing import Optional

from src.core.config import PROJECT_ROOT, config
from src.core.timeutil import WEEKDAYS, now_kst

logger = logging.getLogger(__name__)

# launchd WorkingDirectory에 의존하지 않도록 프로젝트 루트 기준 절대경로 사용
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"


def _resolve_oauth_token() -> Optional[str]:
    """claude CLI에 주입할 OAuth 토큰을 해석한다.

    launchd 백그라운드 프로세스는 macOS Keychain의 claude 자격증명을 읽지 못해
    401이 난다. .env의 장기 토큰을 우선 사용하고, 없으면 credentials.json의
    accessToken을 매 호출 시점에 읽어 환경변수로 주입한다(파일이 갱신되면 자동 반영).
    """
    if config.CLAUDE_CODE_OAUTH_TOKEN:
        return config.CLAUDE_CODE_OAUTH_TOKEN
    try:
        data = json.loads(Path(config.CLAUDE_CREDENTIALS_PATH).read_text())
        oauth = data.get("claudeAiOauth", data)
        return oauth.get("accessToken") or None
    except Exception:
        return None

# Discord는 마크다운 테이블(|---|)을 렌더링하지 못해 raw 텍스트로 깨져 보인다.
# 모든 역할 공통으로 표 대신 목록형 마크다운을 사용하도록 강제한다.
_DISCORD_FORMAT_RULE = (
    "\n\n[출력 형식 — Discord 채팅]\n"
    "Discord는 마크다운 표(| 항목 | 금액 | 같은 |---| 테이블)를 렌더링하지 못해 "
    "파이프 문자가 그대로 노출되어 매우 보기 불편합니다. "
    "절대 마크다운 테이블을 사용하지 마세요. 대신 다음을 사용하세요:\n"
    "- 항목 나열은 `- 라벨: 값` 형태의 글머리표 목록으로 작성\n"
    "- 정렬된 수치 비교가 꼭 필요하면 코드블록(```) 안에 고정폭 텍스트로 작성\n"
    "- 강조는 **굵게**, 구분은 이모지와 빈 줄을 활용\n"
    "- 금액·수치는 천 단위 콤마를 사용"
)

ROLE_CONFIGS = {
    "general": {
        "model": "sonnet",
        "system_prompt": (
            "당신은 명재의 개인 비서입니다. "
            "웹 검색 등 도구 사용 시 사전에 확인을 구하지 말고 즉시 실행하세요. "
            "모든 도구 사용 권한은 이미 허가되어 있습니다.\n\n"
            "세션 시작 시 반드시 data/sessions/general/memory.md를 읽어 명재에 대한 맥락을 파악하세요. "
            "오늘 날짜의 data/sessions/general/daily/YYYY-MM-DD.md 파일이 있으면 함께 읽어 이전 대화 흐름을 이어가세요."
            + _DISCORD_FORMAT_RULE
        ),
        "mcp": False,
        "allowed_tools": "WebSearch,WebFetch",
    },
    "infra": {
        "model": "sonnet",
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
        "model": "sonnet",
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
    "work": {
        "model": "opus",
        "system_prompt": (
            "당신은 명재의 업무 프로젝트 전담 비서입니다. "
            f"담당 프로젝트 디렉토리는 {config.WORK_PROJECT_DIR} 입니다. "
            "이 디렉토리에 직접 접근하여 코드 작성, 분석, 디버깅, 리뷰를 수행합니다. "
            "파일 읽기·쓰기·생성 등 도구 사용 시 사전 확인 없이 즉시 실행하세요. "
            "모든 도구 사용 권한은 이미 허가되어 있습니다.\n\n"
            f"세션 시작 시 {config.WORK_PROJECT_DIR}/claude.md 파일이 존재하면 반드시 읽어 "
            "해당 파일에 정의된 정책과 규칙을 최우선으로 따르세요.\n\n"
            "명재가 '메일로 보내줘', '메일로 전달해줘' 등 메일 발송을 요청하면 "
            f"send_email 도구를 사용해 {config.MAIL_RECIPIENT}로 즉시 발송하세요. "
            "제목과 본문을 적절히 구성하여 보내면 됩니다. "
            "파일을 첨부해달라고 하면 attachments 파라미터에 절대 경로 목록을 전달하세요.\n\n"
            "응답은 Discord 채팅에 최적화된 형식으로 작성하세요: "
            "코드 블록(```)을 적극 활용하고, 표는 마크다운 테이블 대신 고정폭 텍스트로 작성하세요."
        ),
        "mcp": True,
        "allowed_tools": "WebSearch,WebFetch,mcp__mail__send_email",
        "extra_dirs": [config.WORK_PROJECT_DIR] if config.WORK_PROJECT_DIR else [],
    },
    "calendar": {
        "model": "sonnet",
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
            + _DISCORD_FORMAT_RULE
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
        # infra/news 인스턴스는 스케줄러와 커맨드가 공유하므로,
        # 세션 ID 갱신·파일 쓰기가 겹치지 않도록 역할 단위로 직렬화한다.
        self._lock = threading.Lock()
        self._session_id: Optional[str] = self._load_session()
        if self._session_id:
            logger.info("[LLM:%s] 저장된 세션 복원: %s", self._role, self._session_id)

    def ask(self, message: str) -> str:
        with self._lock:
            return self._ask_locked(message, allow_retry=True)

    def _ask_locked(self, message: str, allow_retry: bool) -> str:
        cmd = self._build_command(message)
        logger.debug("[LLM:%s] Claude CLI 실행: %s", self._role, " ".join(cmd[:6]) + " ...")

        try:
            env = os.environ.copy()
            env["GOOGLE_OAUTH_CREDENTIALS"] = config.GOOGLE_OAUTH_CREDENTIALS
            token = _resolve_oauth_token()
            if token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = token
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
            if allow_retry and self._session_id and "No conversation found" in stderr:
                logger.warning("[LLM:%s] 세션 만료. 새 세션으로 재시도", self._role)
                self._session_id = None
                return self._ask_locked(message, allow_retry=False)
            # claude는 한도 초과 등 일부 오류를 stderr가 아닌 stdout(JSON)에 담는다.
            # stderr가 비어 있으면 stdout에서 실제 원인을 끌어와 로깅·표시한다.
            detail = stderr
            if not detail:
                stdout = result.stdout.strip()
                try:
                    data = json.loads(stdout)
                    detail = (data.get("result") or data.get("error")
                              or json.dumps(data, ensure_ascii=False))[:800]
                except (json.JSONDecodeError, AttributeError):
                    detail = stdout[:800]
            logger.error(
                "[LLM:%s] Claude CLI 오류 (exit=%s): %s",
                self._role, result.returncode, detail or "(stdout·stderr 모두 비어 있음)",
            )
            raise RuntimeError(f"Claude CLI 오류: {detail or '(빈 응답)'}")

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
        now = now_kst()
        daily_dir = SESSIONS_DIR / self._role / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / f"{now.strftime('%Y-%m-%d')}.md"

        header = ""
        if not daily_file.exists():
            header = f"## {now.strftime('%Y-%m-%d')} ({WEEKDAYS[now.weekday()]})\n\n"

        entry = (
            f"### [{now.strftime('%H:%M')}] 명재\n{user_msg}\n\n"
            f"### [{now.strftime('%H:%M')}] Claude\n{assistant_msg}\n\n"
        )
        # append 모드 단일 쓰기 — exists() 확인과 쓰기 사이의 경합(TOCTOU)을 피한다.
        with daily_file.open("a", encoding="utf-8") as f:
            f.write(header + entry)

    @property
    def daily_dir(self) -> Path:
        return SESSIONS_DIR / self._role / "daily"

    def reset_session(self) -> None:
        with self._lock:
            self._session_id = None
            self._session_file.unlink(missing_ok=True)
        logger.info("[LLM:%s] 세션 초기화됨", self._role)

    def _save_session(self) -> None:
        self._session_file.parent.mkdir(parents=True, exist_ok=True)
        # 임시 파일에 쓴 뒤 원자적으로 교체 — 쓰기 도중 크래시해도 파일이 깨지지 않는다.
        tmp = self._session_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"session_id": self._session_id}))
        tmp.replace(self._session_file)

    def _load_session(self) -> Optional[str]:
        if not self._session_file.exists():
            return None
        try:
            return json.loads(self._session_file.read_text()).get("session_id")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[LLM:%s] 세션 파일 읽기 실패 — 새 세션으로 시작: %s", self._role, e)
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
        if "model" in role_cfg:
            cmd += ["--model", role_cfg["model"]]
        if self._session_id:
            cmd += ["--resume", self._session_id]
        for d in config.ALLOWED_DIRS:
            cmd += ["--add-dir", d.strip()]
        for d in role_cfg.get("extra_dirs", []):
            if d:
                cmd += ["--add-dir", d]
        cmd += ["--add-dir", self._memory_dir]
        if role_cfg["mcp"]:
            cmd += ["--mcp-config", config.MCP_CONFIG_PATH]
        cmd += ["--allowedTools", role_cfg["allowed_tools"]]
        return cmd
