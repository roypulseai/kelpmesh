# SOC 2 Preparation Checklist

## Controls to implement before audit

### Security
- [x] Encryption at rest (Fernet/AES-128-CBC + HMAC-SHA256 via `KELPMESH_ENCRYPTION_KEY` for state DB; DuckDB native encryption for warehouse)
- [x] Encryption in transit (TLS 1.2+ on all endpoints)
- [ ] Secrets management (AWS Secrets Manager, not env vars)
- [ ] Network isolation (ECS in private subnets, VPC endpoints)
- [ ] WAF / rate limiting on public API endpoints
- [x] Secrets scanner (`kelpmesh scan secrets --fail` in CI)
- [x] Telemetry guard (runtime block of analytics packages)

### Availability
- [ ] Multi-AZ database deployment
- [ ] Auto-scaling for runner tasks (target tracking)
- [ ] Health checks + auto-recovery for all services
- [ ] Runbook for incident response

### Integrity
- [x] Audit log for all user actions (model changes, runs, config) — `KelpMesh security audit`
- [x] Immutable run history (append-only JSONL in `target/audit.log`)
- [x] Checksums on model SQL versions (SHA-256 hashes in state engine)
- [ ] Backup policy (daily DB snapshots, 30-day retention)

### Confidentiality
- [x] Row-level security for multi-tenant data — `KelpMesh security rls`
- [x] Dynamic column masking per role — `KelpMesh security mask`
- [x] Data classification (pii/sensitive/restricted/internal) — `KelpMesh security classify`
- [x] Right to be forgotten / erasure — `KelpMesh security clean-pii`
- [x] Role-based access control (admin/editor/viewer) — `KelpMesh security roles`
- [ ] API key rotation policy (90-day max)
- [ ] Session timeout (15 min idle)
- [x] Data residency options (EU, US, CH via `kelpmesh.yml`)

### Privacy / Compliance
- [x] GDPR Article 17 erasure endpoint (`DELETE /api/account`)
- [x] GDPR Article 20 portability endpoint (`GET /api/account/export`)
- [x] Swiss nFADP compliance (DPA, Privacy Policy, Swiss representative)
- [x] Data Processing Agreement (`DPA.md`) with Swiss governing law

## New security subsystems (June 2026)

| Subsystem | File | CLI Command | Description |
|-----------|------|-------------|-------------|
| Audit log | `KelpMesh/security/audit.py` | `KelpMesh security audit` | Append-only JSONL with actor, action, resource, before/after state |
| Data classification | `KelpMesh/security/classifier.py` | `KelpMesh security classify` | Tag columns pii/sensitive/restricted/internal via `classify.yml` |
| Column masking | `KelpMesh/security/masking.py` | `KelpMesh security mask` | SQL-level masking expressions per role at query time |
| Row-level security | `KelpMesh/security/rls.py` | `KelpMesh security rls` | WHERE-clause filters per table+role from `security.yml` or `kelpmesh.yml` |
| PII erasure | `KelpMesh/security/erasure.py` | `KelpMesh security clean-pii` | Right to be forgotten — nulls PII columns across warehouse tables |
| Role reference | (built into masking) | `KelpMesh security roles` | Lists role hierarchy and accessible sensitivity levels |
| Security status | (aggregate) | `KelpMesh security status` | Shows overall security posture (encryption, classify, RLS, audit, etc.) |

## Notes for audit
- Use AWS Artifact to download SOC reports for infrastructure
- Engage a CPA firm 3 months before target audit date
- Year 1: SOC 2 Type I (point-in-time). Year 2: Type II (6-month period).
- Audit log is append-only JSONL — ship to secure S3 for long-term retention
- All masking is injected at query time; base tables remain unmasked for admin access
