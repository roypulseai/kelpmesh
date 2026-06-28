"""JWT authentication for briq Studio — stdlib only (no passlib, no python-jose)."""
import hmac
import hashlib
import secrets
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer(auto_error=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class TokenData(BaseModel):
    email: str
    role: str = "viewer"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt}${dk.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _, salt, dk_hex = hashed.split("$")
        dk = hashlib.scrypt(plain.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_token(email: str, role: str, secret: str, algorithm: str, expire_minutes: int) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
    payload_data = {
        "email": email,
        "role": role,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    payload = _b64url_encode(json.dumps(payload_data).encode())
    msg = f"{header}.{payload}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return f"{msg}.{_b64url_encode(sig)}"


def decode_token(token: str, secret: str, algorithm: str) -> Optional[TokenData]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        msg = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig_b64), expected_sig):
            return None
        data = json.loads(_b64url_decode(payload_b64))
        if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        email = data.get("email")
        role = data.get("role", "viewer")
        if email is None:
            return None
        return TokenData(email=email, role=role)
    except Exception:
        return None


def api_key_hash() -> str:
    return secrets.token_hex(32)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """Extract and validate user from JWT or API key."""
    from briq_studio.server import User

    if credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if not token:
        return None

    cfg = request.app.state.config
    session = request.app.state.Session()

    token_data = decode_token(token, cfg.jwt_secret, cfg.jwt_algorithm)
    if token_data:
        user = session.query(User).filter_by(email=token_data.email).first()
        session.close()
        return user

    user = session.query(User).filter_by(api_key=token).first()
    session.close()
    return user


def require_role(role: str):
    """Dependency factory for role-based access control."""
    async def _require(current_user=Depends(get_current_user)):
        if not current_user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        roles_order = ["admin", "editor", "viewer"]
        if roles_order.index(current_user.role) > roles_order.index(role):
            raise HTTPException(status_code=403, detail="Forbidden")
        return current_user
    return _require
