"""GitHub integration — post/update KelpMesh CI results as a PR comment.

All HTTP calls use stdlib urllib; zero extra dependencies.

Environment variables consumed (set automatically by GitHub Actions):
  GITHUB_TOKEN         - required for API calls
  GITHUB_REPOSITORY    - owner/repo  e.g. acme/analytics
  GITHUB_EVENT_PATH    - path to the JSON event payload (pull_request events)
  GITHUB_SHA           - current commit SHA
  GITHUB_RUN_ID        - actions run ID (for the "View run" link)
  GITHUB_API_URL       - default https://api.github.com (for GHES)
  GITHUB_SERVER_URL    - default https://github.com
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

_MARKER = "<!-- kelpmesh-ci -->"


def detect() -> Optional[dict]:
    """Return GitHub context dict or None if not running in GitHub Actions."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo  = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (token and repo):
        return None

    pr_number = _extract_pr_number()
    if not pr_number:
        return None

    server  = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_id  = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if run_id else ""

    return {
        "token":      token,
        "repo":       repo,
        "pr_number":  pr_number,
        "sha":        os.environ.get("GITHUB_SHA", "")[:7],
        "run_url":    run_url,
        "api_url":    os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
    }


def post_comment(ctx: dict, body: str) -> bool:
    """Post or update the KelpMesh CI comment on the PR. Returns True on success."""
    headers = {
        "Authorization": f"Bearer {ctx['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "kelpmesh-ci/0.2.0",
    }
    full_body = f"{_MARKER}\n{body}"
    payload   = json.dumps({"body": full_body}).encode()

    existing = _find_existing(ctx, headers)
    if existing:
        url    = f"{ctx['api_url']}/repos/{ctx['repo']}/issues/comments/{existing}"
        method = "PATCH"
    else:
        url    = f"{ctx['api_url']}/repos/{ctx['repo']}/issues/{ctx['pr_number']}/comments"
        method = "POST"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as exc:
        # Surface the error body if available
        try:
            err = json.loads(exc.read())
            print(f"[kelpmesh-ci] GitHub API error {exc.code}: {err.get('message', exc.reason)}")
        except Exception:
            print(f"[kelpmesh-ci] GitHub API error {exc.code}: {exc.reason}")
        return False
    except Exception as exc:
        print(f"[kelpmesh-ci] Failed to post PR comment: {exc}")
        return False


# ── helpers ────────────────────────────────────────────────────────────────

def _extract_pr_number() -> Optional[int]:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if event_path:
        try:
            with open(event_path) as fh:
                event = json.load(fh)
            pr = event.get("pull_request") or {}
            if pr.get("number"):
                return int(pr["number"])
            if event.get("number"):
                return int(event["number"])
        except Exception:
            pass

    # Fallback: refs/pull/123/merge
    ref = os.environ.get("GITHUB_REF", "")
    if "/pull/" in ref:
        try:
            return int(ref.split("/pull/")[1].split("/")[0])
        except (IndexError, ValueError):
            pass
    return None


def _find_existing(ctx: dict, headers: dict) -> Optional[int]:
    """Return the comment ID of an existing KelpMesh CI comment, or None."""
    url = (
        f"{ctx['api_url']}/repos/{ctx['repo']}/issues/{ctx['pr_number']}"
        "/comments?per_page=100"
    )
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            for c in json.loads(resp.read()):
                if _MARKER in c.get("body", ""):
                    return int(c["id"])
    except Exception:
        pass
    return None
