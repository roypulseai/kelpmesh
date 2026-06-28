"""GitLab integration — post/update KelpMesh CI results as an MR comment (note).

Environment variables consumed (set automatically by GitLab CI/CD):
  GITLAB_TOKEN            - personal/project access token with api scope
                            (or CI_JOB_TOKEN for project-scoped comment)
  CI_SERVER_URL           - e.g. https://gitlab.com
  CI_PROJECT_ID           - numeric project ID
  CI_MERGE_REQUEST_IID    - MR internal ID  (only set in merge_request pipelines)
  CI_PIPELINE_URL         - link back to the pipeline
  CI_COMMIT_SHORT_SHA     - short commit SHA
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

_MARKER = "<!-- kelpmesh-ci -->"


def detect() -> Optional[dict]:
    """Return GitLab context dict or None if not in a GitLab merge-request pipeline."""
    token      = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN", "")
    project_id = os.environ.get("CI_PROJECT_ID", "")
    mr_iid     = os.environ.get("CI_MERGE_REQUEST_IID", "")

    if not (token and project_id and mr_iid):
        return None

    server = os.environ.get("CI_SERVER_URL", "https://gitlab.com").rstrip("/")
    return {
        "token":        token.strip(),
        "server":       server,
        "project_id":   project_id,
        "mr_iid":       mr_iid,
        "sha":          os.environ.get("CI_COMMIT_SHORT_SHA", ""),
        "pipeline_url": os.environ.get("CI_PIPELINE_URL", ""),
        "is_job_token": bool(os.environ.get("CI_JOB_TOKEN")) and not os.environ.get("GITLAB_TOKEN"),
    }


def post_comment(ctx: dict, body: str) -> bool:
    """Post or update a KelpMesh CI note on the MR. Returns True on success."""
    base = f"{ctx['server']}/api/v4/projects/{ctx['project_id']}/merge_requests/{ctx['mr_iid']}/notes"

    auth_header = "JOB-TOKEN" if ctx.get("is_job_token") else "PRIVATE-TOKEN"
    headers = {
        auth_header:    ctx["token"],
        "Content-Type": "application/json",
        "User-Agent":   "kelpmesh-ci/0.2.0",
    }
    full_body = f"{_MARKER}\n{body}"
    payload   = json.dumps({"body": full_body}).encode()

    existing = _find_existing(ctx, headers, base)
    if existing:
        url    = f"{base}/{existing}"
        method = "PUT"
    else:
        url    = base
        method = "POST"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read())
            msg = err.get("message", exc.reason)
        except Exception:
            msg = exc.reason
        print(f"[kelpmesh-ci] GitLab API error {exc.code}: {msg}")
        return False
    except Exception as exc:
        print(f"[kelpmesh-ci] Failed to post MR comment: {exc}")
        return False


def _find_existing(ctx: dict, headers: dict, base_url: str) -> Optional[int]:
    url = f"{base_url}?per_page=100"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            for note in json.loads(resp.read()):
                if _MARKER in note.get("body", ""):
                    return int(note["id"])
    except Exception:
        pass
    return None
