"""Phase E — Studio ship tests."""
import json
import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch


# ── Studio Config ───────────────────────────────────────────────────

class TestStudioConfig:
    def test_default_config(self):
        from briq_studio.config import StudioConfig
        cfg = StudioConfig()
        assert cfg.data_dir.exists()
        assert cfg.database_url.startswith("sqlite")
        assert cfg.jwt_secret == "dev-secret-change-in-production"
        assert cfg.jwt_algorithm == "HS256"
        assert cfg.jwt_expire_minutes == 1440
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8765

    def test_config_from_env(self):
        with patch.dict(os.environ, {
            "BRIQ_STUDIO_DATABASE_URL": "postgresql://user:pass@localhost:5432/briq",
            "BRIQ_STUDIO_JWT_SECRET": "super-secret",
            "BRIQ_STUDIO_HOST": "127.0.0.1",
            "BRIQ_STUDIO_PORT": "8080",
            "BRIQ_STUDIO_JWT_EXPIRE": "60",
        }, clear=False):
            from briq_studio.config import StudioConfig
            cfg = StudioConfig()
            assert cfg.database_url == "postgresql://user:pass@localhost:5432/briq"
            assert cfg.jwt_secret == "super-secret"
            assert cfg.host == "127.0.0.1"
            assert cfg.port == 8080
            assert cfg.jwt_expire_minutes == 60
            assert cfg.is_postgres()

    def test_config_is_postgres(self):
        from briq_studio.config import StudioConfig
        cfg = StudioConfig()
        cfg.database_url = "postgresql://localhost/db"
        assert cfg.is_postgres()
        cfg.database_url = "sqlite:///test.db"
        assert not cfg.is_postgres()

    def test_config_db_connect_args(self):
        from briq_studio.config import StudioConfig
        cfg = StudioConfig()
        cfg.database_url = "sqlite:///test.db"
        assert cfg.db_connect_args == {"check_same_thread": False}
        cfg.database_url = "postgresql://localhost/db"
        assert cfg.db_connect_args == {}

    def test_config_data_dir_override(self):
        with patch.dict(os.environ, {"BRIQ_STUDIO_DATA": "/tmp/briq_studio_test"}, clear=False):
            from briq_studio.config import StudioConfig
            cfg = StudioConfig()
            assert str(cfg.data_dir) == "/tmp/briq_studio_test"


# ── Auth ────────────────────────────────────────────────────────────

class TestAuth:
    def test_hash_and_verify(self):
        from briq_studio.auth import hash_password, verify_password
        pw = "test_password_123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)
        assert not verify_password("wrong", hashed)

    def test_create_and_decode_token(self):
        from briq_studio.auth import create_token, decode_token
        secret = "test-secret"
        token = create_token("user@test.com", "admin", secret, "HS256", 60)
        assert token
        data = decode_token(token, secret, "HS256")
        assert data is not None
        assert data.email == "user@test.com"
        assert data.role == "admin"

    def test_decode_invalid_token(self):
        from briq_studio.auth import decode_token
        assert decode_token("invalid-token", "secret", "HS256") is None

    def test_decode_expired_token(self):
        from briq_studio.auth import create_token, decode_token
        token = create_token("user@test.com", "viewer", "secret", "HS256", -1)
        data = decode_token(token, "secret", "HS256")
        assert data is None

    def test_decode_wrong_secret(self):
        from briq_studio.auth import create_token, decode_token
        token = create_token("user@test.com", "admin", "secret1", "HS256", 60)
        data = decode_token(token, "secret2", "HS256")
        assert data is None

    def test_api_key_hash_unique(self):
        from briq_studio.auth import api_key_hash
        key1 = api_key_hash()
        key2 = api_key_hash()
        assert len(key1) == 64
        assert key1 != key2


# ── Studio App routes ───────────────────────────────────────────────

class TestStudioApp:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from briq_studio.server import create_app
        app = create_app()
        return TestClient(app)

    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_auth_signup_and_login(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "test@briq.dev",
            "name": "Test User",
            "password": "securepass123",
        })
        assert signup_resp.status_code == 200
        data = signup_resp.json()
        assert "token" in data
        assert data["email"] == "test@briq.dev"
        assert data["role"] == "admin"

        login_resp = client.post("/api/auth/login", json={
            "email": "test@briq.dev",
            "password": "securepass123",
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert "token" in login_data
        assert login_data["email"] == "test@briq.dev"

    def test_auth_signup_duplicate(self, client):
        client.post("/api/auth/signup", json={
            "email": "dup@briq.dev", "name": "Dup", "password": "pass"
        })
        resp = client.post("/api/auth/signup", json={
            "email": "dup@briq.dev", "name": "Dup", "password": "pass"
        })
        assert resp.status_code == 409

    def test_auth_login_wrong_password(self, client):
        client.post("/api/auth/signup", json={
            "email": "wrong@briq.dev", "name": "Wrong", "password": "correct"
        })
        resp = client.post("/api/auth/login", json={
            "email": "wrong@briq.dev", "password": "incorrect"
        })
        assert resp.status_code == 401

    def test_me_endpoint_requires_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_endpoint_with_token(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "me@briq.dev", "name": "Me", "password": "pass"
        })
        token = signup_resp.json()["token"]
        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "me@briq.dev"
        assert data["name"] == "Me"

    def test_create_project(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "project@briq.dev", "name": "Project", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/projects", json={"name": "test-proj"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-proj"

    def test_list_projects(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "list@briq.dev", "name": "List", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/api/projects", json={"name": "proj-a"}, headers=headers)
        client.post("/api/projects", json={"name": "proj-b"}, headers=headers)
        resp = client.get("/api/projects", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        names = [p["name"] for p in data]
        assert "proj-a" in names
        assert "proj-b" in names

    def test_get_project_with_models(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "models@briq.dev", "name": "Models", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/api/projects", json={"name": "model-proj"}, headers=headers)
        resp = client.get("/api/projects/model-proj", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "model-proj"
        assert "models" in data

    def test_create_and_get_model(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "crud@briq.dev", "name": "CRUD", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/api/projects", json={"name": "crud-proj"}, headers=headers)
        put_resp = client.put(
            "/api/projects/crud-proj/models/test_model",
            json={"sql": "SELECT 1 AS id"},
            headers=headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["version"] == 1

        get_resp = client.get(
            "/api/projects/crud-proj/models/test_model", headers=headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "test_model"

    def test_model_versioning(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "ver@briq.dev", "name": "Ver", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/api/projects", json={"name": "ver-proj"}, headers=headers)
        client.put(
            "/api/projects/ver-proj/models/m",
            json={"sql": "SELECT 1 AS v1"},
            headers=headers,
        )
        client.put(
            "/api/projects/ver-proj/models/m",
            json={"sql": "SELECT 2 AS v2"},
            headers=headers,
        )

        resp = client.get(
            "/api/projects/ver-proj/models/m/versions", headers=headers
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2

    def test_schedule_crud(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "sched@briq.dev", "name": "Sched", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post(
            "/api/schedules/test-proj",
            json={"cron": "0 */6 * * *", "depends_on": ["upstream"], "enabled": True},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/schedules", headers=headers)
        assert resp.status_code == 200
        schedules = resp.json()
        matching = [s for s in schedules if s["project"] == "test-proj"]
        assert len(matching) == 1
        assert matching[0]["cron"] == "0 */6 * * *"
        assert matching[0]["enabled"]

        resp = client.delete("/api/schedules/test-proj", headers=headers)
        assert resp.status_code == 200

    def test_schedule_update(self, client):
        signup_resp = client.post("/api/auth/signup", json={
            "email": "upd@briq.dev", "name": "Upd", "password": "pass"
        })
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/api/schedules/proj", json={"cron": "0 0 * * *", "depends_on": [], "enabled": True}, headers=headers)
        client.post("/api/schedules/proj", json={"cron": "0 */12 * * *", "depends_on": [], "enabled": True}, headers=headers)

        resp = client.get("/api/schedules", headers=headers)
        schedules = resp.json()
        matching = [s for s in schedules if s["project"] == "proj"]
        assert matching[0]["cron"] == "0 */12 * * *"


# ── Billing tiers ──────────────────────────────────────────────────

class TestBilling:
    def test_tiers_exist(self):
        from briq_studio.billing import TIERS
        for name in ["free", "pro", "team", "enterprise"]:
            assert name in TIERS, f"Missing tier: {name}"

    def test_free_tier_limits(self):
        from briq_studio.billing import TIERS
        free = TIERS["free"]
        assert free.price_monthly_chf == 0
        assert free.max_users == 1
        assert free.max_models == 20

    def test_allowed_models(self):
        from briq_studio.billing import allowed_models
        assert allowed_models("free", 5)
        assert not allowed_models("free", 25)
        assert allowed_models("enterprise", 5000)
        assert allowed_models("pro", 50)

    def test_get_tier(self):
        from briq_studio.billing import get_tier
        assert get_tier("free") is not None
        assert get_tier("nonexistent") is None


# ── Scheduler ───────────────────────────────────────────────────────

class TestScheduler:
    def test_scheduler_list_empty(self):
        from briq_studio.scheduler import list_schedules
        assert list_schedules() == []

    def test_scheduler_dependencies_satisfied_no_schedule(self):
        from briq_studio.scheduler import dependencies_satisfied
        result = dependencies_satisfied("nonexistent")
        assert result["project"] == "nonexistent"
        assert result["dependencies"] == []
        assert result["all_satisfied"]
