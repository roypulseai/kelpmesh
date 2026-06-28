# kelpmesh-studio

Browser dashboard for [KelpMesh](https://github.com/saikatxtreme/kelpmesh) — the pure-SQL transformation platform.

## Installation

```bash
pip install kelpmesh-studio
```

This installs `kelpmesh-core` (the full CLI engine) plus the FastAPI + uvicorn dependencies needed to run the browser UI.

## Pricing

| Tier | Use case | Price | Key limits |
|------|----------|-------|------------|
| **Free** | Personal projects | $0 | 1 user · 3 projects · 50-entry run history |
| **Pro** | Commercial teams | $29 / user / month | 5 seats · unlimited projects · all features |
| **Business** | Larger orgs | $79 / user / month | Unlimited seats · SSO · BYOC |
| **Enterprise** | Custom / on-prem | Contact us | Dedicated SLA · on-premises |

`kelpmesh-core` is always **free and open-source** (Apache 2.0). Studio's freemium model applies only to the browser dashboard.

### Activating a paid license

```bash
# Set the key from the email you receive after purchase
export KELPMESH_STUDIO_LICENSE_KEY=km_pro_<payload>_<sig>
kelpmesh studio
```

Or add it to `kelpmesh.yml`:

```yaml
studio:
  license_key: km_pro_<payload>_<sig>
```

No internet connection is required after activation — all validation is local.

## Usage

```bash
# Start the browser dashboard (opens http://localhost:8501 automatically)
kelpmesh studio

# Check your current tier
curl http://localhost:8501/api/tier

# Core CLI always works, no license required
kelpmesh run
kelpmesh plan
kelpmesh test
```

## Feature matrix

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| DAG visualization | ✅ | ✅ | ✅ | ✅ |
| Run / Test / Plan from browser | ✅ | ✅ | ✅ | ✅ |
| Projects | 3 | Unlimited | Unlimited | Unlimited |
| Run history | 50 entries | Unlimited | Unlimited | Unlimited |
| Users / seats | 1 | 5 | Unlimited | Unlimited |
| Column-level lineage | — | ✅ | ✅ | ✅ |
| Authentication & RBAC | — | ✅ | ✅ | ✅ |
| API keys | — | ✅ | ✅ | ✅ |
| Git sync (auto-deploy on push) | — | ✅ | ✅ | ✅ |
| Slack / e-mail alerts | — | ✅ | ✅ | ✅ |
| Browser-managed schedules | — | ✅ | ✅ | ✅ |
| AI assistant (BYOK) | — | ✅ | ✅ | ✅ |
| Audit log browser | — | ✅ | ✅ | ✅ |
| SSO (SAML / OIDC / LDAP) | — | — | ✅ | ✅ |
| BYOC (Docker / K8s deploy) | — | — | ✅ | ✅ |
| On-premises deployment | — | — | — | ✅ |
| Commercial use | Personal only | ✅ | ✅ | ✅ |
| Support | Community | Email 48h | Email 8h | Dedicated 1h |

## Package structure

`kelpmesh-studio` is a meta-package:

| Dependency | Purpose |
|-----------|---------|
| `kelpmesh-core>=0.2.0` | SQL engine, 9 adapters, 32 macros, scheduler |
| `fastapi>=0.110` | REST API for the browser dashboard |
| `uvicorn[standard]>=0.27` | ASGI server |
| `python-multipart>=0.0.6` | Form / file upload support |

## Just the CLI (no browser UI)

```bash
pip install kelpmesh-core
```

`kelpmesh-core` is 100% free and open-source — no license required, ever.

## License

Apache 2.0 · © 2026 Saikat Roy

KelpMesh Studio's paid tiers are a commercial add-on on top of the Apache 2.0 core.
