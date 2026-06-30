"""KelpMesh Studio — freemium licensing and feature gating.

Tier model:
  free       Personal projects only, no commercial use.
             Limits: 1 user, 3 projects, 50 run history entries.
  pro        Commercial use, teams up to 5. $29 / user / month.
  business   Unlimited seats, SSO, BYOC. $79 / user / month.
  enterprise Custom pricing, dedicated support, on-prem.

License detection order (first match wins):
  1. KELPMESH_STUDIO_LICENSE_KEY environment variable
  2. `studio.license_key` field in kelpmesh.yml
  3. Default → free tier

License key format: km_<tier>_<b64url(json_payload)>_<b64url(ed25519_sig)>
  json_payload: {"tier":"pro","email":"...","seats":5,"exp":1800000000}
  ed25519_sig: Ed25519 signature of the b64url payload bytes, signed by
               the private key (kept off-repo). Verified with the public
               key embedded below.

Security model:
  - The signing private key is NEVER committed to the repo. It is loaded
    from KELPMESH_STUDIO_PRIVATE_KEY env var or a file path when issuing
    licenses via `kelpmesh license generate`.
  - The public key below is safe to publish — it can only verify, not forge.
  - The old HMAC shared-secret scheme and the KELPMESH_STUDIO_TIER env
    bypass have been REMOVED. Tier escalation requires a valid signed key.

Self-hosted validation is local — no phone-home.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Feature flag constants
# ---------------------------------------------------------------------------

F_AUTH               = "auth"            # login / user management
F_RBAC               = "rbac"            # role-based access control
F_API_KEYS           = "api_keys"        # programmatic API access
F_GIT_SYNC           = "git_sync"        # auto-deploy on git push
F_ALERTS             = "alerts"          # Slack / e-mail run alerts
F_AI_BYOK            = "ai_byok"         # AI assistant with BYOK
F_COLUMN_LINEAGE     = "column_lineage"  # column-level lineage in DAG
F_ADV_SCHEDULING     = "adv_scheduling" # browser-managed schedules
F_SSO                = "sso"             # SAML / OIDC / LDAP
F_BYOC               = "byoc"            # bring-your-own-compute packaging
F_AUDIT_LOG          = "audit_log"       # full audit log browser
F_UNLIMITED_HISTORY  = "unlimited_history"  # unlimited run history
F_UNLIMITED_PROJECTS = "unlimited_projects"  # unlimited projects

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierDef:
    name: str
    label: str
    price_usd_user_month: int       # 0 = free, -1 = custom
    max_users: int                  # 0 = unlimited
    max_projects: int               # 0 = unlimited
    max_run_history: int            # 0 = unlimited
    features: frozenset = field(default_factory=frozenset)
    commercial_use: bool = False
    support: str = "Community (Discord)"


_PRO_FEATURES = frozenset({
    F_AUTH, F_RBAC, F_API_KEYS, F_GIT_SYNC, F_ALERTS,
    F_AI_BYOK, F_COLUMN_LINEAGE, F_ADV_SCHEDULING,
    F_UNLIMITED_HISTORY, F_UNLIMITED_PROJECTS,
})

_BUSINESS_FEATURES = _PRO_FEATURES | frozenset({F_SSO, F_BYOC, F_AUDIT_LOG})

TIER_DEFS: dict[str, TierDef] = {
    "free": TierDef(
        name="free",
        label="Free",
        price_usd_user_month=0,
        max_users=1,
        max_projects=3,
        max_run_history=50,
        features=frozenset(),
        commercial_use=False,
        support="Community (Discord)",
    ),
    "pro": TierDef(
        name="pro",
        label="Pro",
        price_usd_user_month=29,
        max_users=5,
        max_projects=0,
        max_run_history=0,
        features=_PRO_FEATURES,
        commercial_use=True,
        support="Email (48h SLA)",
    ),
    "business": TierDef(
        name="business",
        label="Business",
        price_usd_user_month=79,
        max_users=0,
        max_projects=0,
        max_run_history=0,
        features=_BUSINESS_FEATURES,
        commercial_use=True,
        support="Priority email (8h SLA)",
    ),
    "enterprise": TierDef(
        name="enterprise",
        label="Enterprise",
        price_usd_user_month=-1,
        max_users=0,
        max_projects=0,
        max_run_history=0,
        features=_BUSINESS_FEATURES,
        commercial_use=True,
        support="Dedicated (1h SLA)",
    ),
}

# Tier ordering for ">=" comparisons
_TIER_ORDER = ["free", "pro", "business", "enterprise"]

# ---------------------------------------------------------------------------
# Ed25519 public key (safe to publish — can only verify, not forge keys)
# ---------------------------------------------------------------------------

_LICENSE_PUBLIC_KEY_B64 = "B49tWaeMe/Xaq6a2kOPA0APveGt0BXgS9x9x7s0yQ7s="


def _get_public_key():
    """Load the Ed25519 public key from the embedded base64 raw bytes."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    raw = base64.b64decode(_LICENSE_PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)


# ---------------------------------------------------------------------------
# License key codec
# ---------------------------------------------------------------------------

@dataclass
class LicenseInfo:
    tier: str = "free"
    email: str = ""
    seats: int = 1
    expires_at: Optional[datetime] = None
    source: str = "default"   # "default" | "env" | "config" | "key"

    @property
    def is_valid(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.now(timezone.utc) < self.expires_at

    @property
    def tier_def(self) -> TierDef:
        return TIER_DEFS.get(self.tier, TIER_DEFS["free"])


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode_key(key: str) -> LicenseInfo:
    """Parse and validate a km_<tier>_<b64payload>.<b64sig> key.

    Uses Ed25519 asymmetric signature verification. The private key is kept
    off-repo; only the public key is embedded here.

    The payload and signature are separated by '.' (not '_') because
    base64url encoding uses '_' as a valid character, which would break
    splitting on '_'.

    Raises ValueError on any validation failure.
    """
    # Format: km_<tier>_<b64payload>.<b64sig>
    # Split on first two '_' to get prefix+tier, then split rest on '.'
    if not key.startswith("km_"):
        raise ValueError("invalid key format (must start with km_)")
    rest = key[3:]  # strip "km_"
    under_idx = rest.find("_")
    if under_idx < 0:
        raise ValueError("invalid key format (missing tier separator)")
    tier_prefix = rest[:under_idx]
    b64_combined = rest[under_idx + 1:]
    dot_idx = b64_combined.find(".")
    if dot_idx < 0:
        raise ValueError("invalid key format (missing payload.signature separator)")
    b64_payload = b64_combined[:dot_idx]
    b64_sig = b64_combined[dot_idx + 1:]

    # Verify Ed25519 signature
    try:
        pub_key = _get_public_key()
        payload_bytes = b64_payload.encode()
        sig_bytes = _b64url_decode(b64_sig)
        pub_key.verify(sig_bytes, payload_bytes)
    except Exception as exc:
        raise ValueError(f"invalid license key signature: {exc}") from exc

    try:
        payload = json.loads(_b64url_decode(b64_payload))
    except Exception as exc:
        raise ValueError(f"malformed payload: {exc}") from exc

    tier = payload.get("tier", tier_prefix)
    if tier not in TIER_DEFS:
        raise ValueError(f"unknown tier: {tier!r}")

    expires_at: Optional[datetime] = None
    if "exp" in payload:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    info = LicenseInfo(
        tier=tier,
        email=payload.get("email", ""),
        seats=int(payload.get("seats", 1)),
        expires_at=expires_at,
        source="key",
    )
    if not info.is_valid:
        raise ValueError("license key has expired")

    return info


def generate_license_key(
    tier: str,
    email: str = "",
    seats: int = 1,
    expires_at: Optional[datetime] = None,
    private_key_pem: Optional[str] = None,
) -> str:
    """Generate a signed license key using the Ed25519 private key.

    The private key is loaded from:
      1. The *private_key_pem* argument (PEM string)
      2. KELPMESH_STUDIO_PRIVATE_KEY env var (PEM string)
      3. KELPMESH_STUDIO_PRIVATE_KEY_FILE env var (path to PEM file)

    This function is used by `kelpmesh license generate` and should NEVER
    be called with a key that is committed to the repository.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    # Load private key
    pem_data = private_key_pem
    if pem_data is None:
        pem_data = os.environ.get("KELPMESH_STUDIO_PRIVATE_KEY", "")
    if not pem_data:
        key_file = os.environ.get("KELPMESH_STUDIO_PRIVATE_KEY_FILE", "")
        if key_file and Path(key_file).exists():
            pem_data = Path(key_file).read_text()
    if not pem_data:
        raise RuntimeError(
            "No private key found. Set KELPMESH_STUDIO_PRIVATE_KEY or "
            "KELPMESH_STUDIO_PRIVATE_KEY_FILE to issue license keys."
        )

    private_key = serialization.load_pem_private_key(
        pem_data.encode(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("Loaded key is not an Ed25519 private key")

    # Build payload
    payload: dict = {"tier": tier, "seats": seats}
    if email:
        payload["email"] = email
    if expires_at:
        payload["exp"] = int(expires_at.timestamp())

    payload_json = json.dumps(payload, separators=(",", ":"))
    b64_payload = _b64url_encode(payload_json.encode())

    # Sign the base64url payload
    sig = private_key.sign(b64_payload.encode())
    b64_sig = _b64url_encode(sig)

    return f"km_{tier}_{b64_payload}.{b64_sig}"


# ---------------------------------------------------------------------------
# Current license resolution
# ---------------------------------------------------------------------------

_cached_license: Optional[LicenseInfo] = None


def _load_from_config() -> Optional[str]:
    """Try to read studio.license_key from kelpmesh.yml in cwd or project dir."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return None

    candidates = [
        Path(os.environ.get("KELPMESH_PROJECT_DIR", ".")) / "kelpmesh.yml",
        Path.cwd() / "kelpmesh.yml",
    ]
    for p in candidates:
        if p.exists():
            try:
                data = yaml.safe_load(p.read_text())
                key = (data or {}).get("studio", {}).get("license_key")
                if key:
                    return str(key)
            except Exception:
                pass
    return None


def get_current_license(refresh: bool = False) -> LicenseInfo:
    """Return the active license, resolved once and cached.

    Resolution order:
      1. KELPMESH_STUDIO_LICENSE_KEY env var -> validated key
      2. studio.license_key in kelpmesh.yml -> validated key
      3. Default -> free tier

    The KELPMESH_STUDIO_TIER env var bypass has been REMOVED. Tier
    escalation now requires a valid Ed25519-signed license key.
    """
    global _cached_license
    if _cached_license is not None and not refresh:
        return _cached_license

    # 1. License key from env
    raw_key = os.environ.get("KELPMESH_STUDIO_LICENSE_KEY", "").strip()
    if raw_key:
        try:
            info = _decode_key(raw_key)
            _cached_license = LicenseInfo(
                tier=info.tier,
                email=info.email,
                seats=info.seats,
                expires_at=info.expires_at,
                source="env",
            )
            return _cached_license
        except ValueError:
            pass  # fall through to config check

    # 2. License key from kelpmesh.yml
    config_key = _load_from_config()
    if config_key:
        try:
            info = _decode_key(config_key)
            _cached_license = LicenseInfo(
                tier=info.tier,
                email=info.email,
                seats=info.seats,
                expires_at=info.expires_at,
                source="config",
            )
            return _cached_license
        except ValueError:
            pass

    # Default -> free
    _cached_license = LicenseInfo(tier="free", source="default")
    return _cached_license


# ---------------------------------------------------------------------------
# Feature checking
# ---------------------------------------------------------------------------

def has_feature(feature: str) -> bool:
    lic = get_current_license()
    return feature in lic.tier_def.features


def within_limit(limit_name: str, current_value: int) -> bool:
    """Return True if current_value is within the tier's limit for limit_name.

    limit_name: "projects" | "users" | "run_history"
    """
    td = get_current_license().tier_def
    limit_map = {
        "projects": td.max_projects,
        "users": td.max_users,
        "run_history": td.max_run_history,
    }
    limit = limit_map.get(limit_name, 0)
    if limit == 0:
        return True
    return current_value <= limit


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------

_UPGRADE_URL = "https://roypulseai.github.io/kelpmesh/studio/overview/"

_UPGRADE_MSG = (
    "Your KelpMesh Studio plan does not include this feature. "
    f"Upgrade at {_UPGRADE_URL}"
)


def require_feature(feature: str):
    """FastAPI dependency: raises HTTP 402 if feature not on current tier."""
    def _check():
        if not has_feature(feature):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "upgrade_required",
                    "feature": feature,
                    "current_tier": get_current_license().tier,
                    "message": _UPGRADE_MSG,
                    "upgrade_url": _UPGRADE_URL,
                },
            )
    return _check


def require_min_tier(min_tier: str):
    """FastAPI dependency: raises HTTP 402 if current tier is below min_tier."""
    def _check():
        current = get_current_license().tier
        if _TIER_ORDER.index(current) < _TIER_ORDER.index(min_tier):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "upgrade_required",
                    "required_tier": min_tier,
                    "current_tier": current,
                    "message": _UPGRADE_MSG,
                    "upgrade_url": _UPGRADE_URL,
                },
            )
    return _check


def enforce_limit(limit_name: str, current_value: int, resource_label: str = ""):
    """Raise HTTP 402 if current_value exceeds the tier limit."""
    td = get_current_license().tier_def
    limit_map = {
        "projects": td.max_projects,
        "users": td.max_users,
        "run_history": td.max_run_history,
    }
    limit = limit_map.get(limit_name, 0)
    if limit != 0 and current_value >= limit:
        label = resource_label or limit_name
        raise HTTPException(
            status_code=402,
            detail={
                "error": "limit_reached",
                "limit_name": limit_name,
                "limit": limit,
                "current": current_value,
                "current_tier": get_current_license().tier,
                "message": (
                    f"You have reached the {label} limit ({limit}) for the "
                    f"{td.label} tier. {_UPGRADE_MSG}"
                ),
                "upgrade_url": _UPGRADE_URL,
            },
        )


# ---------------------------------------------------------------------------
# Info endpoint payload
# ---------------------------------------------------------------------------

def tier_info() -> dict:
    """Return a safe, serialisable dict for the /api/tier endpoint."""
    lic = get_current_license()
    td = lic.tier_def
    return {
        "tier": td.name,
        "label": td.label,
        "commercial_use": td.commercial_use,
        "price_usd_user_month": td.price_usd_user_month,
        "max_users": td.max_users,
        "max_projects": td.max_projects,
        "max_run_history": td.max_run_history,
        "features": sorted(td.features),
        "support": td.support,
        "license_email": lic.email,
        "license_seats": lic.seats,
        "license_expires": lic.expires_at.isoformat() if lic.expires_at else None,
        "license_source": lic.source,
        "upgrade_url": _UPGRADE_URL,
    }
