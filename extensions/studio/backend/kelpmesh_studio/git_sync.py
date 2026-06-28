"""Git sync — connect a Studio project to GitHub/GitLab, pull on push."""

from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import subprocess
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text
from kelpmesh_studio.db import Base


class GitRepo(Base):
    __tablename__ = "git_repos"
    id              = Column(Integer, primary_key=True)
    project_name    = Column(String, unique=True, nullable=False)
    remote_url      = Column(String, nullable=False)
    branch          = Column(String, default="main")
    provider        = Column(String, default="github")  # github | gitlab | bitbucket
    webhook_secret  = Column(String, nullable=True)
    auto_sync       = Column(Boolean, default=True)
    last_synced_at  = Column(DateTime, nullable=True)
    last_commit_sha = Column(String, nullable=True)
    sync_status     = Column(String, default="never")  # never | ok | error
    sync_error      = Column(Text, nullable=True)
    created_at      = Column(DateTime, server_default=sa.func.now())


class GitSyncManager:
    def __init__(self, session):
        self._session = session

    # ------------------------------------------------------------------ #
    # Repo management                                                      #
    # ------------------------------------------------------------------ #

    def connect(
        self,
        project_name: str,
        remote_url: str,
        branch: str = "main",
        provider: str = "github",
        auto_sync: bool = True,
    ) -> GitRepo:
        existing = self._session.query(GitRepo).filter_by(project_name=project_name).first()
        webhook_secret = secrets.token_hex(32)
        if existing:
            existing.remote_url = remote_url
            existing.branch = branch
            existing.provider = provider
            existing.auto_sync = auto_sync
            existing.webhook_secret = webhook_secret
            self._session.commit()
            return existing
        repo = GitRepo(
            project_name=project_name,
            remote_url=remote_url,
            branch=branch,
            provider=provider,
            webhook_secret=webhook_secret,
            auto_sync=auto_sync,
        )
        self._session.add(repo)
        self._session.commit()
        return repo

    def disconnect(self, project_name: str) -> bool:
        repo = self._session.query(GitRepo).filter_by(project_name=project_name).first()
        if not repo:
            return False
        self._session.delete(repo)
        self._session.commit()
        return True

    def get(self, project_name: str) -> Optional[GitRepo]:
        return self._session.query(GitRepo).filter_by(project_name=project_name).first()

    # ------------------------------------------------------------------ #
    # Sync                                                                 #
    # ------------------------------------------------------------------ #

    def sync(self, project_name: str, project_path: Path) -> dict:
        """Pull latest commits. Returns {success, sha, message}."""
        repo = self.get(project_name)
        if not repo:
            return {"success": False, "error": "No git repo configured for this project"}

        if not project_path.exists():
            return {"success": False, "error": f"Project path not found: {project_path}"}

        from datetime import datetime, timezone
        git_dir = project_path / ".git"

        try:
            if not git_dir.exists():
                result = subprocess.run(
                    ["git", "clone", "--branch", repo.branch, repo.remote_url, str(project_path)],
                    capture_output=True, text=True, timeout=60,
                )
            else:
                result = subprocess.run(
                    ["git", "-C", str(project_path), "pull", "origin", repo.branch],
                    capture_output=True, text=True, timeout=60,
                )

            if result.returncode != 0:
                repo.sync_status = "error"
                repo.sync_error = result.stderr[:500]
                self._session.commit()
                return {"success": False, "error": result.stderr}

            sha_result = subprocess.run(
                ["git", "-C", str(project_path), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""

            repo.last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
            repo.last_commit_sha = sha
            repo.sync_status = "ok"
            repo.sync_error = None
            self._session.commit()
            return {"success": True, "sha": sha, "output": result.stdout}

        except subprocess.TimeoutExpired:
            repo.sync_status = "error"
            repo.sync_error = "git operation timed out"
            self._session.commit()
            return {"success": False, "error": "git operation timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "git not found in PATH"}

    # ------------------------------------------------------------------ #
    # Webhook verification                                                 #
    # ------------------------------------------------------------------ #

    def verify_github_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify X-Hub-Signature-256 header from GitHub."""
        if not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_gitlab_token(self, token: str, secret: str) -> bool:
        """Verify X-Gitlab-Token header."""
        return hmac.compare_digest(token, secret)

    def parse_push_event(self, payload: dict, provider: str = "github") -> dict:
        """Extract branch and commit SHA from a push webhook payload."""
        if provider == "github":
            ref = payload.get("ref", "")
            branch = ref.replace("refs/heads/", "")
            sha = payload.get("after", "")
            pusher = payload.get("pusher", {}).get("name", "unknown")
        elif provider == "gitlab":
            ref = payload.get("ref", "")
            branch = ref.replace("refs/heads/", "")
            sha = payload.get("after", "")
            pusher = payload.get("user_name", "unknown")
        else:
            branch = ""
            sha = ""
            pusher = "unknown"
        return {"branch": branch, "sha": sha, "pusher": pusher}


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
