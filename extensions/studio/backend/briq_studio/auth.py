"""JWT authentication for briq Studio."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    email: str
    role: str = "viewer"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(email: str, role: str, secret: str, algorithm: str, expire_minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"email": email, "role": role, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        email = payload.get("email")
        role = payload.get("role", "viewer")
        if email is None:
            return None
        return TokenData(email=email, role=role)
    except JWTError:
        return None


def api_key_hash() -> str:
    return secrets.token_hex(32)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """Extract and validate user from JWT or API key."""
    from briq_studio.server import get_db_session, User

    if credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = ""

    if not token:
        return None

    cfg = request.app.state.config

    token_data = decode_token(token, cfg.jwt_secret, cfg.jwt_algorithm)
    if token_data:
        session = get_db_session()
        user = session.query(User).filter_by(email=token_data.email).first()
        session.close()
        return user

    session = get_db_session()
    user = session.query(User).filter_by(api_key=token).first()
    session.close()
    return user


def require_role(role: str):
    """Dependency factory for role-based access control."""
    async def _require(current_user = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        roles_order = ["admin", "editor", "viewer"]
        if roles_order.index(current_user.role) > roles_order.index(role):
            raise HTTPException(status_code=403, detail="Forbidden")
        return current_user
    return _require
