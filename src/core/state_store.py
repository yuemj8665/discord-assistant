"""스케줄러 실행 상태 영속화.

봇은 launchd KeepAlive로 크래시 시 수시로 재시작된다. '오늘 이미 보냈는지'
같은 상태를 메모리에만 두면 재시작 직후 일일 리포트·알림이 중복 발송되므로,
단일 JSON 파일(data/scheduler_state.json)에 변경 즉시 저장해 재시작을 견딘다.
"""
import json
import logging
import threading
from pathlib import Path

from src.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


class StateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[StateStore] 상태 파일 읽기 실패 — 빈 상태로 시작: %s", e)
            return {}

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
            self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))
        tmp.replace(self._path)


# 모든 스케줄러가 공유하는 단일 인스턴스
scheduler_state = StateStore(PROJECT_ROOT / "data" / "scheduler_state.json")
