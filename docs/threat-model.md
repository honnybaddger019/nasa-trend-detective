# EarthTrend AI - Threat Model

Owner: Role 6 (Security & Platform Engineer). Method: STRIDE (Microsoft).
Scope: the public website (static front end + FastAPI backend), the LLM call, the NASA POWER call, the GitHub repository and the deployment on Render.

## 1. Assets

| Asset | Why it matters |
|---|---|
| LLM API key | Paid or quota-limited; a leak means a bill, a revoked key and a dead "Explain with AI" button during the demo |
| LLM quota / credits | Free tiers allow few requests per minute; exhausting them breaks the demo |
| Site availability | The jury must see a working site at pitch time |
| Integrity of the numbers shown | The project's value is honest statistics from NASA data |
| Credibility of the AI text | The pitch promises "the data shows, not causes"; a hijacked answer breaks that promise |

## 2. Data flow and trust boundaries

```
 Browser (untrusted input)                       Trust boundary (security.py)
 static/index.html  --HTTPS-->  SecurityMiddleware: body limit, headers, request ID, generic errors
                                CORS (allowed origins only)
                                Rate limiter (per IP + global on LLM routes)
                                Pydantic validation (422)
                                        |
                                FastAPI routes (server.py, Member 4)
                                  |                          |
                     NASA POWER API (HTTPS,          LLM provider (HTTPS)
                     timeout + retry + CSV cache)    only the stats dict + escaped, tagged question
                                                     guard system prompt, output filter, fallback text

 CI (GitHub Actions): Gitleaks, Bandit, pip-audit, security tests, Trivy
 Platform: Docker image (non-root, read-only code), Render (HTTPS, health check)
```

## 3. STRIDE table - every threat points to a control and a test

| # | STRIDE | Threat | Component | Control (code) | Test / evidence |
|---|---|---|---|---|---|
| S1 | Spoofing | Another website calls our API from a visitor's browser | Backend | CORS restricted to `ALLOWED_ORIGINS` (`install_security`) | `test_headers.py::test_cors_allows_only_the_configured_origin` |
| S2 | Spoofing | A client forges `X-Forwarded-For` to dodge the rate limit | Backend | Client IP taken from the trusted proxy hop only (`client_ip`, `TRUSTED_PROXY_HOPS`) | `test_rate_limit.py::test_forged_x_forwarded_for_cannot_bypass_the_limit` |
| T1 | Tampering | Tampered parameters (lat, lon, years, variable) to crash or abuse the analysis | Backend | `AnalyzeRequest` / `CompareRequest`: bounds, JSON numbers only, allow-list of variables, minimum period, unknown fields rejected | `test_validation.py` (40+ cases, fuzz test: never a 500) |
| T2 | Tampering | A question rewrites the LLM instructions (prompt injection, OWASP LLM01) | LLM | 4 layers: input filter, tagged + escaped data, stats-only context, output filter (`guarded_ask`) | `test_injection.py` (10 annex attacks + variants), `scripts/live_injection_eval.py` |
| T3 | Tampering | The browser sends fake statistics, or instructions hidden in them, to the LLM | LLM | `api/server.py`: the `stats` / `computed_results` sent to `/explain` and `/ask` are bounded (size, depth, types, text length) and every key and text value goes through the injection filter (422); the AI answer is filtered on output. `AskRequest` (parameters only, stats recomputed on the server) remains the target design | `test_api_server.py::test_explain_rejects_tampered_or_oversized_stats`, `test_api_server.py::test_ask_rejects_injection_hidden_in_computed_results`, `test_injection.py::test_attack5_tag_escape_cannot_replace_the_real_numbers` |
| R1 | Repudiation | No way to know who caused an error or an abuse | Backend | JSON access logs: request ID, truncated IP, route, status, duration; events `rate_limited`, `prompt_injection_blocked`, `llm_fallback` | Logs visible in Render; `X-Request-ID` header (`test_headers.py`) |
| I1 | Information disclosure | API key committed to the repository | Repo | `.gitignore`, pre-commit Gitleaks, Gitleaks in CI on the full history, GitHub push protection | CI job `secrets`, `gitleaks dir .` |
| I2 | Information disclosure | API key or stack trace in an error message | Backend | Generic 500 body with a request ID only; 422 bodies never echo input; provider errors logged by status code only | `test_headers.py::test_unexpected_error_gives_generic_500_without_details`, `test_validation.py::test_422_does_not_echo_submitted_values` |
| I3 | Information disclosure | The LLM reveals its system prompt | LLM | No secret in the context; per-process canary in the system prompt; leaked answers replaced by the refusal | `test_injection.py::test_system_prompt_leak_is_replaced_by_refusal` |
| I4 | Information disclosure | XSS steals data from visitors | Front end | Strict CSP (no inline script), HTML stripped from LLM output, front end uses `textContent` | `test_headers.py::test_csp_*`, `test_injection.py::test_attack9_output_is_plain_text` |
| D1 | Denial of service | Mass calls to `/explain` or `/ask` burn the LLM quota | Backend / cost | Rate limit per IP + global cap, response cache, bounded concurrency, capped `max_tokens` | `test_rate_limit.py` (429 on the 11th call, global cap with IP rotation) |
| D2 | Denial of service | Huge request bodies | Backend | `MAX_BODY_BYTES` limit (413), question length 3-300 (422) | `test_headers.py::test_body_larger_than_limit_gives_413` |
| D3 | Denial of service | NASA API slow or network down | Network | Timeout + retry snippet (Member 2), CSV cache (Member 2), "Wi-Fi off" drill | `test_nasa_fetch.py`, drill at H19 |
| D4 | Denial of service | LLM provider down or quota exceeded | LLM | Every provider error becomes the fallback template text (Member 4) | `test_injection.py::test_llm_failure_gives_fallback_text`, `test_llm_client.py` |
| E1 | Elevation of privilege | Code execution through a vulnerable dependency or the container | Platform | Pinned dependencies + pip-audit, Bandit, slim image + Debian security updates + Trivy, non-root user, read-only code | CI jobs `code` and `container` |
| E2 | Elevation of privilege | A compromised GitHub Action steals the repository token | CI | Actions pinned by commit SHA, `permissions: contents: read`, `persist-credentials: false` | `.github/workflows/security.yml` |

## 4. Residual risks (accepted for a hackathon)

- `/explain` and `/ask` in `api/server.py` receive statistics computed in the browser session. They are bounded and scanned, but a user can still send plausible fake numbers and get an explanation of them; only that user sees the result. Recomputing the statistics on the server from validated parameters removes this risk.
- In-memory rate limiting is per process: fine for one Render instance, not for several replicas (would need Redis).
- The layer-1 pattern filter can be bypassed by a creative attacker; layers 2-4 carry the real defence, and the worst outcome is an off-topic answer, never a secret leak (no secret is in the context).
- A free LLM tier may use prompts to improve its models. Only public NASA statistics and the user's question are sent; no personal data is collected.
- The Render free plan sleeps when idle: the first request can take up to a minute (warm up `/health` before the pitch).
