# Role 6 - Integration Guide (day of access to the team repository)

Target: from "write access granted" to "security pipeline green + site deployed" in less than 30 minutes.
Repository: `honnybaddger019/nasa-trend-detective` (checked on 2026-11-15: public, one initial commit, README only).

Each step has a **Done when** check. Do them in order.

---

## Step 1 - Scan the existing history BEFORE adding anything (2 min)

```bash
git clone https://github.com/honnybaddger019/nasa-trend-detective.git
```

```bash
cd nasa-trend-detective && gitleaks git . --no-banner --redact -v
```

If Gitleaks finds a key: **revoke the key at the provider first**, then tell the team. Removing the commit does not make the key safe again.

**Done when:** `no leaks found`.

## Step 2 - Copy the kit into the repository (3 min)

Run from the folder that contains both `role6-kit/` and `nasa-trend-detective/` (works in Git Bash on Windows too):

```bash
cd role6-kit && cp -r security.py llm_client.py examples snippets tests scripts docs static .github Dockerfile .dockerignore render.yaml requirements-security.txt requirements-dev.txt .pre-commit-config.yaml .env.example SECURITY.md INTEGRATION.md MANUAL-CHECKLIST.md ../nasa-trend-detective/ && cd ..
```

`README.md`, `requirements.txt` and `.gitignore` are not copied: they belong to the team and are merged below. Existing team folders (`tests/`, `docs/`, `static/`) are merged, not replaced.

Then merge the three files that the team may already have:

```bash
cat role6-kit/.gitignore >> nasa-trend-detective/.gitignore
```

```bash
echo "-r requirements-security.txt" >> nasa-trend-detective/requirements.txt
```

Copy `docs/README-security-section.md` into the team `README.md` (section "Security") and replace `OWNER/REPO` in the badge URL if the repository name changed.

**Done when:** `git status` shows the new files and `.gitignore` contains `.env`.

## Step 3 - Local checks on the laptop (5 min)

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
```

```bash
pytest tests/role6_security -q
```

```bash
bandit -r . -x ./tests,./static,./.venv -ll && pip-audit -r requirements.txt
```

```bash
pip install pre-commit && pre-commit install
```

**Done when:** all tests pass, Bandit and pip-audit report nothing.

## Step 4 - Plug security.py into server.py (with Member 4, 15 min)

**Status (2026-11-15): done.** Member 4's backend is `api/server.py` (run with `uvicorn api.server:app`). It keeps Member 4's routes and response keys, adds `install_security`, `@limit_compute` on `/forecast`, `/backtest`, `/anomalies`, `@limit_llm` on `/explain` and `/ask`, strict bounded models, the injection guard and the output filter. `/explain` and `/ask` now also return a `source` field (`llm`, `guard` or `fallback`). It imports Member 4's `ai` package (`ai/forecasting.py`, `ai/anomalies.py`, `ai/explanation.py`): Member 4 pushes `ai/` and adds its dependencies to `requirements.txt`, but does not push another copy of `api/server.py`. Tests: `tests/role6_security/test_api_server.py` (the `ai` package is stubbed). The generic pattern below stays as a reference.

Member 4 owns `server.py`. The changes are:

```python
from fastapi import FastAPI, Request
from llm_client import LLMClient
from security import AnalyzeRequest, AskRequest, guarded_ask, guarded_explain, install_security, limit_compute, limit_llm, request_id_of

app = FastAPI()
install_security(app)          # 1. once, right after app = FastAPI()
llm = LLMClient.from_env()     # 2. once, at startup

@app.post("/analyze")
@limit_compute                 # 3. under the route decorator of CPU-heavy routes
async def analyze(request: Request, body: AnalyzeRequest): ...

@app.post("/explain")
@limit_llm                     # 4. under the route decorator of each LLM route
async def explain(request: Request, body: AnalyzeRequest):
    stats = compute_stats(body)
    return await guarded_explain(llm, base_system_prompt=MEMBER4_PROMPT, stats=stats,
                                 fallback_text=fallback_text(stats), request_id=request_id_of(request))
```

Rules:
- Every rate-limited route must take `request: Request` as an argument.
- `/ask` takes `AskRequest` (parameters + question). The server recomputes the stats; the browser never sends stats.
- Member 4 keeps `MEMBER4_PROMPT` and `fallback_text()`. `security.py` appends the guard.
- Do not pass `temperature` to Claude models: current models reject it with a 400 error. `llm_client.py` already handles this.
- `examples/demo_server.py` is the complete working reference.

**Done when:** `pytest tests/role6_security -q` still passes and `./scripts/smoke.sh` passes against `uvicorn api.server:app --port 8000`.

## Step 5 - Notes for Members 2 and 5 (5 min)

**Member 2 (data):** wrap the NASA call in `get_nasa_data()` with the snippet:

```python
from snippets.nasa_fetch import NasaUnavailable, fetch_power
try:
    payload = fetch_power(POWER_URL, params)
except NasaUnavailable:
    ...  # Member 2's CSV cache takes over
```

Runtime cache files must be written to `data/` (the only writable folder in the container).

**Member 5 (front end):**
1. Display every AI answer with `element.textContent = answer`. **Never `innerHTML`.** This is the main XSS defence.
2. Error codes to handle: `422` (invalid input: show "Please check the region, years and variable"), `429` (show "Too many requests, please wait a minute"), `413` (question too long), `500` (show "Something went wrong" and the `request_id`).
3. The `source` field of `/ask` and `/explain` is `llm`, `guard` or `fallback`. Optionally show a small "template text" label when it is `fallback`.
4. CSP check: open the site with the browser console. Any `Content-Security-Policy` error must be fixed by adding the host to `CSP_EXTRA_SCRIPT_SRC` or `CSP_EXTRA_CONNECT_SRC`, not by removing the policy. Do not use inline `<script>` blocks or `onclick=` attributes: move the code to a `.js` file.
5. If a third-party library breaks with the CSP during development, set `CSP_REPORT_ONLY=true` temporarily and report it to Role 6.

**Done when:** the dashboard renders with no CSP error in the console.

## Step 6 - Push and enable GitHub protections (5 min)

```bash
git checkout -b role6-security && git add -A && git commit -m "Add security layer, CI pipeline and hardened deployment (Role 6)"
```

```bash
git push -u origin role6-security
```

Open a pull request. Then, with Member 1 (repository owner), in GitHub **Settings**:

1. **Actions > General**: allow GitHub Actions.
2. **Advanced Security** (or **Code security**): enable **Secret Protection > Push protection** and **Private vulnerability reporting** (free for public repositories).
3. **Branches**: add a rule for `main` requiring the `security` checks to pass (optional but recommended).

**Done when:** the 3 jobs of the `security` workflow are green on the pull request. Screenshot it for the slide.

Optional proof for the slide: on a throwaway branch, commit a fake key and show Gitleaks blocking it, then delete the branch.

## Step 7 - Deploy on Render (10 min)

1. Render dashboard: **New > Blueprint**, select the repository. Render reads `render.yaml`.
2. Fill the variables marked "sync: false":
   - `ALLOWED_ORIGINS` = the Render URL, e.g. `https://earthtrend-ai.onrender.com`
   - `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` = see step 8 (use `LLM_PROVIDER=none` until the free offer is known; the fallback text is used).
3. Wait for the deployment, then check the client IP detection:

```bash
curl -s https://earthtrend-ai.onrender.com/health
```

```bash
curl -s https://api.ipify.org
```

The `client_ip` value from `/health` must equal your public IP from the second command. If it shows another address (a proxy), raise `TRUSTED_PROXY_HOPS` by 1 and redeploy; if `x_forwarded_for` is empty, set `TRUSTED_PROXY_HOPS=0`. When correct, set `DEBUG_CLIENT_IP=false`.

4. Run the smoke test against production:

```bash
./scripts/smoke.sh https://earthtrend-ai.onrender.com
```

**Done when:** `ALL CHECKS PASSED`, including the HSTS header.

## Step 8 - When the free LLM offer is known (5 min)

Set in Render (never in the repository):

| Provider | `LLM_PROVIDER` | `LLM_MODEL` example |
|---|---|---|
| Google Gemini (free tier) | `gemini` | the model name given by Google AI Studio |
| Groq | `groq` | a model listed in the Groq console |
| OpenRouter (free models) | `openrouter` | a model id ending in `:free` |
| Mistral | `mistral` | a model listed in the Mistral console |
| Anthropic Claude | `anthropic` | `claude-opus-5-5` (default) |
| Other OpenAI-compatible API | `openai_compatible` + `LLM_BASE_URL` | per provider |

Then:
1. Set `RATE_LIMIT_LLM_GLOBAL` **below** the provider's requests-per-minute quota (e.g. quota 15/min -> `12/minute`).
2. Set a spending limit or budget alert in the provider console, and use a key dedicated to the hackathon.
3. Run the live attack evaluation once and paste the table into the README:

```bash
python scripts/live_injection_eval.py https://earthtrend-ai.onrender.com
```

**Done when:** 10/10 without automatic failure and every `CHECK` line read by hand.

## Step 9 - Timeline checkpoints

| When | Action |
|---|---|
| H18 (feature freeze) | Repository variable `SECURITY_STRICT=false` (Settings > Secrets and variables > Actions > Variables). Only Gitleaks and the tests keep blocking. |
| H19 | "Wi-Fi off" drill: run the demo with the network cut. Expected: NASA data from the CSV cache, AI text from the fallback template, no crash, no error 500. |
| H20-H22 | Security slide and README section (see `docs/README-security-section.md`). |
| 2 minutes before the pitch | Open `/health` on the Render URL to wake up the free instance. |
| Right after the event | Revoke and rotate the LLM API key. |

Local "Wi-Fi off" run with Docker:

```bash
docker build -t earthtrend . && docker run --rm -p 8000:8000 -e ALLOWED_ORIGINS=http://localhost:8000 earthtrend
```
