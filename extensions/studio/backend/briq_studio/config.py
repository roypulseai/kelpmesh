"""Studio configuration — loaded from environment variables."""
import os
from pathlib import Path


class StudioConfig:
    def __init__(self):
        self.data_dir = Path(os.environ.get(
            "BRIQ_STUDIO_DATA", str(Path(__file__).parent.parent / "studio_data")
        ))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_url = os.environ.get(
            "BRIQ_STUDIO_DATABASE_URL",
            f"sqlite:///{self.data_dir / 'studio.db'}",
        )
        self.jwt_secret = os.environ.get(
            "BRIQ_STUDIO_JWT_SECRET", "dev-secret-change-in-production"
        )
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = int(os.environ.get("BRIQ_STUDIO_JWT_EXPIRE", "1440"))
        self.cors_origins = [
            o.strip()
            for o in os.environ.get(
                "BRIQ_STUDIO_ORIGINS",
                "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000",
            ).split(",")
        ]
        self.host = os.environ.get("BRIQ_STUDIO_HOST", "0.0.0.0")
        self.port = int(os.environ.get("BRIQ_STUDIO_PORT", "8765"))
        self.debug = os.environ.get("BRIQ_STUDIO_DEBUG", "0") == "1"
        self.encryption_key = os.environ.get("BRIQ_ENCRYPTION_KEY", "")

    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def db_connect_args(self) -> dict:
        if self.is_postgres():
            return {}
        return {"check_same_thread": False}
