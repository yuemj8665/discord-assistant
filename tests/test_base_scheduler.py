from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.state_store import StateStore
from src.core import timeutil
from src.scheduler.base_scheduler import BaseScheduler


@pytest.fixture
def store(tmp_path):
    return StateStore(tmp_path / "state.json")


class TestStateStore:
    def test_get_default_when_empty(self, store):
        assert store.get("missing") is None
        assert store.get("missing", "기본값") == "기본값"

    def test_set_then_get(self, store):
        store.set("news.daily", "2026-07-02")
        assert store.get("news.daily") == "2026-07-02"

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "state.json"
        StateStore(path).set("key", {"a": 1})
        assert StateStore(path).get("key") == {"a": 1}

    def test_corrupt_file_starts_empty(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("{깨진 json")
        assert StateStore(path).get("key") is None

    def test_atomic_write_no_tmp_leftover(self, store, tmp_path):
        store.set("k", "v")
        assert not (tmp_path / "state.json.tmp").exists()


@pytest.fixture
def scheduler(store, monkeypatch):
    monkeypatch.setattr("src.scheduler.base_scheduler.scheduler_state", store)
    sched = BaseScheduler(MagicMock())
    sched._state = store
    return sched


def _fake_now(monkeypatch, hour: int, minute: int, day: int = 2):
    fixed = datetime(2026, 7, day, hour, minute, tzinfo=timeutil.KST)
    monkeypatch.setattr("src.scheduler.base_scheduler.now_kst", lambda: fixed)


class TestShouldRunDaily:
    def test_runs_once_at_time(self, scheduler, monkeypatch):
        _fake_now(monkeypatch, 8, 0)
        assert scheduler._should_run_daily("job", 8, 0) is True
        assert scheduler._should_run_daily("job", 8, 0) is False  # 같은 날 재실행 방지

    def test_not_before_time(self, scheduler, monkeypatch):
        _fake_now(monkeypatch, 7, 59)
        assert scheduler._should_run_daily("job", 8, 0) is False

    def test_survives_restart(self, scheduler, store, monkeypatch):
        """봇 재시작(새 인스턴스) 후에도 같은 날 중복 실행하지 않는다."""
        _fake_now(monkeypatch, 8, 30)
        assert scheduler._should_run_daily("job", 8, 0) is True

        restarted = BaseScheduler(MagicMock())
        restarted._state = store
        assert restarted._should_run_daily("job", 8, 0) is False

    def test_runs_again_next_day(self, scheduler, monkeypatch):
        _fake_now(monkeypatch, 8, 0, day=2)
        assert scheduler._should_run_daily("job", 8, 0) is True
        _fake_now(monkeypatch, 8, 0, day=3)
        assert scheduler._should_run_daily("job", 8, 0) is True


class TestSendTo:
    async def test_splits_long_message(self, scheduler):
        channel = MagicMock()
        channel.send = AsyncMock()
        scheduler._bot.get_channel.return_value = channel

        await scheduler._send_to(123, "가" * 4500)

        assert channel.send.await_count == 3  # 2000 + 2000 + 500

    async def test_missing_channel_logs_and_skips(self, scheduler):
        scheduler._bot.get_channel.return_value = None
        await scheduler._send_to(123, "메시지")  # 예외 없이 통과
