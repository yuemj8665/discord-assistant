import pytest
from unittest.mock import patch, MagicMock

from src.services import llm_service
from src.services.llm_service import LLMService


@pytest.fixture
def llm(tmp_path, monkeypatch):
    """실제 운영 세션 파일(data/sessions/)을 건드리지 않도록 임시 디렉토리로 격리."""
    monkeypatch.setattr(llm_service, "SESSIONS_DIR", tmp_path)
    return LLMService()


class TestLLMService:
    def test_first_ask_builds_command_without_resume(self, llm):
        cmd = llm._build_command("안녕")
        assert "--resume" not in cmd
        assert "안녕" in cmd

    def test_ask_with_session_builds_command_with_resume(self, llm):
        llm._session_id = "test-session-123"
        cmd = llm._build_command("안녕")
        assert "--resume" in cmd
        assert "test-session-123" in cmd

    def test_reset_session_clears_session_id(self, llm):
        llm._session_id = "some-session"
        llm.reset_session()
        assert llm.session_id is None

    @patch("subprocess.run")
    def test_ask_returns_response_text(self, mock_run, llm):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="안녕하세요!",
            stderr="",
        )
        result = llm.ask("안녕")
        assert result == "안녕하세요!"

    @patch("subprocess.run")
    def test_ask_raises_on_nonzero_returncode(self, mock_run, llm):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="some error",
        )
        with pytest.raises(RuntimeError):
            llm.ask("안녕")

    @patch("subprocess.run")
    def test_session_expiry_retries_once_with_new_session(self, mock_run, llm):
        """세션 만료 시 정확히 1회만 재시도한다 (무한 재귀 방지)."""
        llm._session_id = "expired-session"
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="No conversation found with session ID expired-session",
        )
        with pytest.raises(RuntimeError):
            llm.ask("안녕")
        assert mock_run.call_count == 2  # 원 호출 + 재시도 1회
        assert llm.session_id is None

    def test_save_session_is_atomic(self, llm, tmp_path):
        """세션 저장은 임시 파일 → 교체 방식이어야 한다."""
        llm._session_id = "abc-123"
        llm._save_session()
        assert llm._session_file.exists()
        assert not llm._session_file.with_suffix(".json.tmp").exists()
        assert llm._load_session() == "abc-123"
