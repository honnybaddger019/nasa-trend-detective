# Role 6 - Manual Checklist (actions only a human with the accounts can do)

These steps need logins to GitHub, Render or the LLM provider. Nothing here can be automated from the kit.

## Before the event

- [ ] Create an account on the LLM provider chosen by the team (free tier).
- [ ] Create a **dedicated** API key for the hackathon (not a personal key used elsewhere).
- [ ] Set a spending limit or budget alert in the provider console (if the provider has a paid tier).
- [ ] Note the free tier quota (requests per minute and per day) to set `RATE_LIMIT_LLM_GLOBAL` below it.
- [ ] Create a Render account and connect it to GitHub.

## When write access to the repository is granted

- [ ] Run Gitleaks on the existing history (INTEGRATION.md, step 1).
- [ ] Ask Member 1 to enable GitHub Actions.
- [ ] Enable push protection for secrets:
  - Public repository: free. Settings > Advanced Security > Secret Protection > Push protection.
  - Private repository: needs GitHub Secret Protection (paid). Rely on the pre-commit hook + the CI scan instead.
- [ ] Enable private vulnerability reporting (Settings > Advanced Security).
- [ ] Optional: branch rule on `main` requiring the `security` checks.
- [ ] Ask every team member to run `pip install pre-commit && pre-commit install`.

## Deployment

- [ ] Create the Render service from `render.yaml` (Blueprint).
- [ ] Type `ALLOWED_ORIGINS`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` in the Render dashboard (never in Git).
- [ ] Confirm `TRUSTED_PROXY_HOPS` with `DEBUG_CLIENT_IP`, then set `DEBUG_CLIENT_IP=false`.
- [ ] Run `./scripts/smoke.sh <render-url>`: all checks must pass.

## During the event

- [ ] H18: set the repository variable `SECURITY_STRICT=false`.
- [ ] H19: "Wi-Fi off" drill with the team.
- [ ] Screenshots for the slide: green pipeline, smoke test output, injection table, Gitleaks blocking a fake key.
- [ ] 2 minutes before the pitch: open `<render-url>/health` to wake up the free instance.

## After the event

- [ ] Revoke the hackathon API key at the provider.
- [ ] Remove `LLM_API_KEY` from Render, or suspend the service.
- [ ] Review the repository collaborators.
