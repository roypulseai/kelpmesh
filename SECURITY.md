# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in KelpMesh, please report it via [GitHub's private vulnerability reporting](https://github.com/RoyPulseAI/kelpmesh/security/advisories/new) or email **roypulse.ai@gmail.com**.

**Do not** open a public GitHub issue for security vulnerabilities.

We will respond within 48 hours with a triage plan. We appreciate responsible disclosure.

## Supported Versions

We currently provide security patches for the latest minor version of KelpMesh.

## Security Features

- **Secrets scanner**: Run `kelpmesh scan secrets` to detect hardcoded credentials in your SQL files.
- **Encryption at rest**: Set `KELPMESH_ENCRYPTION_KEY` to encrypt the state database with AES-256-GCM.
- **Telemetry guard**: KelpMesh blocks execution if any telemetry/analytics package is loaded.
- **Data leak prevention**: Executor warns when models reference external URLs or data sources.
