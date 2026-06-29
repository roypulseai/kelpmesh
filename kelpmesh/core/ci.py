"""Slim CI — git-diff-aware model selection for changed-models-only runs."""

import logging
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)


def _git_diff_files(against: str = "main", project_path: Path | None = None) -> list[str]:
    """Return list of changed + untracked file paths vs `against`."""
    files = []
    cwd = project_path or Path.cwd()
    try:
        # Try diff against base branch
        cmd = ["git", "diff", "--name-only", against, "--"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        if result.returncode == 0:
            files.extend(f.strip() for f in result.stdout.splitlines() if f.strip())
        else:
            # Fallback: diff HEAD for modified files
            head_cmd = ["git", "diff", "--name-only", "HEAD", "--"]
            head_result = subprocess.run(head_cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
            if head_result.returncode == 0:
                files.extend(f.strip() for f in head_result.stdout.splitlines() if f.strip())
        # Also include untracked files
        status_cmd = ["git", "ls-files", "--others", "--exclude-standard", "--full-name"]
        status_result = subprocess.run(status_cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        if status_result.returncode == 0:
            files.extend(f.strip() for f in status_result.stdout.splitlines() if f.strip())
    except FileNotFoundError:
        _logger.debug("git not found — not a git repository?")
        return []
    except subprocess.TimeoutExpired:
        _logger.debug("git diff timed out")
        return []
    return sorted(set(files))


def _git_merge_base(project_path: Path | None = None) -> str:
    """Detect the best base branch: main, master, or HEAD~1."""
    for candidate in ("main", "master", "HEAD~1"):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", candidate],
                capture_output=True, text=True, cwd=project_path or Path.cwd(),
                timeout=10,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return "HEAD~1"


def changed_models(project_path: Path | None = None, against: str | None = None) -> list[str]:
    """Detect model names changed vs the base branch.

    Returns model names (stem of .sql files) that differ.
    """
    base = against or _git_merge_base(project_path)
    files = _git_diff_files(base, project_path)
    models = []
    for f in files:
        path = Path(f)
        if path.suffix == ".sql":
            stem = path.stem
            models.append(stem)
    return sorted(set(models))


def changed_subgraph(project_path: Path | None = None, against: str | None = None) -> list[str]:
    """Return selection expressions (@model) to build the full subgraph of changed models.

    Each changed model gets the @ prefix to include upstream + downstream.
    """
    models = changed_models(project_path, against)
    return [f"@{m}" for m in models]
