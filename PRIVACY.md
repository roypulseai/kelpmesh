# Privacy Policy

**Last updated: June 2026**

## 1. What we collect

### KelpMesh CLI (open source)
The CLI tool runs entirely on your machine. It collects **no telemetry, no usage data, no personal information**. No analytics, no crash reports, no phone-home. This is enforced at the code level — any telemetry library detected at startup will block execution.

Optional state database encryption is available via the `KELPMESH_ENCRYPTION_KEY` environment variable (AES-256-GCM via Fernet, `KelpMesh/core/crypto.py`). The CLI never generates or stores encryption keys unless explicitly asked (`kelpmesh scan generate-key`).

If you use `KelpMesh import` to migrate from dbt, all data stays local.

### KelpMesh Studio (cloud offering)
When you use KelpMesh Studio, we collect:

| What | Why |
|------|-----|
| Email address + name | Account creation, login, support |
| Project SQL + model metadata | Core functionality — stored in your workspace |
| Run history (timestamps, pass/fail) | Audit log, debugging |
| IP address + user agent | Security, rate limiting |

We do **not** sell your data. We do **not** share your data with third parties except as required by law.

## 2. Legal basis (Swiss nFADP / revDSG)

For users in Switzerland, processing is based on:

- **Art. 6 para. 1 lit. a nFADP (consent)** — account creation, marketing opt-in
- **Art. 6 para. 1 lit. b nFADP (contract)** — service delivery, support
- **Art. 6 para. 1 lit. f nFADP (legitimate interest)** — security, fraud prevention

For EU/EEA users, the equivalent GDPR bases apply (Art. 6(1)(a), (b), (f)).

## 3. Data storage

- **CLI**: All data stored locally in `target/` and `kelpmesh_packages/`. You control retention. The state database (`target/kelpmesh_state.duckdb`) can be encrypted at rest via `KELPMESH_ENCRYPTION_KEY`.
- **Studio**: Data stored in encrypted SQLite/S3. Backups retained 30 days.
- **Swiss / EU users**: Data can be hosted in `eu-west-1` (Frankfurt/Ireland) or `ch-west-1` (Zurich). Specify at account creation.

## 4. Data retention

We retain your account data for the duration of your account + 90 days after cancellation. After 90 days, all data is permanently deleted.

Run history is retained for 12 months for audit purposes, then anonymized.

## 5. Your rights (GDPR & nFADP)

If you are in Switzerland or the EU/EEA, you have the right to:

- **Access / information** — request a copy of all data we hold about you (GDPR Art. 15, nFADP Art. 25)
- **Rectification** — correct inaccurate data (GDPR Art. 16, nFADP Art. 5)
- **Erasure** — delete your account and all associated data (GDPR Art. 17, nFADP Art. 8)
- **Portability** — export your data in JSON format (GDPR Art. 20, nFADP Art. 28)
- **Object** — object to processing of your data (GDPR Art. 21, nFADP Art. 12)

To exercise these rights, email **privacy@KelpMesh.dev**. We respond within 30 days.

## 6. Cookies

KelpMesh Studio uses a single session cookie (`session`) for authentication. No tracking cookies, no analytics cookies, no third-party cookies.

You can use Studio without cookies by generating an API key and using the API directly.

## 7. Security

- Encryption at rest: AES-256-GCM (state DB, RDS/S3)
- Encryption in transit: TLS 1.2+
- API keys: SHA-256 hashed at rest
- No plaintext passwords stored (OAuth-only for Studio)
- Secrets scanner built-in: `kelpmesh scan secrets` detects hardcoded credentials in SQL files
- Telemetry guard: runtime check prevents loading analytics packages

## 8. Data Processing

When you use KelpMesh Cloud to process your company's data, KelpMesh acts as a **Data Processor** under GDPR / nFADP. We offer a Data Processing Agreement (DPA) for enterprise customers — see `DPA.md`.

## 9. International transfers

Data may be processed in Switzerland, the EU, or the United States. For transfers from Switzerland to the US, we rely on:
- Standard Contractual Clauses (SCCs) as recognised by the Swiss FDPIC
- Swiss-US Data Privacy Framework (where applicable)

## 10. Contact

- Privacy questions: **privacy@KelpMesh.dev**
- DPO / Data Protection Advisor: **dpo@KelpMesh.dev** (reachable under Swiss law Art. 10 nFADP)
- Swiss representative (Art. 14 nFADP): **KelpMesh GmbH, Bahnhofstrasse 10, 8001 Zurich, Switzerland**
- Security: **security@KelpMesh.dev**

## 11. Changes

We'll notify you by email 30 days before any material change to this policy.

---

*KelpMesh — Build your data, KelpMesh by KelpMesh.*
