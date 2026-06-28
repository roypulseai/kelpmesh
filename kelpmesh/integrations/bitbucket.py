"""Bitbucket Cloud integration — post KelpMesh CI results as a PR comment.

Environment variables consumed (set automatically by Bitbucket Pipelines):
  BITBUCKET_TOKEN         - app password / repository access token (api scope)
  BITBUCKET_REPO_OWNER    - workspace slug  e.g. acme
  BITBUCKET_REPO_SLUG     - repo slug  e.g. analytics
  BITBUCKET_PR_ID         - pull-request ID  (only in PR pipelines)
  BITBUCKET_COMMIT        - full commit SHA
  BITBUCKET_BUILD_NUMBER  - pipeline build number

Note: CI_JOB_TOKEN (from Bitbucket) does NOT have API write access. You must
create a Bitbucket app password with `pullrequest:write` scope and store it
as a pipeline secret named BITBUCKET_TOKEN.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

_MARKER    = "<!-- kelpmesh-ci -->"
_API_BASE  = "https://api.bitbucket.org/2.0"


def detect() -> Optional[dict]:
    """Return Bitbucket context dict or None if not in a Bitbucket PR pipeline."""
    token   = os.environ.get("BITBUCKET_TOKEN", "").strip()
    owner   = os.environ.get("BITBUCKET_REPO_OWNER", "")
    slug    = os.environ.get("BITBUCKET_REPO_SLUG", "")
    pr_id   = os.environ.get("BITBUCKET_PR_ID", "")

    if not (token and owner and slug and pr_id):
        return None

    commit = os.environ.get("BITBUCKET_COMMIT", "")
    build  = os.environ.get("BITBUCKET_BUILD_NUMBER", "")
    pipe_url = (
        f"https://bitbucket.org/{owner}/{slug}/addon/pipelines/home"
        f"#!/results/{build}" if build else ""
    )
    return {
        "token":    token,
        "owner":    owner,
        "slug":     slug,
        "pr_id":    pr_id,
        "sha":      commit[:7],
        "run_url":  pipe_url,
    }


def post_comment(ctx: dict, body: str) -> bool:
    base = f"{_API_BASE}/repositories/{ctx['owner']}/{ctx['slug']}/pullrequests/{ctx['pr_id']}/comments"
    headers = {
        "Authorization": f"Bearer {ctx['token']}",
        "Content-Type":  "application/json",
        "User-Agent":    "kelpmesh-ci/0.2.0",
    }
    full_body = f"{_MARKER}\n{body}"

    existing = _find_existing(ctx, headers, base)
    if existing:
        url    = f"{base}/{existing}"
        method = "PUT"
        payload = json.dumps({"content": {"raw": full_body}}).encode()
    else:
        url     = base
        method  = "POST"
        payload = json.dumps({"content": {"raw": full_body}}).encode()

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as exc:
        print(f"[kelpmesh-ci] Bitbucket API error {exc.code}: {exc.reason}")
        return False
    except Exception as exc:
        print(f"[kelpmesh-ci] Failed to post PR comment: {exc}")
        return False


def _find_existing(ctx: dict, headers: dict, base_url: str) -> Optional[int]:
    url = f"{base_url}?pagelen=50"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            for c in data.get("values", []):
                raw = c.get("content", {}).get("raw", "")
                if _MARKER in raw:
                    return int(c["id"])
    except Exception:
        pass
    return None
