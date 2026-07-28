# Security Policy

<!-- Prose in this file is hard-wrapped at 80 columns. Tables, code blocks and
     link targets are left unwrapped. -->

Finlytics is a self-hosted application that stores bank transactions, account
balances and investment holdings. A vulnerability here exposes financial data,
so reports are taken seriously.

## Supported versions

Only the latest published image (`drdonoso/finlytics:latest`) is supported.
Fixes ship as a new CalVer tag; there are no backports.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub Security Advisories:

1. Go to the [Security tab](https://github.com/DrDonoso/Finlytics/security/advisories)
2. Click **Report a vulnerability**

Helpful details: affected version or image tag, reproduction steps, impact, and
any suggested fix. Expect an initial response within 7 days. Please allow a
reasonable window to ship a fix before public disclosure.

## Scope

**In scope** — authentication and session handling, authorization gaps between
accounts, injection, path traversal or arbitrary file access, SSRF via the
investment connectors, leakage of connector tokens or statement contents, and
RCE.

**Out of scope** — anything that requires an already-compromised host, findings
against a deployment that ignores the hardening rules below, denial of service
through resource exhaustion, and vulnerabilities in third-party dependencies
with no exploitable path in Finlytics (report those upstream).

## Deployment hardening

Getting these wrong is the most likely cause of a real-world compromise:

| Setting | Requirement |
|---------|-------------|
| `AUTH_SECRET` | Generate your own. Signs session JWTs — a shared or placeholder value lets anyone forge a session cookie. The app refuses to start on known placeholders. |
| `FINLYTICS_ENCRYPTION_KEY` | Generate your own Fernet key. Encrypts connector API tokens at rest. |
| `POSTGRES_PASSWORD` | Required; never leave it at the example value. |
| `AUTH_COOKIE_SECURE` | Set to `true` when serving over HTTPS. |
| Network exposure | Do not publish port 7777 straight to the internet. Put it behind a reverse proxy with TLS. |
| First-run setup | `POST /api/auth/setup` is unauthenticated until the first user exists. Complete setup immediately after the first start, before the instance is reachable by anyone else. |

Generate secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"                                # AUTH_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FINLYTICS_ENCRYPTION_KEY
```

## Known design limits

These are documented, not bugs — but you should know about them:

- **No rate limiting on login.** There is no lockout or throttling on
  `/api/auth/login`. Enforce it at your reverse proxy if the instance is
  reachable from an untrusted network.
- **Single-user model.** Records are scoped to the owning user, but the app is
  designed for one account per deployment, not for multi-tenant use.
- **Statement contents reach your AI provider.** When `OPENAI_API_KEY` is set,
  statement text is sent to the configured endpoint for extraction. PII is
  redacted first (see `src/finlytics/extraction/redaction.py`). Leave the key
  unset to disable extraction entirely.
