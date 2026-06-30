"""Phase H — kelpmesh Studio Pro features: pricing, RBAC, audit, API keys,
git sync, alerts, SLA monitoring."""

from __future__ import annotations
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """In-memory SQLite session with all Pro module tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from kelpmesh_studio.db import Base
    import kelpmesh_studio.pricing as pm
    import kelpmesh_studio.rbac as rm
    import kelpmesh_studio.audit as am
    import kelpmesh_studio.api_keys as km
    import kelpmesh_studio.git_sync as gm
    import kelpmesh_studio.alerts as alm
    import kelpmesh_studio.sla as sm

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# PricingEngine — tier loading
# ---------------------------------------------------------------------------

class TestPricingEngine:
    def test_loads_default_yml(self):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        tiers = eng.all_tiers()
        assert "free" in tiers
        assert "pro" in tiers
        assert "business" in tiers
        assert "enterprise" in tiers

    def test_community_free(self):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        t = eng.get_tier("free")
        assert t.price_monthly_chf == 0
        assert t.max_users == 1
        assert t.pro_features is False

    def test_pro_features_enabled(self):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        t = eng.get_tier("pro")
        assert t.pro_features is True
        assert t.rbac is True
        assert t.api_keys is True
        assert t.git_sync is True
        assert t.alerts is True

    def test_enterprise_unlimited(self):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        t = eng.get_tier("enterprise")
        assert t.max_users == 0       # 0 = unlimited
        assert t.max_models == 0
        assert t.sso is True

    def test_custom_pricing_yml(self, tmp_path):
        custom = tmp_path / "pricing.yml"
        custom.write_text("""
tiers:
  startup:
    name: Startup
    price_monthly_chf: 25
    max_users: 3
    max_models: 50
    max_projects: 10
    max_schedules_per_project: 3
    pro_features: true
    sso: false
    audit_log: true
    rbac: true
    api_keys: false
    git_sync: false
    alerts: false
    support: "Email"
""", encoding="utf-8")
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine(config_path=custom)
        t = eng.get_tier("startup")
        assert t is not None
        assert t.price_monthly_chf == 25
        assert t.max_users == 3

    def test_resolve_price_no_override(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        result = eng.resolve_price("pro", org_id="org1", session=db)
        assert result["base_price_chf"] == 49
        assert result["effective_price_chf"] == 49
        assert result["discount_applied"] is None

    def test_resolve_price_with_org_override(self, db):
        from kelpmesh_studio.pricing import PricingEngine, OrgPricing
        eng = PricingEngine()
        db.add(OrgPricing(org_id="special_org", tier="pro", custom_price_chf=19.0, note="pilot deal"))
        db.commit()
        result = eng.resolve_price("pro", org_id="special_org", session=db)
        assert result["effective_price_chf"] == 19.0
        assert result["note"] == "pilot deal"


class TestPromoCode:
    def test_create_promo(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        promo = eng.create_promo(db, code="LAUNCH50", discount_type="pct",
                                  discount_value=50, description="Launch offer")
        assert promo.id is not None
        assert promo.code == "LAUNCH50"
        assert promo.discount_type == "pct"
        assert promo.discount_value == 50

    def test_apply_pct_promo(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        eng.create_promo(db, code="HALF", discount_type="pct", discount_value=50)
        result = eng.apply_promo("HALF", "pro", org_id="org1", session=db)
        assert result["success"] is True
        assert result["effective_price_chf"] == 24.5   # 49 * 0.5

    def test_apply_fixed_promo(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        eng.create_promo(db, code="SAVE10", discount_type="fixed", discount_value=10)
        result = eng.apply_promo("SAVE10", "pro", org_id="org2", session=db)
        assert result["success"] is True
        assert result["effective_price_chf"] == 39.0   # 49 - 10

    def test_apply_invalid_code(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        result = eng.apply_promo("NOTREAL", "pro", org_id="org3", session=db)
        assert result["success"] is False

    def test_apply_expired_promo(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        past = datetime.utcnow() - timedelta(days=1)
        eng.create_promo(db, code="OLDCODE", discount_type="pct",
                          discount_value=20, expires_at=past)
        result = eng.apply_promo("OLDCODE", "pro", org_id="org4", session=db)
        assert result["success"] is False
        assert "expired" in result["error"]

    def test_apply_max_uses_reached(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        promo = eng.create_promo(db, code="ONESHOT", discount_type="pct",
                                  discount_value=10, max_uses=1)
        promo.used_count = 1
        db.commit()
        result = eng.apply_promo("ONESHOT", "pro", org_id="org5", session=db)
        assert result["success"] is False
        assert "limit" in result["error"]

    def test_apply_wrong_tier(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        eng.create_promo(db, code="ENTONLY", discount_type="pct",
                          discount_value=10, applicable_tiers="enterprise")
        result = eng.apply_promo("ENTONLY", "pro", org_id="org6", session=db)
        assert result["success"] is False

    def test_set_org_override(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        override = eng.set_org_override(db, "bigcorp", "team", 99.0, note="Annual deal")
        assert override.custom_price_chf == 99.0
        assert override.note == "Annual deal"

    def test_set_org_override_updates_existing(self, db):
        from kelpmesh_studio.pricing import PricingEngine
        eng = PricingEngine()
        eng.set_org_override(db, "acme", "pro", 30.0)
        eng.set_org_override(db, "acme", "pro", 20.0, note="Renegotiated")
        result = eng.resolve_price("pro", org_id="acme", session=db)
        assert result["effective_price_chf"] == 20.0


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_add_member(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        member = mgr.add_member("org1", "alice@kelpmesh.dev", "editor", invited_by="owner@kelpmesh.dev")
        assert member.role == "editor"

    def test_get_role(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "bob@kelpmesh.dev", "admin")
        assert mgr.get_role("org1", "bob@kelpmesh.dev") == "admin"
        assert mgr.get_role("org1", "unknown@kelpmesh.dev") is None

    def test_has_permission(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "alice@kelpmesh.dev", "editor")
        assert mgr.has_permission("org1", "alice@kelpmesh.dev", "run_models")
        assert mgr.has_permission("org1", "alice@kelpmesh.dev", "edit_models")
        assert not mgr.has_permission("org1", "alice@kelpmesh.dev", "manage_users")

    def test_viewer_limited_permissions(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "viewer@kelpmesh.dev", "viewer")
        assert mgr.has_permission("org1", "viewer@kelpmesh.dev", "view_projects")
        assert not mgr.has_permission("org1", "viewer@kelpmesh.dev", "run_models")

    def test_owner_all_permissions(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "owner@kelpmesh.dev", "owner")
        for perm in ["view_projects", "run_models", "manage_users", "manage_pricing"]:
            assert mgr.has_permission("org1", "owner@kelpmesh.dev", perm)

    def test_update_role(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "user@kelpmesh.dev", "viewer")
        assert mgr.update_role("org1", "user@kelpmesh.dev", "editor")
        assert mgr.get_role("org1", "user@kelpmesh.dev") == "editor"

    def test_remove_member(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "ex@kelpmesh.dev", "viewer")
        assert mgr.remove_member("org1", "ex@kelpmesh.dev")
        assert mgr.get_role("org1", "ex@kelpmesh.dev") is None

    def test_list_members(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        mgr.add_member("org1", "a@kelpmesh.dev", "admin")
        mgr.add_member("org1", "b@kelpmesh.dev", "editor")
        members = mgr.list_members("org1")
        assert len(members) == 2

    def test_invalid_role_raises(self, db):
        from kelpmesh_studio.rbac import RBACManager
        mgr = RBACManager(db)
        with pytest.raises(ValueError):
            mgr.add_member("org1", "x@kelpmesh.dev", "superadmin")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_log_event(self, db):
        from kelpmesh_studio.audit import AuditLogger
        logger = AuditLogger(db)
        event = logger.log("user@kelpmesh.dev", "run_models", resource="project:myproj", ip_address="1.2.3.4")
        assert event.id is not None
        assert event.action == "run_models"

    def test_query_by_user(self, db):
        from kelpmesh_studio.audit import AuditLogger
        logger = AuditLogger(db)
        logger.log("alice@kelpmesh.dev", "edit_model")
        logger.log("bob@kelpmesh.dev", "run_models")
        events = logger.query(user_email="alice@kelpmesh.dev")
        assert len(events) == 1
        assert events[0].user_email == "alice@kelpmesh.dev"

    def test_query_by_action(self, db):
        from kelpmesh_studio.audit import AuditLogger
        logger = AuditLogger(db)
        logger.log("u@kelpmesh.dev", "run_models")
        logger.log("u@kelpmesh.dev", "edit_model")
        events = logger.query(action="run_models")
        assert all(e.action == "run_models" for e in events)

    def test_count(self, db):
        from kelpmesh_studio.audit import AuditLogger
        logger = AuditLogger(db)
        for i in range(5):
            logger.log(f"u{i}@kelpmesh.dev", "login")
        assert logger.count() == 5

    def test_pagination(self, db):
        from kelpmesh_studio.audit import AuditLogger
        logger = AuditLogger(db)
        for i in range(10):
            logger.log("u@kelpmesh.dev", f"action_{i}")
        page1 = logger.query(limit=5, offset=0)
        page2 = logger.query(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        assert {e.action for e in page1}.isdisjoint({e.action for e in page2})


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class TestAPIKeys:
    def test_create_key(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        record, raw = mgr.create("org1", "CI Pipeline", created_by="admin@kelpmesh.dev")
        assert raw.startswith("bsk_")
        assert record.key_prefix == raw[:12]
        assert record.active

    def test_verify_key(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        record, raw = mgr.create("org1", "test key", created_by="admin@kelpmesh.dev")
        found = mgr.verify(raw, org_id="org1")
        assert found is not None
        assert found.name == "test key"

    def test_verify_wrong_key(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        mgr.create("org1", "key1", created_by="admin@kelpmesh.dev")
        assert mgr.verify("bsk_wrongkey123") is None

    def test_verify_expired_key(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        past = datetime.utcnow() - timedelta(days=1)
        record, raw = mgr.create("org1", "expired", created_by="admin@kelpmesh.dev", expires_at=past)
        assert mgr.verify(raw) is None

    def test_revoke_key(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        record, raw = mgr.create("org1", "temp key", created_by="admin@kelpmesh.dev")
        assert mgr.revoke(record.id, "org1")
        assert mgr.verify(raw) is None

    def test_list_keys(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        mgr.create("org1", "key-a", created_by="admin@kelpmesh.dev")
        mgr.create("org1", "key-b", created_by="admin@kelpmesh.dev")
        keys = mgr.list_keys("org1")
        assert len(keys) == 2

    def test_has_scope(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager
        mgr = APIKeyManager(db)
        record, _ = mgr.create("org1", "read-only", created_by="admin@kelpmesh.dev", scopes="read")
        assert mgr.has_scope(record, "read")
        assert not mgr.has_scope(record, "run")

    def test_raw_value_not_stored(self, db):
        from kelpmesh_studio.api_keys import APIKeyManager, _hash_key
        mgr = APIKeyManager(db)
        record, raw = mgr.create("org1", "k", created_by="admin@kelpmesh.dev")
        assert record.key_hash != raw
        assert record.key_hash == _hash_key(raw)


# ---------------------------------------------------------------------------
# Git Sync
# ---------------------------------------------------------------------------

class TestGitSync:
    def test_connect_repo(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        repo = mgr.connect("my_project", "https://github.com/acme/data.git", branch="main")
        assert repo.remote_url == "https://github.com/acme/data.git"
        assert repo.branch == "main"
        assert repo.webhook_secret is not None

    def test_connect_generates_unique_secrets(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        r1 = mgr.connect("proj_a", "https://github.com/acme/a.git")
        r2 = mgr.connect("proj_b", "https://github.com/acme/b.git")
        assert r1.webhook_secret != r2.webhook_secret

    def test_get_repo(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        mgr.connect("proj", "https://github.com/acme/repo.git")
        repo = mgr.get("proj")
        assert repo is not None

    def test_disconnect_repo(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        mgr.connect("proj", "https://github.com/acme/repo.git")
        assert mgr.disconnect("proj")
        assert mgr.get("proj") is None

    def test_verify_github_signature(self, db):
        import hashlib, hmac as hmac_mod
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        secret = "mysecret"
        payload = b'{"ref":"refs/heads/main"}'
        sig = "sha256=" + hmac_mod.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert mgr.verify_github_signature(payload, sig, secret)
        assert not mgr.verify_github_signature(payload, "sha256=badsig", secret)

    def test_verify_gitlab_token(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        assert mgr.verify_gitlab_token("mysecret", "mysecret")
        assert not mgr.verify_gitlab_token("wrong", "mysecret")

    def test_parse_github_push_event(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        payload = {"ref": "refs/heads/main", "after": "abc123", "pusher": {"name": "RoyPulseAI"}}
        result = mgr.parse_push_event(payload, "github")
        assert result["branch"] == "main"
        assert result["sha"] == "abc123"
        assert result["pusher"] == "RoyPulseAI"

    def test_parse_gitlab_push_event(self, db):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        payload = {"ref": "refs/heads/develop", "after": "def456", "user_name": "analyst"}
        result = mgr.parse_push_event(payload, "gitlab")
        assert result["branch"] == "develop"
        assert result["pusher"] == "analyst"

    def test_sync_no_git_configured(self, db, tmp_path):
        from kelpmesh_studio.git_sync import GitSyncManager
        mgr = GitSyncManager(db)
        result = mgr.sync("nonexistent", tmp_path)
        assert result["success"] is False
        assert "No git repo" in result["error"]

    def test_sync_no_git_binary(self, db, tmp_path):
        from kelpmesh_studio.git_sync import GitSyncManager
        import subprocess
        mgr = GitSyncManager(db)
        mgr.connect("test_proj", "https://github.com/acme/data.git")
        proj_path = tmp_path / "test_proj"
        proj_path.mkdir()

        orig_run = subprocess.run
        def mock_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")
        with patch("kelpmesh_studio.git_sync.subprocess.run", side_effect=FileNotFoundError("git")):
            result = mgr.sync("test_proj", proj_path)
        assert result["success"] is False
        assert "git not found" in result["error"]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_add_slack_channel(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher
        disp = AlertDispatcher(db)
        ch = disp.add_channel("org1", "DataTeam", "slack",
                               {"webhook_url": "https://hooks.slack.com/test"})
        assert ch.id is not None
        assert ch.channel_type == "slack"

    def test_add_webhook_channel(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher
        disp = AlertDispatcher(db)
        ch = disp.add_channel("org1", "PagerDuty", "webhook",
                               {"url": "https://events.pagerduty.com/v2/enqueue"})
        assert ch.channel_type == "webhook"

    def test_remove_channel(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher
        disp = AlertDispatcher(db)
        ch = disp.add_channel("org1", "temp", "webhook", {"url": "http://test"})
        assert disp.remove_channel(ch.id, "org1")
        assert disp.list_channels("org1") == []

    def test_list_channels(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher
        disp = AlertDispatcher(db)
        disp.add_channel("org1", "ch1", "slack", {"webhook_url": "http://a"})
        disp.add_channel("org1", "ch2", "webhook", {"url": "http://b"})
        assert len(disp.list_channels("org1")) == 2

    def test_dispatch_only_subscribed_events(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher, AlertChannel
        disp = AlertDispatcher(db)
        disp.add_channel("org1", "failures only", "webhook",
                         {"url": "http://test"},
                         events="run_failed")
        # Mock the actual HTTP call
        with patch.object(disp, "_send_webhook", return_value=(True, "ok")) as mock_send:
            results = disp.dispatch("org1", "run_failed", "Run failed", "Model X failed")
            assert len(results) == 1
            assert results[0]["ok"] is True

        with patch.object(disp, "_send_webhook", return_value=(True, "ok")) as mock_send:
            results = disp.dispatch("org1", "sla_breach", "SLA breach", "Model Y slow")
            assert results == []   # not subscribed to sla_breach

    def test_dispatch_wildcard_events(self, db):
        from kelpmesh_studio.alerts import AlertDispatcher
        disp = AlertDispatcher(db)
        disp.add_channel("org1", "all events", "webhook",
                         {"url": "http://test"},
                         events="*")
        with patch.object(disp, "_send_webhook", return_value=(True, "ok")):
            results = disp.dispatch("org1", "anything", "Title", "Body")
            assert len(results) == 1


# ---------------------------------------------------------------------------
# SLA Monitoring
# ---------------------------------------------------------------------------

class TestSLA:
    def test_set_sla(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        cfg = mgr.set_sla("org1", "my_project", "fct_orders", expected_seconds=60.0)
        assert cfg.expected_seconds == 60.0

    def test_no_breach(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "orders", expected_seconds=60.0)
        result = mgr.check("org1", "proj", "orders", actual_seconds=45.0)
        assert result["breach"] is False
        assert result["sla_configured"] is True

    def test_breach_detected(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "orders", expected_seconds=30.0)
        result = mgr.check("org1", "proj", "orders", actual_seconds=45.0)
        assert result["breach"] is True
        assert result["overage_seconds"] == 15.0

    def test_fallback_to_wildcard(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "*", expected_seconds=120.0)
        result = mgr.check("org1", "proj", "any_model", actual_seconds=150.0)
        assert result["breach"] is True

    def test_no_sla_configured(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        result = mgr.check("org1", "proj", "unconfigured_model", actual_seconds=999.0)
        assert result["breach"] is False
        assert result["sla_configured"] is False

    def test_remove_sla(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "model", expected_seconds=30.0)
        assert mgr.remove_sla("org1", "proj", "model")
        result = mgr.check("org1", "proj", "model", actual_seconds=99.0)
        assert result["sla_configured"] is False

    def test_list_slas(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "a", expected_seconds=30.0)
        mgr.set_sla("org1", "proj", "b", expected_seconds=60.0)
        slas = mgr.list_slas("org1", project_name="proj")
        assert len(slas) == 2

    def test_batch_report(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "fast_model", expected_seconds=10.0)
        mgr.set_sla("org1", "proj", "slow_model", expected_seconds=30.0)
        durations = {"fast_model": 8.0, "slow_model": 45.0, "unconfigured": 5.0}
        report = mgr.report("org1", "proj", durations)
        assert len(report) == 2
        breached = [r for r in report if r["breach"]]
        assert len(breached) == 1
        assert breached[0]["model"] == "slow_model"

    def test_update_sla_value(self, db):
        from kelpmesh_studio.sla import SLAManager
        mgr = SLAManager(db)
        mgr.set_sla("org1", "proj", "model", expected_seconds=30.0)
        mgr.set_sla("org1", "proj", "model", expected_seconds=90.0)
        cfg = mgr.get_sla("org1", "proj", "model")
        assert cfg.expected_seconds == 90.0


# ---------------------------------------------------------------------------
# billing.py backward compatibility
# ---------------------------------------------------------------------------

class TestBillingCompat:
    def test_tiers_exist(self):
        from kelpmesh_studio.billing import TIERS
        for name in ("free", "pro", "business", "enterprise"):
            assert name in TIERS

    def test_free_tier(self):
        from kelpmesh_studio.billing import TIERS
        assert TIERS["free"].price_monthly_usd == 0
        assert TIERS["free"].max_users == 1

    def test_pro_price_updated(self):
        from kelpmesh_studio.billing import TIERS
        assert TIERS["pro"].price_monthly_usd == 29

    def test_enterprise_price_updated(self):
        from kelpmesh_studio.billing import TIERS
        assert TIERS["enterprise"].price_monthly_usd == -1

    def test_allowed_models_unlimited(self):
        from kelpmesh_studio.billing import allowed_models
        assert allowed_models("pro", 10000)     # 0 = unlimited
        assert allowed_models("enterprise", 99999)

    def test_allowed_models_limited(self):
        from kelpmesh_studio.billing import allowed_models
        assert allowed_models("free", 1)        # free has 3 max_projects
        assert allowed_models("free", 3)
        assert not allowed_models("free", 4)
