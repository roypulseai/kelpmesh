"""briq Studio backend — FastAPI server with Postgres + JWT auth."""
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

from briq_studio.config import StudioConfig
from briq_studio.auth import (
    hash_password, verify_password, create_token, api_key_hash,
    get_current_user, require_role,
)

Base = declarative_base()


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


class RunHistory(Base):
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
    cfg = StudioConfig()
    engine = create_engine(cfg.database_url, connect_args=cfg.db_connect_args)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    app = FastAPI(title="briq Studio", version="0.1.0")
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
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

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
        return {"status": "ok", "version": "0.1.0"}

    # ── Auth ──

    @app.post("/api/auth/signup")
    def signup(body: SignupRequest):
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
        rows = session.query(ProjectModel).all()
        session.close()
        return [{"id": r.id, "name": r.name, "path": r.path, "created_at": str(r.created_at)} for r in rows]

    @app.post("/api/projects")
    def create_project(body: ProjectCreate):
        data_dir = app.state.config.data_dir
        project_path = data_dir / body.name
        briq_path = project_path / "briq.yml"
        if briq_path.exists():
            raise HTTPException(409, f"Project '{body.name}' already exists")
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "models").mkdir(exist_ok=True)
        (project_path / "tests").mkdir(exist_ok=True)
        from briq.core.config import ProjectConfig
        config = ProjectConfig(name=body.name)
        config.save(project_path)
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
        row = session.query(ProjectModel).filter_by(name=name).first()
        if not row:
            session.close()
            raise HTTPException(404, f"Project '{name}' not found")
        project_path = Path(row.path)
        if project_path.exists():
            shutil.rmtree(project_path, ignore_errors=True)
        session.query(ModelVersion).filter_by(project_name=name).delete()
        session.query(RunHistory).filter_by(project_name=name).delete()
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
            if model_name in existing:
                model_path = existing[model_name]
            else:
                model_path = project.path / "models" / f"{model_name}.sql"
        else:
            model_path = model.file_path

        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(body.sql, encoding="utf-8")

        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
        rows = session.query(ModelVersion).filter_by(
            project_name=name, model_name=model_name
        ).order_by(ModelVersion.version.desc()).all()
        session.close()
        return [{"version": r.version, "sql": r.sql, "created_at": str(r.created_at)} for r in rows]

    @app.get("/api/projects/{name}/models/{model_name}/versions/{version}")
    def get_version(name: str, model_name: str, version: int):
        session = get_db_session(app.state)
        row = session.query(ModelVersion).filter_by(
            project_name=name, model_name=model_name, version=version
        ).first()
        session.close()
        if not row:
            raise HTTPException(404, f"Version {version} not found")
        return {"version": row.version, "sql": row.sql, "created_at": str(row.created_at)}

    # ── Run ──

    @app.post("/api/projects/{name}/run")
    def run_project(name: str, body: RunRequest):
        from briq.core.project import Project
        from briq.core.executor import Executor
        from briq.state.engine import StateEngine
        from briq.adapters import get_adapter

        project = _get_project(app.state, name)
        adapter = get_adapter(project.config.warehouse, project_path=str(project.path))
        state = StateEngine(project.path)
        if body.full_refresh:
            state.reset()
        executor = Executor(project, adapter, state)
        results = executor.run(models=body.models, select=body.select)
        adapter.disconnect()
        state.close()

        success = len(results.get("failed", [])) == 0
        session = get_db_session(app.state)
        row = RunHistory(
            project_name=name,
            success=1 if success else 0,
            models_ran=len(results.get("ran", [])),
            models_failed=len(results.get("failed", [])),
        )
        session.add(row)
        session.commit()
        session.close()

        return {
            "success": success,
            "ran": len(results.get("ran", [])),
            "skipped": len(results.get("skipped", [])),
            "failed": len(results.get("failed", [])),
            "results": results,
        }

    @app.get("/api/projects/{name}/runs")
    def get_run_history(name: str, limit: int = 20):
        session = get_db_session(app.state)
        rows = session.query(RunHistory).filter_by(
            project_name=name
        ).order_by(RunHistory.created_at.desc()).limit(limit).all()
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

    # ── Schedules ──

    @app.get("/api/schedules")
    def list_schedules():
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
        session.query(ScheduleEntry).filter_by(project_name=project_name).delete()
        session.commit()
        session.close()
        return {"deleted": project_name}

    @app.get("/api/projects/{name}/status")
    def project_status(name: str):
        from briq_studio.scheduler import dependencies_satisfied
        return dependencies_satisfied(name)

    # ── Users ──

    @app.post("/api/users")
    def create_user(body: UserCreate, current_user=Depends(require_role("admin"))):
        session = get_db_session(app.state)
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
        session = get_db_session(app.state)
        users = session.query(User).all()
        session.close()
        return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in users]

    # ── GDPR ──

    @app.get("/api/account/export")
    def export_user_data(current_user=Depends(require_role("viewer"))):
        session = get_db_session(app.state)
        projects = session.query(ProjectModel).all()
        run_history = session.query(RunHistory).order_by(RunHistory.created_at.desc()).limit(100).all()
        user = current_user
        session.close()
        return {
            "user": {"email": user.email, "name": user.name, "role": user.role},
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
        session = get_db_session(app.state)
        user = current_user
        session.query(User).filter_by(id=user.id).delete()
        for project in session.query(ProjectModel).all():
            project_path = Path(project.path)
            if project_path.exists():
                shutil.rmtree(project_path, ignore_errors=True)
            session.query(ModelVersion).filter_by(project_name=project.name).delete()
            session.query(RunHistory).filter_by(project_name=project.name).delete()
            session.query(ScheduleEntry).filter_by(project_name=project.name).delete()
            session.delete(project)
        session.commit()
        session.close()
        return {"deleted": True, "message": "All data permanently deleted"}


# ── Helpers ─────────────────────────────────────────────────────────

def _get_project(app_state, name: str):
    from briq.core.project import Project
    session = get_db_session(app_state)
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
        "briq_studio.server:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
    )
