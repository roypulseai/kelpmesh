"""Alert channels — Slack, email, and generic webhooks for kelpmesh Studio Pro."""

from __future__ import annotations
import json
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlencode

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text
from kelpmesh_studio.db import Base


class AlertChannel(Base):
    __tablename__ = "alert_channels"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(String, nullable=False, default="default")
    name        = Column(String, nullable=False)
    channel_type = Column(String, nullable=False)   # slack | email | webhook
    config      = Column(Text, nullable=False)       # JSON config
    # Events that trigger this channel (comma-sep)
    events      = Column(String, default="run_failed,sla_breach,schema_drift")
    active      = Column(Boolean, default=True)
    created_at  = Column(DateTime, server_default=sa.func.now())


class AlertDispatcher:
    """Send alerts to configured channels."""

    def __init__(self, session):
        self._session = session

    # ------------------------------------------------------------------ #
    # Channel management                                                   #
    # ------------------------------------------------------------------ #

    def add_channel(
        self,
        org_id: str,
        name: str,
        channel_type: str,
        config: dict,
        events: str = "run_failed,sla_breach,schema_drift",
    ) -> AlertChannel:
        ch = AlertChannel(
            org_id=org_id,
            name=name,
            channel_type=channel_type,
            config=json.dumps(config),
            events=events,
        )
        self._session.add(ch)
        self._session.commit()
        return ch

    def remove_channel(self, channel_id: int, org_id: str) -> bool:
        ch = self._session.query(AlertChannel).filter_by(id=channel_id, org_id=org_id).first()
        if not ch:
            return False
        self._session.delete(ch)
        self._session.commit()
        return True

    def list_channels(self, org_id: str) -> list[AlertChannel]:
        return (
            self._session.query(AlertChannel)
            .filter_by(org_id=org_id, active=True)
            .all()
        )

    # ------------------------------------------------------------------ #
    # Dispatch                                                             #
    # ------------------------------------------------------------------ #

    def dispatch(
        self,
        org_id: str,
        event: str,
        title: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> list[dict]:
        """Send alert to all channels subscribed to this event."""
        channels = self._session.query(AlertChannel).filter_by(org_id=org_id, active=True).all()
        results = []
        for ch in channels:
            subscribed = [e.strip() for e in ch.events.split(",")]
            if event not in subscribed and "*" not in subscribed:
                continue
            try:
                cfg = json.loads(ch.config)
                ok, detail = self._send(ch.channel_type, cfg, title, message, metadata or {})
                results.append({"channel": ch.name, "type": ch.channel_type, "ok": ok, "detail": detail})
            except Exception as exc:
                results.append({"channel": ch.name, "type": ch.channel_type, "ok": False, "detail": str(exc)})
        return results

    def test_channel(self, channel_id: int, org_id: str) -> dict:
        ch = self._session.query(AlertChannel).filter_by(id=channel_id, org_id=org_id).first()
        if not ch:
            return {"ok": False, "detail": "Channel not found"}
        cfg = json.loads(ch.config)
        ok, detail = self._send(ch.channel_type, cfg, "kelpmesh test alert", "This is a test alert from kelpmesh Studio.", {})
        return {"ok": ok, "detail": detail}

    # ------------------------------------------------------------------ #
    # Senders                                                              #
    # ------------------------------------------------------------------ #

    def _send(self, channel_type: str, cfg: dict, title: str, message: str, meta: dict) -> tuple[bool, str]:
        if channel_type == "slack":
            return self._send_slack(cfg, title, message, meta)
        elif channel_type == "email":
            return self._send_email(cfg, title, message)
        elif channel_type == "webhook":
            return self._send_webhook(cfg, title, message, meta)
        return False, f"Unknown channel type '{channel_type}'"

    def _send_slack(self, cfg: dict, title: str, message: str, meta: dict) -> tuple[bool, str]:
        url = cfg.get("webhook_url", "")
        if not url:
            return False, "No webhook_url configured"
        payload = json.dumps({
            "text": f"*{title}*\n{message}",
            "username": "kelpmesh Studio",
            "icon_emoji": ":bricks:",
        }).encode()
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=10) as resp:
                return resp.status == 200, f"HTTP {resp.status}"
        except URLError as e:
            return False, str(e)

    def _send_email(self, cfg: dict, title: str, message: str) -> tuple[bool, str]:
        # SMTP sending — requires smtplib; returns a stub in test mode
        smtp_host = cfg.get("smtp_host", "")
        if not smtp_host:
            return False, "No smtp_host configured"
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = f"[kelpmesh] {title}"
        msg["From"] = cfg.get("from_address", "noreply@example.com")
        msg["To"] = cfg.get("to_address", "")
        msg.set_content(message)
        try:
            with smtplib.SMTP(smtp_host, cfg.get("smtp_port", 587), timeout=10) as smtp:
                if cfg.get("use_tls", True):
                    smtp.starttls()
                if cfg.get("username"):
                    smtp.login(cfg["username"], cfg.get("password", ""))
                smtp.send_message(msg)
            return True, "sent"
        except Exception as e:
            return False, str(e)

    def _send_webhook(self, cfg: dict, title: str, message: str, meta: dict) -> tuple[bool, str]:
        url = cfg.get("url", "")
        if not url:
            return False, "No url configured"
        payload = json.dumps({"title": title, "message": message, "meta": meta}).encode()
        headers = {"Content-Type": "application/json"}
        if cfg.get("secret_header") and cfg.get("secret_value"):
            headers[cfg["secret_header"]] = cfg["secret_value"]
        try:
            req = Request(url, data=payload, headers=headers, method="POST")
            with urlopen(req, timeout=10) as resp:
                return resp.status < 400, f"HTTP {resp.status}"
        except URLError as e:
            return False, str(e)


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
