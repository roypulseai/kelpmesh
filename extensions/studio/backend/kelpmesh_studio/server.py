"""kelpmesh Studio backend — FastAPI server with SQLite + JWT auth."""
import os
import secrets
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

from kelpmesh_studio.config import StudioConfig
from kelpmesh_studio.auth import (
    hash_password, verify_password, create_token, api_key_hash,
    get_current_user, require_role,
)
from kelpmesh_studio.db import Base  # noqa – re-exported; tests import Base from server


class ProjectModel(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    path = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=sa.func.now())


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(Integer, primary_key=True)
    project_name = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    sql = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=sa.func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)
    role = Column(String, default="viewer")
    api_key = Column(String, unique=True)
    created_at = Column(DateTime, server_default=sa.func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True)
    user_email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=sa.func.now())


class RunLog(Base):
    __tablename__ = "run_history"
    id = Column(Integer, primary_key=True)
    project_name = Column(String, nullable=False)
    success = Column(Integer, nullable=False)
    models_ran = Column(Integer, default=0)
    models_failed = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=sa.func.now())


class ScheduleEntry(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    project_name = Column(String, unique=True, nullable=False)
    cron = Column(String, default="")
    depends_on = Column(JSON, default=list)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=sa.func.now())


def create_app() -> FastAPI:
    import kelpmesh_studio.pricing as _pricing_mod
    import kelpmesh_studio.rbac as _rbac_mod
    import kelpmesh_studio.audit as _audit_mod
    import kelpmesh_studio.api_keys as _apikey_mod
    import kelpmesh_studio.git_sync as _git_mod
    import kelpmesh_studio.alerts as _alerts_mod
    import kelpmesh_studio.sla as _sla_mod

    cfg = StudioConfig()
    engine = create_engine(cfg.database_url, connect_args=cfg.db_connect_args)
    Base.metadata.create_all(engine)
    # Create tables for all Pro modules (shared Base — idempotent)
    for mod in (_pricing_mod, _rbac_mod, _audit_mod, _apikey_mod, _git_mod, _alerts_mod, _sla_mod):
        mod.create_tables(engine)
    Session = sessionmaker(bind=engine)

    app = FastAPI(title="kelpmesh Studio", version="0.2.0")
    app.state.config = cfg
    app.state.engine = engine
    app.state.Session = Session

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    _register_routes(app)
    return app


def get_db_session(request: Request):
    return request.app.state.Session()


# ── Schemas ─────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str


class ModelUpdate(BaseModel):
    sql: str


class RunRequest(BaseModel):
    models: Optional[list[str]] = None
    select: Optional[list[str]] = None
    full_refresh: bool = False
    env: Optional[str] = None


class TestRequest(BaseModel):
    model: Optional[str] = None


class PreviewRequest(BaseModel):
    sql: Optional[str] = None
    limit: int = 100


class ScheduleCreate(BaseModel):
    cron: str = ""
    depends_on: list[str] = []
    enabled: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    name: str
    password: str


class UserCreate(BaseModel):
    email: str
    name: str
    role: str = "viewer"


# ── Routes ──────────────────────────────────────────────────────────

def _register_routes(app: FastAPI):

    # ── Health ──

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    # ── Auth ──

    @app.post("/api/auth/signup")
    def signup(body: SignupRequest):
        session = app.state.Session()
        existing = session.query(User).filter_by(email=body.email).first()
        if existing:
            session.close()
            raise HTTPException(409, "User already exists")
        user = User(
            email=body.email,
            name=body.name,
            password_hash=hash_password(body.password),
            role="admin",
            api_key=api_key_hash(),
        )
        session.add(user)
        session.commit()
        token = create_token(
            user.email, user.role,
            app.state.config.jwt_secret,
            app.state.config.jwt_algorithm,
            app.state.config.jwt_expire_minutes,
        )
        session.close()
        return {"token": token, "email": user.email, "name": user.name, "role": user.role}

    @app.post("/api/auth/login")
    def login(body: LoginRequest):
        session = app.state.Session()
        user = session.query(User).filter_by(email=body.email).first()
        session.close()
        if not user or not user.password_hash:
            raise HTTPException(401, "Invalid email or password")
        if not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")
        token = create_token(
            user.email, user.role,
            app.state.config.jwt_secret,
            app.state.config.jwt_algorithm,
            app.state.config.jwt_expire_minutes,
        )
        return {"token": token, "email": user.email, "name": user.name, "role": user.role}

    @app.get("/api/auth/me")
    def me(current_user=Depends(require_role("viewer"))):
        return {
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
        }

    # ── Projects ──

    @app.get("/api/projects")
    def list_projects():
        session = app.state.Session()
        rows = session.query(ProjectModel).all()
        session.close()
        return [{"id": r.id, "name": r.name, "path": r.path, "created_at": str(r.created_at)} for r in rows]

    @app.post("/api/projects")
    def create_project(body: ProjectCreate):
        data_dir = app.state.config.data_dir
        project_path = data_dir / body.name
        briq_path = project_path / "kelpmesh.yml"
        if briq_path.exists():
            raise HTTPException(409, f"Project '{body.name}' already exists")
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "models").mkdir(exist_ok=True)
        (project_path / "tests").mkdir(exist_ok=True)
        from kelpmesh.core.config import ProjectConfig
        config = ProjectConfig(name=body.name)
        config.save(project_path)
        session = app.state.Session()
        row = ProjectModel(name=body.name, path=str(project_path))
        session.add(row)
        session.commit()
        session.close()
        return {"name": body.name, "path": str(project_path)}

    @app.get("/api/projects/{name}")
    def get_project(name: str):
        project = _get_project(app.state, name)
        return {
            "name": project.config.name,
            "model_names": sorted(project.models.keys()),
            "models": [
                {
                    "name": m.name,
                    "materialized": m.materialized,
                    "upstream": sorted(m.upstream),
                    "downstream": sorted(m.downstream),
                    "path": str(m.file_path.relative_to(project.path)) if m.file_path else None,
                }
                for m in project.models.values()
            ],
        }

    @app.delete("/api/projects/{name}")
    def delete_project(name: str, current_user=Depends(require_role("admin"))):
        import shutil
        session = app.state.Session()
        row = session.query(ProjectModel).filter_by(name=name).first()
        if not row:
            session.close()
            raise HTTPException(404, f"Project '{name}' not found")
        project_path = Path(row.path)
        if project_path.exists():
            shutil.rmtree(project_path, ignore_errors=True)
        session.query(ModelVersion).filter_by(project_name=name).delete()
        session.query(RunLog).filter_by(project_name=name).delete()
        session.query(ScheduleEntry).filter_by(project_name=name).delete()
        session.delete(row)
        session.commit()
        session.close()
        return {"deleted": name}

    # ── Models ──

    @app.get("/api/projects/{name}/models/{model_name}")
    def get_model(name: str, model_name: str):
        project = _get_project(app.state, name)
        model = project.get_model(model_name)
        if not model:
            raise HTTPException(404, f"Model '{model_name}' not found")
        return {
            "name": model.name,
            "sql": model.sql,
            "materialized": model.materialized,
            "upstream": sorted(model.upstream),
            "downstream": sorted(model.downstream),
            "columns": model.columns,
            "path": str(model.file_path),
        }

    @app.put("/api/projects/{name}/models/{model_name}")
    def update_model(name: str, model_name: str, body: ModelUpdate):
        project = _get_project(app.state, name)
        model = project.get_model(model_name)
        if not model:
            files = list((project.path / "models").glob("*.sql"))
            existing = {f.stem: f for f in files}
            model_path = existing.get(model_name) or project.path / "models" / f"{model_name}.sql"
        else:
            model_path = model.file_path

        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(body.sql, encoding="utf-8")

        session = app.state.Session()
        last = session.query(ModelVersion).filter_by(
            project_name=name, model_name=model_name
        ).order_by(ModelVersion.version.desc()).first()
        version = (last.version + 1) if last else 1
        row = ModelVersion(project_name=name, model_name=model_name, sql=body.sql, version=version)
        session.add(row)
        session.commit()
        session.close()
        return {"name": model_name, "version": version}

    @app.get("/api/projects/{name}/models/{model_name}/versions")
    def list_versions(name: str, model_name: str):
        session = app.state.Session()
        rows = session.query(ModelVersion).filter_by(
            project_name=name, model_name=model_name
        ).order_by(ModelVersion.version.desc()).all()
        session.close()
        return [{"version": r.version, "sql": r.sql, "created_at": str(r.created_at)} for r in rows]

    @app.get("/api/projects/{name}/models/{model_name}/versions/{version}")
    def get_version(name: str, model_name: str, version: int):
        session = app.state.Session()
        row = session.query(ModelVersion).filter_by(
            project_name=name, model_name=model_name, version=version
        ).first()
        session.close()
        if not row:
            raise HTTPException(404, f"Version {version} not found")
        return {"version": row.version, "sql": row.sql, "created_at": str(row.created_at)}

    # ── Lineage ──

    @app.get("/api/projects/{name}/lineage")
    def get_lineage(name: str):
        project = _get_project(app.state, name)
        nodes = [
            {
                "id": m.name,
                "label": m.name,
                "materialized": m.materialized,
                "upstream_count": len(m.upstream),
                "downstream_count": len(m.downstream),
            }
            for m in project.models.values()
        ]
        edges = []
        for m in project.models.values():
            for u in m.upstream:
                edges.append({"from": u, "to": m.name})
        return {"nodes": nodes, "edges": edges}

    # ── Run ──

    @app.post("/api/projects/{name}/run")
    def run_project(name: str, body: RunRequest):
        from kelpmesh.core.project import Project
        from kelpmesh.core.executor import Executor
        from kelpmesh.state.engine import StateEngine
        from kelpmesh.adapters import get_adapter
        from kelpmesh.core.schema_yaml import SchemaYaml
        from kelpmesh.observability.history import RunHistory as BriqRunHistory

        project = _get_project(app.state, name)
        adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
        state = StateEngine(project.path)
        if body.full_refresh:
            state.reset()

        schema_yaml = SchemaYaml(project.path)
        run_hist = BriqRunHistory(project.path)
        executor = Executor(
            project, adapter, state,
            schema_yaml=schema_yaml,
            run_history=run_hist,
            env=body.env,
        )
        results = executor.run(models=body.models, select=body.select)
        run_hist.close()
        adapter.disconnect()
        state.close()

        ran = results.get("success", [])
        failed = results.get("failed", [])
        skipped = results.get("skipped", [])
        success = len(failed) == 0

        session = app.state.Session()
        row = RunLog(
            project_name=name,
            success=1 if success else 0,
            models_ran=len(ran),
            models_failed=len(failed),
        )
        session.add(row)
        session.commit()
        session.close()

        return {
            "success": success,
            "ran": len(ran),
            "skipped": len(skipped),
            "failed": len(failed),
            "results": {
                "success": ran,
                "failed": failed,
                "skipped": skipped,
            },
        }

    @app.get("/api/projects/{name}/runs")
    def get_run_history(name: str, limit: int = 20):
        session = app.state.Session()
        rows = session.query(RunLog).filter_by(
            project_name=name
        ).order_by(RunLog.created_at.desc()).limit(limit).all()
        session.close()
        return [
            {
                "id": r.id,
                "success": bool(r.success),
                "models_ran": r.models_ran,
                "models_failed": r.models_failed,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]

    # ── Preview ──

    @app.post("/api/projects/{name}/preview/{model_name}")
    def preview_model(name: str, model_name: str, body: PreviewRequest):
        from kelpmesh.adapters import get_adapter

        project = _get_project(app.state, name)

        sql = body.sql
        if not sql:
            model = project.get_model(model_name)
            if not model:
                raise HTTPException(404, f"Model '{model_name}' not found")
            sql = model.sql

        limit = max(1, min(body.limit, 500))
        preview_sql = f"SELECT * FROM ({sql}) __preview LIMIT {limit}"

        adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
        try:
            adapter.connect()
            row_dicts = adapter.execute(preview_sql)
        except Exception as exc:
            adapter.disconnect()
            raise HTTPException(400, str(exc))
        adapter.disconnect()

        columns = list(row_dicts[0].keys()) if row_dicts else []
        rows = [list(r.values()) for r in row_dicts]

        return {
            "model": model_name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }

    # ── Tests ──

    @app.post("/api/projects/{name}/test")
    def test_project(name: str, body: TestRequest):
        from kelpmesh.adapters import get_adapter
        from kelpmesh.testing.runner import TestRunner
        from kelpmesh.core.schema_yaml import SchemaYaml
        from kelpmesh.testing.schema_tests import SchemaTestGenerator

        project = _get_project(app.state, name)
        adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
        try:
            adapter.connect()
        except Exception as exc:
            raise HTTPException(400, f"Could not connect to warehouse: {exc}")

        schema_yaml = SchemaYaml(project.path)
        gen = SchemaTestGenerator(schema_yaml)

        test_dir = project.path / "tests"
        test_files = list(test_dir.glob("*.sql")) if test_dir.exists() else []
        if body.model:
            test_files = [f for f in test_files if body.model in f.stem]

        schema_tests = []
        target_models = [body.model] if body.model else list(project.models.keys())
        for model_name in target_models:
            model = project.get_model(model_name)
            if model:
                schema_tests.extend(gen.generate(model_name, model.name))

        runner = TestRunner(adapter, project.path)
        report = runner.run_all(test_files=test_files, schema_tests=schema_tests or None)
        adapter.disconnect()

        return {
            "passed": report.passed,
            "failed": report.failed,
            "total": report.total,
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "failures": r.failures,
                    "error": r.error,
                }
                for r in report.results
            ],
        }

    # ── Health / anomalies ──

    @app.get("/api/projects/{name}/health")
    def project_health(name: str):
        from kelpmesh.observability.history import RunHistory as BriqRunHistory
        from kelpmesh.observability.anomaly import check_row_count_anomaly

        project = _get_project(app.state, name)
        run_hist = BriqRunHistory(project.path)

        alerts = []
        for model_name in project.models:
            history = run_hist.rolling_row_counts(model_name, n=7)
            recent = run_hist.get_history(model_name=model_name, limit=1)
            if recent:
                current_count = recent[0].get("row_count") or 0
                alert = check_row_count_anomaly(model_name, current_count, history)
                if alert:
                    alerts.append({
                        "model": alert.model_name,
                        "level": alert.level,
                        "message": alert.message,
                        "current": alert.current_count,
                        "baseline": alert.baseline,
                        "deviation_pct": round(alert.deviation * 100, 1),
                    })
        run_hist.close()

        last_runs = []
        session = app.state.Session()
        rows = session.query(RunLog).filter_by(project_name=name).order_by(
            RunLog.created_at.desc()
        ).limit(5).all()
        session.close()
        for r in rows:
            last_runs.append({
                "success": bool(r.success),
                "models_ran": r.models_ran,
                "models_failed": r.models_failed,
                "created_at": str(r.created_at),
            })

        return {
            "project": name,
            "model_count": len(project.models),
            "alerts": alerts,
            "last_runs": last_runs,
            "status": "healthy" if not alerts else "degraded",
        }

    # ── Schedules ──

    @app.get("/api/schedules")
    def list_schedules():
        session = app.state.Session()
        rows = session.query(ScheduleEntry).all()
        session.close()
        return [
            {
                "project": r.project_name,
                "cron": r.cron,
                "depends_on": r.depends_on or [],
                "enabled": bool(r.enabled),
            }
            for r in rows
        ]

    @app.post("/api/schedules/{project_name}")
    def set_schedule(project_name: str, body: ScheduleCreate):
        session = app.state.Session()
        existing = session.query(ScheduleEntry).filter_by(project_name=project_name).first()
        if existing:
            existing.cron = body.cron
            existing.depends_on = body.depends_on
            existing.enabled = 1 if body.enabled else 0
        else:
            entry = ScheduleEntry(
                project_name=project_name,
                cron=body.cron,
                depends_on=body.depends_on,
                enabled=1 if body.enabled else 0,
            )
            session.add(entry)
        session.commit()
        session.close()
        return {"project": project_name, "cron": body.cron, "depends_on": body.depends_on}

    @app.delete("/api/schedules/{project_name}")
    def delete_schedule(project_name: str):
        session = app.state.Session()
        session.query(ScheduleEntry).filter_by(project_name=project_name).delete()
        session.commit()
        session.close()
        return {"deleted": project_name}

    @app.get("/api/projects/{name}/status")
    def project_status(name: str):
        from kelpmesh_studio.scheduler import dependencies_satisfied
        return dependencies_satisfied(name)

    # ── Users ──

    @app.post("/api/users")
    def create_user(body: UserCreate, current_user=Depends(require_role("admin"))):
        session = app.state.Session()
        existing = session.query(User).filter_by(email=body.email).first()
        if existing:
            session.close()
            raise HTTPException(409, "User already exists")
        user = User(
            email=body.email, name=body.name, role=body.role, api_key=api_key_hash()
        )
        session.add(user)
        session.commit()
        session.close()
        return {"email": user.email, "name": user.name, "role": user.role, "api_key": user.api_key}

    @app.get("/api/users")
    def list_users(current_user=Depends(require_role("admin"))):
        session = app.state.Session()
        users = session.query(User).all()
        session.close()
        return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in users]

    # ── GDPR ──

    @app.get("/api/account/export")
    def export_user_data(current_user=Depends(require_role("viewer"))):
        session = app.state.Session()
        projects = session.query(ProjectModel).all()
        run_history = session.query(RunLog).order_by(RunLog.created_at.desc()).limit(100).all()
        session.close()
        return {
            "user": {"email": current_user.email, "name": current_user.name, "role": current_user.role},
            "projects": [
                {"name": p.name, "path": p.path, "created_at": str(p.created_at)} for p in projects
            ],
            "recent_runs": [
                {
                    "project": r.project_name, "success": bool(r.success),
                    "models_ran": r.models_ran, "at": str(r.created_at),
                }
                for r in run_history
            ],
        }

    @app.delete("/api/account")
    def delete_account(current_user=Depends(require_role("viewer"))):
        import shutil
        session = app.state.Session()
        session.query(User).filter_by(id=current_user.id).delete()
        for project in session.query(ProjectModel).all():
            project_path = Path(project.path)
            if project_path.exists():
                shutil.rmtree(project_path, ignore_errors=True)
            session.query(ModelVersion).filter_by(project_name=project.name).delete()
            session.query(RunLog).filter_by(project_name=project.name).delete()
            session.query(ScheduleEntry).filter_by(project_name=project.name).delete()
            session.delete(project)
        session.commit()
        session.close()
        return {"deleted": True, "message": "All data permanently deleted"}


# ── Helpers ─────────────────────────────────────────────────────────

def _get_project(app_state, name: str):
    from kelpmesh.core.project import Project
    session = app_state.Session()
    row = session.query(ProjectModel).filter_by(name=name).first()
    session.close()
    if not row:
        raise HTTPException(404, f"Project '{name}' not found")
    return Project(Path(row.path))


def _get_session(request: Request):
    return request.app.state.Session()


# ── Entry point ─────────────────────────────────────────────────────

app = create_app()


def run():
    import uvicorn
    cfg = app.state.config
    uvicorn.run(
        "kelpmesh_studio.server:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
    )
