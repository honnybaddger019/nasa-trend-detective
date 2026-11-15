# Security Policy - EarthTrend AI

EarthTrend AI is a NASA Space Apps Challenge 2026 project. Security is owned by Role 6 (Security & Platform Engineer). The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Reporting a problem

Please do **not** open a public issue for a security problem (for example a leaked key or a way to make the AI misbehave).

- Open a private report: repository **Security** tab, then **Report a vulnerability** (GitHub private vulnerability reporting), or
- contact the Role 6 owner directly through the team channel.

We answer within 24 hours during the event and within 7 days after it.

## Where secrets live

| Secret | Stored in | Never in |
|---|---|---|
| LLM API key (`LLM_API_KEY`) | Render environment variables (production), local `.env` file (ignored by Git) | the code, the HTML, notebooks, screenshots, the chat, commit messages |
| GitHub token for CI | Provided automatically by GitHub Actions (`GITHUB_TOKEN`, read-only) | anywhere else |

Rules for every team member:

1. Copy `.env.example` to `.env` and put local values there. `.env` is ignored by Git.
2. Install the local secrets scan once: `pip install pre-commit && pre-commit install`.
3. If a key is ever committed or pasted somewhere public: tell Role 6 immediately and **revoke the key first**, then clean up. Deleting the commit is not enough: bots copy leaked keys within minutes.

## Automated checks (every push and pull request)

| Check | Tool | Blocks the merge |
|---|---|---|
| Secrets in the full Git history | Gitleaks | Always |
| Security tests (validation, rate limiting, headers, prompt-injection guard) | pytest | Always |
| Python code scan (SAST) | Bandit | Until the feature freeze (H18) |
| Known vulnerable dependencies (SCA) | pip-audit | Until the feature freeze (H18) |
| Container image vulnerabilities (fixable, high and critical) | Trivy | Until the feature freeze (H18) |

## Security controls in the application

- Strict input validation: invalid input returns `422`, never `500`.
- Rate limiting: per client IP and a global cap on AI routes (`429` with `Retry-After`).
- Security headers: Content-Security-Policy, HSTS (production), X-Content-Type-Options, Referrer-Policy, X-Frame-Options, Permissions-Policy.
- CORS restricted to the site's own origin.
- "Ask the data" prompt-injection guard (OWASP Top 10 for LLM Applications, LLM01), 4 layers.
- Generic error messages, request IDs, JSON logs with truncated IP addresses.
- Non-root Docker container with read-only application code and a health check.

## Data and privacy

- The app uses public NASA POWER data. It does not ask for accounts or personal data.
- Only computed statistics and the user's question are sent to the LLM provider. Free LLM tiers may use prompts to improve their models; do not type personal information in "Ask the data".
- Logs keep a truncated IP address (IPv4 /24, IPv6 /48), never the full address or the question text.

## After the hackathon

1. Revoke and rotate the LLM API key used during the event.
2. Remove the key from Render if the service is stopped.
3. Review who has write access to the repository.
