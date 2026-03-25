import pytest
from unittest.mock import patch, MagicMock

from src.services.llm_service import LLMService


class TestLLMService:
    def setup_method(self):
        self.llm = LLMService()

    def test_first_ask_builds_command_without_resume(self):
        cmd = self.llm._build_command("안녕")
        assert "--resume" not in cmd
        assert "안녕" in cmd

    def test_ask_with_session_builds_command_with_resume(self):
        self.llm._session_id = "test-session-123"
        cmd = self.llm._build_command("안녕")
        assert "--resume" in cmd
        assert "test-session-123" in cmd

    def test_reset_session_clears_session_id(self):
        self.llm._session_id = "some-session"
        self.llm.reset_session()
        assert self.llm.session_id is None

    @patch("subprocess.run")
    def test_ask_returns_response_text(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="안녕하세요!",
            stderr="",
        )
        result = self.llm.ask("안녕")
        assert result == "안녕하세요!"

    @patch("subprocess.run")
    def test_ask_raises_on_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="some error",
        )
        with pytest.raises(RuntimeError):
            self.llm.ask("안녕")
