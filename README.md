# AI-Powered HR Recruitment Voice Agent (2-Day POC)

A narrowly scoped proof of concept for outbound AI candidate screening calls. The repository is the source of truth so development can continue with Codex, Cursor, Claude, or another coding agent.

## Scope
**P0 only:** candidate input, outbound call, AI introduction/consent, two-way screening conversation, configurable screening questions, contextual responses and basic follow-ups, transcript retrieval/storage, candidate information extraction, structured JSON, screening summary, call status, and a basic results dashboard.

**Out of scope:** ATS/HRMS integrations, multi-tenancy, authentication/RBAC, scheduling systems, WhatsApp/SMS, recruitment pipelines, multiple use cases, visual conversation builders, and enterprise features.

P1 vendor capabilities are documented/evaluated only. They are not part of implementation.

## Proposed stack
- Frontend: React + Vite + Material UI
- Backend: FastAPI
- Database: PostgreSQL
- Validation: Pydantic
- ORM: SQLAlchemy
- Local/deployment packaging: Docker
- Voice-provider candidates: undecided; compare multiple providers during Phase 2
- Provider abstraction: application code should not be coupled to one vendor

## Project status
- [x] Scope and BRD reviewed
- [x] Phase 0 project instructions and documentation scaffold (complete; accepted by owner)
- [x] Phase 1 candidate form and backend foundation (accepted by owner)
- [x] Phase 2 AI voice provider and technology evaluation (public-source research complete; provider selection remains undecided)
- [ ] Phase 3 controlled implementation and testing (Milestones 1-8 implemented; Milestone 9A research complete; Milestone 9B Bolna integration implemented behind disabled-by-default controls; no live calls performed)
- [ ] Phase 4 transcript, extraction, summary
- [ ] Phase 5 dashboard
- [ ] Phase 6 end-to-end POC validation and closeout

See `docs/PROJECT_PLAN.md` for phase-by-phase status and acceptance criteria.

## Development workflow
1. Open this repository in VS Code.
2. Use a coding agent (Codex recommended initially) and ask it to read `AGENTS.md` and the relevant docs before making changes.
3. Work on one phase at a time. Do not start a later phase until the current phase is reviewed and accepted.
4. Review the diff and run the listed checks.
5. Commit each approved phase using the commit convention in `AGENTS.md`.
6. Update project status and work log before finishing a phase.

## Configuration and secrets
Copy `.env.example` to `.env` when implementation begins. Never commit `.env`, provider API keys, phone credentials, candidate personal data, recordings, or transcripts from real candidates.

**Local-only POC:** authentication is out of scope. Keep the API, frontend, and database bound to the local machine. Do not expose this application or its candidate data to the public internet or an untrusted network.

## Phase 1 local setup

### Prerequisites
- Python 3.11 or newer
- Node.js 20.19 or newer (or 22.12 or newer) and npm
- Docker Desktop with Docker Compose v2, for the local PostgreSQL service

### Configure and start PostgreSQL
From the repository root, copy `.env.example` to `.env` and replace the placeholder `POSTGRES_PASSWORD` with a local development password. `DATABASE_URL` must use the same `POSTGRES_USER` and password, and must point to `POSTGRES_DB`; update both values in `.env` together if you change the database credentials. Do not commit `.env`.

```powershell
Copy-Item .env.example .env
docker compose up -d db
```

### Install and run the backend
In a new terminal from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://localhost:8000`; interactive API docs are at `/docs`. `GET /health` checks that the API process responds, and `GET /health/database` checks PostgreSQL connectivity. The migration command applies pending revisions; the duplicate-protection revision stops before changing records if it finds existing duplicate applications or invalid stored phone numbers.

### Phase 1 API
- `GET /health` — API process health.
- `GET /health/database` — database connectivity health.
- `POST /api/candidates` — validate and create a candidate (returns `201`).
- `GET /api/candidates/{candidate_id}` — fetch a candidate by UUID.
- `GET /api/candidates?limit=50&offset=0` — list candidates with bounded pagination.

### Install and run the frontend
In another terminal from the repository root:

```powershell
Copy-Item frontend/.env.example frontend/.env
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend reads `VITE_API_BASE_URL` from `frontend/.env`; the backend CORS origins are configured by `CORS_ORIGINS` in the root `.env`.

### Tests
From the repository root, after installing backend requirements:

```powershell
Set-Location backend
pytest
```

The backend tests use an isolated in-memory SQLite database; the application itself is configured for PostgreSQL. A frontend production bundle can be checked with `npm run build` from `frontend`.

An optional PostgreSQL integration test is available with `pytest -m postgres` from `backend`. It runs only when `TEST_DATABASE_URL` is explicitly set in the process environment, and accepts only a local database named `hr_voice_poc_test` that has no existing tables. It applies the migrations, exercises duplicate handling, then downgrades the test database to `base`. Never point this variable at `hr_voice_poc` or any database containing data. When the variable is unset, the integration test is skipped.

Stop the database with `docker compose down`. Add `-v` only when you intentionally want to delete the local database volume.

## Candidate consent and compliance
Use only test candidates who have agreed to participate in the POC. The calling agent must disclose that it is an AI recruitment assistant, explain the purpose, and ask whether the candidate is willing to continue. Recording/transcription disclosures and applicable Indian telecom/privacy requirements must be validated before any real deployment.

## Definition of Done
A candidate can be entered, receive an AI outbound call, complete an initial HR screening conversation, and have the call converted into a structured profile and summary displayed in the dashboard. The POC must also include documented vendor/pricing evidence, test outcomes, and limitations.

## Current implementation
Phase 0 documentation and Phase 1 implementation have been accepted by the owner. Phase 1 provides candidate intake through a React/Vite/Material UI form, a FastAPI API, and a PostgreSQL candidate table managed by Alembic. Candidate actual years of work experience is preliminary candidate information, separate from job requirements. Phase 3 adds screening foundations and a Bolna integration path that is disabled by default; no real provider calls have been made.

The Phase 1 candidate API prevents repeat applications for the same normalized phone number and normalized job title. Phone numbers are canonicalized to E.164 using India as the default region. The Alembic migration checks existing rows before adding the database uniqueness constraint and stops with candidate IDs if duplicate applications need manual review. Since this POC has no jobs table, the normalized job title identifies a role: distinct openings with the same title are treated as the same role. Any future change to phone or title normalization must use a new Alembic migration to backfill and check for collisions; do not edit an applied historical migration.

Phase 2 public-source research is complete. Bolna is the preferred integration target and Retell remains the backup; neither is finally selected. Phase 3 is underway. The mock provider remains the default. Bolna call initiation and execution-sync routes now use the existing lifecycle and M8 recruitment configuration, but return a disabled response unless `BOLNA_CALLS_ENABLED=true` is explicitly configured server-side. Do not enable it before the India route, compliance, consent, data-handling, cost, and owner-approval gates are cleared. No real call or provider request was made during implementation.

### Phase 3 offline foundation status
The backend includes a provider-neutral call record/event model, normalized status transitions, idempotent call-request/event handling, and a mock provider. `MOCK_CALLS_ENABLED` defaults to `false`; it only controls local mock calls. Bolna-specific call initiation and execution retrieval are exposed through server-side routes and are separately gated by `BOLNA_CALLS_ENABLED=false` by default. Retell remains offline-only. No public webhook route is exposed. Screening sessions retain a retrieved Bolna transcript, summary, duration, and raw extraction after a completed execution; raw extraction is not converted into screening answers or an evaluation because provenance and output mapping are not yet validated. LLM extraction, recording access, and voice cloning are not implemented.

For local lifecycle verification only, set `MOCK_CALLS_ENABLED=true` in the repository-root `.env`. `POST /api/candidates/{candidate_id}/calls` requires an `Idempotency-Key` header and returns a mock call record; `GET /api/calls/{call_id}` reads it. This switch enables only the mock provider. There is no public/provider webhook route and no live call implementation.

### Phase 3 Milestone 2 Bolna adapter
The offline adapter implements the documented `POST https://api.bolna.ai/call` contract with Bearer authentication, `agent_id` and `recipient_phone_number` request fields, and `execution_id` response mapping. `BOLNA_CALLS_ENABLED` defaults to `false`; `BOLNA_API_KEY` is a server-only `SecretStr`, `BOLNA_AGENT_ID` is required when enabled, and `BOLNA_TIMEOUT_SECONDS` defaults to 10 (greater than 0 and at most 120 seconds). These settings do not connect the adapter to the application API. No credentials are required for mocked tests.

The initial offline adapter supported only call creation. Milestone 9B extends the mapping and adds call initiation and execution retrieval; see the section below. Timeouts and uncertain creation outcomes require reconciliation. No retry configuration or provider idempotency key is used.

### Phase 3 Milestone 9B Bolna recruitment integration
`POST /api/screening-sessions/{session_id}/bolna-call` builds the M8 configuration, maps it into the documented `user_data` call field, and starts a Bolna execution through `CallLifecycleService`. It uses a stable screening-session idempotency key and links the application-owned call UUID to its screening session. A partial unique index also limits each candidate application to one Bolna call, including when another session or concurrent request attempts one. `GET` is not used for syncing: `POST /api/calls/{call_id}/bolna-sync` explicitly retrieves the execution and updates normalized lifecycle status. Both routes are unavailable unless `BOLNA_CALLS_ENABLED=true`; this switch remains false in `.env.example`. The API key and agent ID remain server-side.

Only documented call fields are sent: `agent_id`, `recipient_phone_number`, and optional `user_data`. Candidate phone and email are omitted from agent context; the normalized phone is used only as the required call destination. The configured Bolna agent must already consume the dynamic `user_data` placeholders. The application does not create or update the provider agent. Provider status `call-disconnected` maps to nonterminal `finalizing`; a later `completed` event finalizes the call. Retrieval stores transcript, summary, duration, and provider extraction on the screening session. Extraction remains raw and advisory; it is not mapped into answers or hiring recommendations.

The webhook processor is an offline service foundation with shared-secret validation and idempotent event IDs; there is no HTTP webhook route. Bolna's signed-webhook scheme, delivery retries, and stable event identifiers remain unverified. See [Milestone 9B integration notes](docs/MILESTONE_9B_BOLNA_INTEGRATION.md). Migration `0007_bolna_finalization` is required to add the `finalizing` status constraint and screening-result columns. It has not been applied to any database.

### Phase 3 Milestone 4 recruitment screening foundation
The backend exposes `POST /api/screening-sessions` and `GET /api/screening-sessions/{session_id}`. A session stores its configurable question snapshot and may reference one existing call belonging to the same candidate. The default questions cover willingness to continue, interest, total/relevant experience, skills, compensation, notice period, location/work arrangement, and interview availability.

Session status is updated through `POST /api/screening-sessions/{session_id}/status`. A session cannot be marked completed until every required question has a recorded non-missing answer; unresolved sessions can be marked incomplete. Answers are upserted at `POST /api/screening-sessions/{session_id}/answers/{question_key}` and listed at `GET /api/screening-sessions/{session_id}/answers`. Each answer preserves the original response, optional normalized value, explicit/inferred source, confidence, or a missing marker without fabricated values. Evaluations are manually supplied and validated at `POST /api/screening-sessions/{session_id}/evaluation`, then read through the matching GET route. Populated evaluation facts require explicit/inferred provenance; candidate name and job title come from the candidate record. Recommendations are advisory only.

Migration `0005_screening_workflow` creates the session, answer, and evaluation tables after `0004_call_outcomes`. It has not been applied. This foundation does not make calls, process transcripts, integrate an LLM, or automatically extract answers or recommendations.

### Phase 3 Milestone 5 simulated conversation orchestrator
The provider-independent orchestrator is a deterministic text-only state machine. Start/resume with `POST /api/screening-sessions/{session_id}/conversation`; the first prompt includes AI identity and the role, then asks the configured question. Responses require both the active `question_key` and an explicit disposition (`answer`, `unclear`, `no_response`, `decline_to_answer`, `skip`, `stop`, `repeat`, or `clarification`). The system does not classify text or extract meaning.

Use `GET /api/screening-sessions/{session_id}/conversation` for state and current prompt, and `GET /api/screening-sessions/{session_id}/conversation/turns` for ordered text history. Additional simulation actions are `POST .../response`, `POST .../repeat`, `POST .../clarify`, `POST .../interrupt`, and `POST .../end` under the same conversation path. A stale response question key is rejected so an answer cannot silently attach to the next question.

Unclear or absent required responses prompt a clarification until the configured maximum (default 2, allowed 1-5). At the limit the raw response remains in turn history, the answer is marked missing, and the flow advances. A refusal/skip marks the question missing and continues; if any required question remains missing at the end, the screening session is `incomplete`. A candidate stop sets both conversation and screening session to `declined`. An explicit interrupt keeps the screening session in progress; resuming repeats the active question. Manual end marks the session incomplete. Required answers must be present before completion.

Revision `0006_screening_conversations` creates conversation state and turn-history tables after `0005_screening_workflow`; it has not been applied. This is simulation only: no speech, transcription, provider calls, LLM, semantic answer validation, audio, or recordings are involved.

### Phase 3 Milestone 6 AI intelligence boundary (offline)
The existing response endpoint also accepts an explicit `intelligence_scenario` fixture instead of a manual disposition. It runs through the provider-independent `ResponseInterpreter` contract and validated `ResponseInterpretation` schema, then hands only the disposition and answer metadata to the deterministic conversation service. The active question key always comes from the conversation record. The scenario name selects a known test fixture; it does not ask the mock to infer arbitrary text.

The mock supports fixed clear/unclear/no-answer/repeat/refusal/stop cases and a fixed experience example. The example's structured value is fixture output, not general extraction quality. Context includes only the active question, bounded job context, and a configurable number/size of recent text turns. On provider, context, or schema failure, the raw response is retained in turn history and the safe fallback requests clarification without storing an extracted answer. Existing manual disposition requests remain supported.

`INTELLIGENCE_PROVIDER=mock` remains the only supported/default provider. Model identifier, timeout, response-size, context-turn, and context-size settings are non-secret placeholders; no LLM credentials or adapter exist. No migration was needed because answer provenance/value fields already exist. Actual LLM integration, semantic interpretation, automatic extraction, and prompt design remain future work.

### Phase 3 Milestone 7 native voice AI evaluation
The preferred 2-day POC baseline is each shortlisted voice provider's native/bundled conversational stack, without a separate LLM by default. Public-source comparison and the disabled, provider-neutral agent configuration template are in [Milestone 7 evaluation](docs/MILESTONE_7_NATIVE_VOICE_AI_EVALUATION.md) and [native agent template](docs/native_recruitment_agent.example.json). Bolna and Retell remain unselected. Hindi and Hinglish are POC validation scenarios; the BRD's P1 priority has not been changed. No public-source capability claim is treated as measured performance.

India outbound calling remains a mandatory gate and is not passed for either provider. The current app API remains mock-only and call execution defaults to disabled. No provider account, API, paid use, agent configuration, real call, candidate data transfer, webhook/tunnel, or external LLM was used. Controlled testing requires separate approval of the route, test participants/data, retention, configuration, and spend ceiling. The template JSON is not loaded by the application.

### Phase 3 Milestone 8 recruitment agent configuration foundation
The `app.recruitment_agent` package builds a validated, provider-neutral configuration from an existing candidate, screening-session question snapshot, and saved answers. It preserves question order, required status, categories, follow-up guidance, and explicit/inferred/missing answer provenance. Candidate phone is omitted by default and can only be included through an explicit builder option. Candidate job context uses fields already present in the application; no job requirements are inferred from the job description.

`RecruitmentAgentPreparationService` passes this configuration to the local `MockAgentConfigurationConsumer` for deterministic inspection. This consumer validates and retains an in-memory copy; it is not an AI agent and has no call method. At the end of M8, no migration was needed and provider translation was deferred. M9B subsequently added Bolna-specific `user_data` translation and result retrieval as described below; Retell translation remains unimplemented. English/Hindi/Hinglish are instruction options only; quality has not been tested.

### Phase 3 Milestone 3 Retell adapter
The offline adapter implements `POST https://api.retellai.com/v2/create-phone-call` with Bearer authentication, E.164 `from_number` and `to_number`, and optional `override_agent_id`. It maps `call_id` to the internal provider call ID and validates the documented `call_status`, `agent_id`, and `call_type` response fields. `RETELL_CALLS_ENABLED` defaults to `false`; the adapter is not registered in the application route. `RETELL_API_KEY` remains server-side, and `RETELL_FROM_NUMBER` must be E.164 before explicit adapter construction.

Retell statuses map as follows: `registered` → `queued`, `not_connected` → `no_answer`, `ongoing` → `in_progress`, `ended` → `completed`, and `error` → `failed`. Unknown statuses make the outcome ambiguous and require reconciliation. Timeouts, transport failures, 429, server errors, and malformed success responses also require reconciliation. No automatic retries are made. `GET /v2/get-call/{call_id}` is documented, but retrieval is not implemented because the verified evidence does not establish the response schema and reconciliation semantics needed to use it safely.
