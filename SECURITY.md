# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in AgentMemoryDB, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **security@agentmemorydb.dev** (placeholder)

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Security Considerations

AgentMemoryDB stores potentially sensitive agent memory data. When deploying:

- Always use TLS for database connections in production
- Use strong, unique database passwords
- Restrict database network access
- Enable PostgreSQL audit logging
- Review and restrict API access (authentication is the deployer's responsibility)
- Be mindful of PII stored in agent memories — consider data retention policies
- Use `expires_at` and memory archival to limit data exposure windows
