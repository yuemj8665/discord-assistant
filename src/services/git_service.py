import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path("data/mail_snapshots")


def _run_git(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def get_head_commit(repo_path: str) -> str:
    return _run_git(repo_path, "rev-parse", "HEAD")


def get_diff(repo_path: str, from_commit: str, file_path: Optional[str] = None) -> str:
    args = ["diff", from_commit, "HEAD"]
    if file_path:
        args += ["--", file_path]
    return _run_git(repo_path, *args)


def get_changed_files(repo_path: str, from_commit: str) -> list[str]:
    output = _run_git(repo_path, "diff", "--name-only", from_commit, "HEAD")
    return [f for f in output.splitlines() if f]


def get_file_content(repo_path: str, file_path: str) -> str:
    path = Path(repo_path) / file_path
    if not path.exists():
        return "(파일 없음)"
    return path.read_text(encoding="utf-8", errors="replace")


def get_initial_commit(repo_path: str) -> str:
    return _run_git(repo_path, "rev-list", "--max-parents=0", "HEAD")


def load_snapshot(repo_path: str) -> Optional[str]:
    """마지막 메일 전송 시점의 커밋 해시. 없으면 None."""
    slug = Path(repo_path).resolve().name
    snapshot_file = SNAPSHOTS_DIR / f"{slug}.json"
    try:
        return json.loads(snapshot_file.read_text())["commit"]
    except Exception:
        return None


def save_snapshot(repo_path: str, commit: str) -> None:
    slug = Path(repo_path).resolve().name
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_file = SNAPSHOTS_DIR / f"{slug}.json"
    snapshot_file.write_text(json.dumps({"commit": commit, "repo": repo_path}))
    logger.info("[GitService] 스냅샷 저장: %s → %s", slug, commit[:8])
