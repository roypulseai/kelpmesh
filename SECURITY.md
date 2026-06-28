# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in briq, please report it privately by emailing **hello@briq.dev**.

**Do not** open a public GitHub issue for security vulnerabilities.

We will respond within 48 hours with a triage plan. We appreciate responsible disclosure.

## Supported Versions

We currently provide security patches for the latest minor version of briq.

## Security Features

- **Secrets scanner**: Run `briq scan secrets` to detect hardcoded credentials in your SQL files.
- **Encryption at rest**: Set `BRIQ_ENCRYPTION_KEY` to encrypt the state database with AES-256-GCM.
- **Telemetry guard**: briq blocks execution if any telemetry/analytics package is loaded.
- **Data leak prevention**: Executor warns when models reference external URLs or data sources.
