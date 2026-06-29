"""Alert integrations — Slack, webhook, and log-based notification on run failure."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    project_name: str
    env: str
    succeeded: list[str]
    skipped: list[str]
    failed: list[dict]      # each dict has "name" and "error" keys
    anomalies: list[str]    # human-readable anomaly messages
    elapsed_s: float

    @property
    def has_failures(self) -> bool:
        return bool(self.failed)

    @property
    def has_anomalies(self) -> bool:
        return bool(self.anomalies)


def send_slack_alert(webhook_url: str, summary: RunSummary) -> bool:
    """POST a Slack block-kit message to *webhook_url*.

    Returns ``True`` on success, ``False`` on any error.
    """
    if not summary.has_failures and not summary.has_anomalies:
        return True  # nothing to alert on

    colour = "#E01E5A" if summary.has_failures else "#ECB22E"
    title = (
        f":red_circle: kelpmesh run failed — {summary.project_name}"
        if summary.has_failures
        else f":warning: kelpmesh anomaly — {summary.project_name}"
    )

    fields = []
    if summary.failed:
        failed_names = ", ".join(f["name"] for f in summary.failed)
        fields.append({"title": "Failed models", "value": failed_names, "short": False})
    if summary.anomalies:
        fields.append({"title": "Anomalies", "value": "\n".join(summary.anomalies), "short": False})
    if summary.succeeded:
        fields.append({"title": "Succeeded", "value": str(len(summary.succeeded)), "short": True})
    fields.append({"title": "Elapsed", "value": f"{summary.elapsed_s:.1f}s", "short": True})
    fields.append({"title": "Environment", "value": summary.env, "short": True})

    payload = {
        "attachments": [
            {
                "color": colour,
                "title": title,
                "fields": fields,
                "footer": "kelpmesh",
            }
        ]
    }

    return _post_json(webhook_url, payload)


def send_webhook_alert(webhook_url: str, summary: RunSummary) -> bool:
    """POST a generic JSON payload to *webhook_url*.

    Returns ``True`` on success, ``False`` on any error.
    """
    if not summary.has_failures and not summary.has_anomalies:
        return True

    payload = {
        "project": summary.project_name,
        "env": summary.env,
        "status": "failed" if summary.has_failures else "anomaly",
        "failed": [{"name": f["name"], "error": f["error"]} for f in summary.failed],
        "anomalies": summary.anomalies,
        "succeeded_count": len(summary.succeeded),
        "elapsed_s": summary.elapsed_s,
    }
    return _post_json(webhook_url, payload)


def _post_json(url: str, payload: dict) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except (urllib.error.URLError, OSError) as exc:
        _logger.warning("Alert delivery failed: %s", exc)
        return False
