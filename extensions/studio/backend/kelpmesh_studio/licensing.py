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

License key format: km_<tier>_<b64url(json_payload)>_<hmac8>
  json_payload: {"tier":"pro","email":"...","seats":5,"exp":1800000000}
  hmac8: first 16 hex chars of HMAC-SHA256(b64_payload, _PRODUCT_SECRET)

Self-hosted validation is local — no phone-home.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
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

# Tier ordering for "≥" comparisons
_TIER_ORDER = ["free", "pro", "business", "enterprise"]


# ---------------------------------------------------------------------------
# License key codec
# ---------------------------------------------------------------------------

# This is obscured-but-not-secret: the project is Apache 2.0. Determined
# users with source access can bypass it. The goal is honest commercial use
# honoring, not DRM.
_PRODUCT_SECRET = "km-studio-lic-v1-a7f3b9c2e5d8f1a4b6c0e3f7d2a8b5c1"


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


def _decode_key(key: str) -> LicenseInfo:
    """Parse and validate a km_<tier>_<b64payload>_<hmac8> key.

    Raises ValueError on any validation failure.
    """
    parts = key.split("_")
    if len(parts) < 4 or parts[0] != "km":
        raise ValueError("invalid key format")

    tier_prefix = parts[1]
    b64_payload = parts[2]
    provided_sig = parts[3]

    # Verify HMAC
    expected_sig = hmac.new(
        _PRODUCT_SECRET.encode(),
        b64_payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("invalid license key signature")

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
    """Return the active license, resolved once and cached."""
    global _cached_license
    if _cached_license is not None and not refresh:
        return _cached_license

    # 1. Explicit tier override (dev / CI convenience — no key needed)
    override = os.environ.get("KELPMESH_STUDIO_TIER", "").lower()
    if override in TIER_DEFS:
        _cached_license = LicenseInfo(tier=override, source="env")
        return _cached_license

    # 2. License key from env
    raw_key = os.environ.get("KELPMESH_STUDIO_LICENSE_KEY", "").strip()
    if raw_key:
        try:
            _cached_license = _decode_key(raw_key)
            _cached_license = LicenseInfo(
                tier=_cached_license.tier,
                email=_cached_license.email,
                seats=_cached_license.seats,
                expires_at=_cached_license.expires_at,
                source="env",
            )
            return _cached_license
        except ValueError:
            pass  # fall through to config check

    # 3. License key from kelpmesh.yml
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

    # Default → free
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

_UPGRADE_MSG = (
    "Your KelpMesh Studio plan does not include this feature. "
    "Upgrade to Pro or Business at https://github.com/RoyPulseAI/kelpmesh#studio-browser-dashboard — "
    "or set KELPMESH_STUDIO_LICENSE_KEY to activate your purchased key."
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
                    "upgrade_url": "https://github.com/RoyPulseAI/kelpmesh#studio-browser-dashboard",
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
                    "upgrade_url": "https://github.com/RoyPulseAI/kelpmesh#studio-browser-dashboard",
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
                "upgrade_url": "https://github.com/RoyPulseAI/kelpmesh#studio-browser-dashboard",
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
        "upgrade_url": "https://github.com/RoyPulseAI/kelpmesh#studio-browser-dashboard",
    }
