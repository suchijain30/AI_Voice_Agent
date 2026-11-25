# Agent Instructions — AI HR Recruitment Voice Agent POC

## Mission
Build a working HR recruitment outbound-screening POC within a two-day MVP constraint. Optimize for a demonstrable end-to-end workflow, not platform completeness.

## Mandatory workflow
1. Read `README.md`, `docs/POC_SCOPE.md`, `docs/PROJECT_PLAN.md`, and relevant architecture/decision documents before coding.
2. Work on **one phase only** at a time.
3. Before a significant architectural, dependency, provider, data-model, or scope change, stop and ask the project owner for approval. Do not silently make the change.
4. At phase start, state the intended changes and acceptance criteria. At phase end, report files changed, tests/checks run and results, limitations, and remaining work.
5. Do not begin the next phase until the owner explicitly approves.
6. Update `docs/PROJECT_PLAN.md` and `docs/WORK_LOG.md` with progress.
7. Prefer small, reviewable changes. Avoid unrelated refactors.

## Scope guardrails
Implement only P0 listed in `docs/POC_SCOPE.md`.
Do not implement ATS/HRMS, multi-tenancy, authentication, RBAC, scheduling workflows, WhatsApp, SMS, recruitment pipelines, multiple use cases, enterprise platform features, or P2 features unless the owner explicitly changes scope.
P1 vendor capabilities are for research, comparison, and documentation only—not implementation.

## Architecture guardrails
- Frontend: React + Vite + Material UI.
- Backend: FastAPI.
- Database: PostgreSQL unless the owner approves a change.
- Use Pydantic schemas for API and structured candidate outputs.
- Keep voice-provider integration behind an adapter/interface. Candidate evaluation and screening logic must not depend on vendor-specific types.
- Keep screening questions configurable; do not bury question definitions in calling-provider code.
- Keep secrets in environment variables. Never commit `.env`, credentials, API keys, private phone numbers, or real candidate data.
- Avoid premature abstraction: implement only the provider-interface methods needed for the POC.
- Do not introduce infrastructure/services that are unnecessary for the two-day demo.

## Quality rules
- Add focused tests for meaningful logic and bug fixes.
- Run relevant formatting, linting, and tests where configured.
- Do not claim tests passed unless they were actually run.
- Handle provider failures, incomplete answers, declined calls, disconnects, and webhook retries defensively.
- Logs must not expose secrets or unnecessary personal information.
- Distinguish candidate-stated facts from inferred/AI-generated assessments.
- Recommendations are advisory; final recruitment decisions belong to recruiters.

## Git rules
Use Conventional Commit style:
- `feat: ...`
- `fix: ...`
- `docs: ...`
- `test: ...`
- `chore: ...`

Each phase should have a small number of commits with clear messages. Commit descriptions or work-log entries must explain:
- Completed work
- Validation performed
- Remaining work
- Known limitations

Do not create a commit unless the owner requests it or has approved the phase's commit policy. Never rewrite or force-push history without explicit approval.

## Documentation
Keep README setup instructions accurate. Update architecture/decision docs when approved decisions change. Record vendor claims as `Verified`, `Unverified`, `Native`, `Integration`, `Custom`, or `Unsupported`, with evidence where possible. Never invent pricing or feature support.

## Stop conditions
Ask the owner before:
- Changing the selected stack or database
- Adding a provider or paid service
- Expanding scope
- Adding authentication or enterprise features
- Making a destructive database/schema migration
- Changing consent/recording behavior
- Deploying or initiating calls to real candidates
