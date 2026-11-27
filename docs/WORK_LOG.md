# Work Log

## Phase 0 — Documentation scaffold
**Status:** Completed; documentation accepted by the owner.
**Repository state:** Scaffold is tracked on `main`; the initial setup commit exists locally and has been pushed to `origin/main`. The working tree was clean when reviewed.

### Included
- README and scope summary
- AGENTS.md coding-agent rules
- Phase plan and acceptance criteria
- Proposed architecture
- Decision log
- Work log
- `.gitignore`
- `.env.example`

### Validation
- Documentation scaffold is present and tracked in the repository.
- Repository state recorded from the owner's provided facts: `main`, clean working tree, and initial setup pushed to `origin/main`.
- No application code, credentials, calls, or deployment actions performed.

### Remaining
- Phase 1 started after explicit owner approval; see the Phase 1 work-log entry below.

## Phase 1 — Candidate input and backend foundation
**Status:** Complete; accepted by the owner on 2026-11-26.
**Started:** 2026-11-25, following the owner's Phase 1 request.

### Planned
- Build a React/Vite/Material UI candidate form and simple candidate list.
- Add FastAPI health and candidate endpoints backed by SQLAlchemy/PostgreSQL.
- Add an Alembic migration, local PostgreSQL setup, configuration examples, and focused backend tests.
- Document setup, run, and test commands.

### Scope limits
- Candidate years of experience is preliminary candidate information, not a job requirement.
- No voice provider, calls, AI screening, transcript, or Phase 2 features.

### Implemented
- Responsive React/Vite/Material UI candidate form with required-field, phone, email, and experience validation; submit state, success/error feedback, duplicate-submit prevention, reset, and a recent-candidate list.
- FastAPI health/database-health routes and candidate create, retrieve, and paginated list endpoints.
- SQLAlchemy candidate model and initial Alembic migration for PostgreSQL; runtime configuration and CORS are environment-based.
- Root Docker Compose PostgreSQL service and setup/run/test instructions in the README.
- Duplicate application protection using E.164 phone normalization (India default), normalized job-title keys, API 409 responses, and a database unique constraint.
- New Alembic revision `0002_prevent_duplicate_applications`; it backfills normalized keys and aborts with candidate IDs before changing records if existing normalized duplicates are found. The already-applied `0001` migration is unchanged.

### Validation performed
- Phase 1 baseline backend suite before duplicate-prevention changes: 9 passed. Tests use an isolated SQLite database.
- Frontend: `npm run build` — passed.
- Migration: `python -m alembic -c backend/alembic.ini upgrade head --sql` — passed; generated PostgreSQL migration SQL.
- `git diff --check` — passed.
- Duplicate-prevention tests cover same/different phone and role combinations, phone formatting, title case/whitespace, invalid phones, a unique-constraint race violation, concurrent database inserts, unrelated database failures, and migration duplicate preflight.
- Full backend suite after this change: 18 passed.
- PostgreSQL could not be started or tested in this environment because Docker and PostgreSQL tools are not installed. Frontend unit tests are not configured; the production build was checked instead.
- Initial npm audit identified vulnerable Vite 5/esbuild versions. Vite and its compatible React plugin were upgraded within the agreed Vite stack; the final `npm install` audit reported 0 vulnerabilities. A separate `npm audit` request could not reach the registry audit endpoint.

### Remaining
- The owner accepted the implementation based on completed testing, validation, and review on 2026-11-26.
- Validate migration and API behavior against a running PostgreSQL instance.
- Apply revision `0002_prevent_duplicate_applications` locally after reviewing any migration preflight errors; resolve reported duplicates manually before retrying.

## Phase 1 review remediation — 2026-11-26
**Status:** Implemented and accepted by the owner on 2026-11-26.

### Implemented
- Removed the embedded database URL credential. `DATABASE_URL` is now required, validated as non-empty, and loaded from the process environment or repository-root `.env`; missing configuration produces a clear startup error.
- Candidate list states now distinguish loading, empty, populated, and error states. Errors include an inline Retry button that repeats the list request.
- Added opt-in PostgreSQL integration-test support using only `TEST_DATABASE_URL`. It accepts a local, empty `hr_voice_poc_test` database, applies migrations, checks concurrent duplicate submissions, and downgrades that test database during cleanup. It never falls back to `DATABASE_URL`.
- Documented local-only operation, the same-title role identity limitation, and the requirement to use a new migration for future normalization changes.
- Tightened local-only bindings for Vite and the Compose PostgreSQL port. Added ignore rules for pytest temporary directories, SQLite files, and coverage artifacts.

### Validation performed
- Backend: `python -m pytest -q` — 20 passed, 1 skipped, 1 existing Starlette deprecation warning.
- PostgreSQL integration test: skipped because `TEST_DATABASE_URL` was not configured. No PostgreSQL migration or candidate data was touched.
- Frontend: `npm run build` — passed.
- Credential-pattern check of `backend/app/config.py` — no embedded credential-style database URL found. `.env` contents were not inspected or displayed.
- `.gitignore` checks confirmed `.env`, `.venv`, frontend dependencies/build output, and pytest cache are ignored. `.pytest_tmp/`, SQLite, and coverage artifact rules were added.
- `git diff --check` — passed (only Git line-ending warnings).
- No files were staged, committed, or pushed.

### Remaining
- If PostgreSQL integration coverage is desired, create an empty local `hr_voice_poc_test` database and set `TEST_DATABASE_URL` explicitly before running `pytest -m postgres` from `backend`.
- Rotate the previously embedded database password if it is valid. No password rotation was performed.

## Environment example credential correction — 2026-11-26
**Status:** Corrected; included in the owner's Phase 1 acceptance on 2026-11-26.

- Replaced the tracked `.env.example` password with a placeholder and aligned its `DATABASE_URL` username/password with the example PostgreSQL user and database. Secret values were not displayed.
- Confirmed Docker Compose defaults to the same `hr_voice_user` account used in the example. Updated the README to say the application URL and PostgreSQL variables must stay in sync.
- No local `.env` file was read or changed, and no database was accessed. Rotate the former example credential if it was valid or reused elsewhere; rotation was not performed.
- Git state and push status on another machine were outside this correction and are not asserted here.

## Phase 2 evaluation plan — 2026-11-26
**Status:** Plan approved by the owner; public-source evaluation in progress; controlled testing not started.

- Owner confirmed Phase 1 acceptance based on completed implementation, testing, validation, and review.
- Updated the proposed phase sequence so Phase 2 covers evidence-based voice platform, LLM, STT, TTS, India telephony, complete-architecture, benchmark, controlled-test, statistical, and cost evaluation. Moved vendor comparison and pricing deliverables from Phase 6 into Phase 2.
- Provider selection remains undecided. Phase 2 acceptance requires an evidence-backed recommendation and owner review; provider-account creation, paid usage, real calls, and sharing real candidate data require separate explicit approval.
- Public-source review has begun for voice platforms, component providers, India telephony, and applicable TRAI numbering guidance. Initial source register and current findings are being recorded in `docs/AI_Provider_Evaluation_Journey.docx`.
- Early official-page snapshots show non-comparable pricing models: per-minute managed platforms (Retell, Bolna, Bland), component + transport pricing (Vapi), and modular session/model/telephony pricing (LiveKit). India-specific speech candidates include Sarvam and Gnani; Gnani and Ozonetel/KooKoo were added as relevant alternatives, not presumed winners.
- TRAI sources make numbering/registration classification a mandatory open gate; applicability to recruitment screening calls has not been determined. Published language, latency, quality, and availability statements remain vendor claims unless independently tested.
- Owner refinement: use a platform-first evaluation. Compare managed platforms with their built-in/recommended full stacks, test LLM options where supported, and treat standalone STT/TTS as fallback/optimization paths only for a demonstrated shortfall. India outbound telephony remains a mandatory gate; a modular architecture must justify its added engineering effort.
- No provider accounts, APIs, paid usage, external-data experiments, integrations, or calls have been used. Provider selection remains undecided.

### Phase 2 public-source platform review — 2026-11-26

- Expanded `docs/AI_Provider_Evaluation_Journey.docx` with a platform-first comparison of Retell, Vapi, and Bolna; screened Bland for India-route relevance; added India outbound gate analysis, indicative five-minute price arithmetic, evidence ledger, conditional shortlist, and unresolved questions.
- Public documentation shows Bolna has the most India-specific telephony evidence in this scan (carrier/SIP integration listings and a vendor claim about regulated numbers), but the actual number series, recruitment-call classification, carrier route, and all-in price remain unverified. It is a conditional pilot lead, not a selected provider or a passed gate.
- Retell documents generic custom SIP and outbound calls, but no reviewed public source confirms a compliant India mobile route. Vapi's Plivo integration specifically says Indian numbers cannot be used on that route; this restriction is not generalized to all Vapi configurations. A different compliant route remains unverified.
- Bland's number documentation says countries beyond US/Canada require support confirmation. It is not advanced to detailed pilot testing unless India number and carrier feasibility is confirmed.
- TRAI source review identifies 140-series promotional robo-call and 1600/other allotted series for service/transactional robo-call provisions, plus a 2026 1601 direction for sectors outside BFSI/Government. The classification and process for this recruitment-screening use case remain open and require written carrier/compliance confirmation before any call experiment.
- Source access date recorded as 2026-11-26. Published prices are snapshots and not India all-in quotes. No Indian outbound route price or completed-screen cost is established.
- Research only: no provider account, API, external data transfer, experiment, paid usage, call, integration, staging, commit, or push was performed. No provider winner is selected. Controlled testing still requires a separate approval proposal; the 24 scenarios × 3 runs remain exploratory only.

## Phase 2 voice cloning feasibility research — 2026-11-26
**Status:** Public-source research documented for owner review; no voice clone or experiment created.

- Updated `docs/AI_Provider_Evaluation_Journey.docx` with a source-linked feasibility assessment for Bolna and Retell voice cloning, including Cartesia, ElevenLabs, Soniox and Retell's native/custom-provider paths; sample guidance; API/workflow notes; language claims; costs; consent safeguards; unknowns; and an approval-gated test proposal.
- Public documentation confirms cloning paths on both platforms. Simplest provisional feasibility candidate is Bolna + Cartesia Instant Voice Cloning, subject to confirming integration billing, consent/data terms, and exact Hindi/English output. Retell's native Platform clone is a reasonable within-platform comparison. No provider or clone is selected.
- Hindi/English support is documented for some provider paths, but cloned-voice quality for Hindi, English and especially Hinglish/code-switching has not been measured and remains UNKNOWN. Vendor language/quality statements are not experimental evidence.
- Public price snapshots: Cartesia Pro $5/month includes Instant Voice Cloning and 100K credits; ElevenLabs Starter $6/month includes Instant Voice Cloning and 30K credits; Retell advertises $0.07–$0.31/min depending on configuration; Bolna PAYG starts at $0.06/min (approximately ₹5.52), with telephony/platform fees and BYOK treatment requiring confirmation. These are not complete India call costs. Soniox clone pricing is UNKNOWN.
- Consent: use only the speaker's own voice or obtain explicit, documented, verifiable permission for recording, provider upload, clone creation, language use and recruitment-call purpose. Provider UI consent is not a substitute for written authorization. Confirm deletion, retention, subprocessors, and withdrawal terms; obtain applicable compliance review.
- No account creation, API use, paid usage, sample recording/upload, data sharing, integration, or call occurred. Controlled experiments remain gated on a specific owner-approved sample/data/cost plan.

## Phase 3 Milestone 1 - Call lifecycle foundation - 2026-11-26
**Status:** Implemented. Bolna and Retell remain evaluation candidates; no provider is selected.

### Implemented
- Added provider-neutral `Call` and `CallEvent` models with application UUIDs, candidate foreign keys, normalized status constraints, idempotency keys, provider/event uniqueness, timestamps, and minimal non-secret metadata. Raw provider payloads are not stored.
- Added a narrow provider protocol, a local-only mock provider, normalized call/event types, lifecycle service, validated state transitions, duplicate request/event handling, and safe error classes.
- Added mock-only call create/read routes. `MOCK_CALLS_ENABLED` defaults to false. No route can invoke Bolna/Retell or make an outbound call; no webhook route exists.
- Added Alembic revision `0003_call_lifecycle` with `down_revision = "0002_duplicate_apps"`. Historical migrations are unchanged. The migration adds only `calls` and `call_events`; it was not run against any database.
- Updated README, project plan, decision log, architecture notes, and the evaluation journey status to record Phase 2 public research complete and Phase 3 Milestone 1 underway.

### Validation
- Backend isolated suite: `python -m pytest -q -m "not postgres"` from `backend` - 32 passed, 1 PostgreSQL test deselected, 2 deprecation warnings.
- PostgreSQL integration/migration test not run because the configured target could not be confirmed as the dedicated empty `hr_voice_poc_test` database. No database was connected to or modified.
- Frontend build/tests not run because no frontend files changed.
- No dependency installation, provider/network call, account creation, paid use, external data transfer, outbound call, voice sample/clone, staging, commit, or push occurred.

## Phase 3 Milestone 2 - Bolna adapter (offline only) - 2026-11-26
**Status:** Implemented and covered by mocked HTTP contract tests. The adapter is not wired to an application route; Bolna and Retell remain unselected comparison candidates.

### Implemented
- Added `BolnaAdapter` behind `CallProvider`, using the owner-supplied contract: `POST https://api.bolna.ai/call`, Bearer auth, only `agent_id` and `recipient_phone_number`, and top-level `execution_id` mapped to the internal provider call ID.
- Added exact mappings for documented status examples. `call-disconnected` maps to `disconnected`; unknown values are rejected.
- Added `BolnaSettings` validation for the API key, agent ID, disabled-by-default flag, and bounded timeout. The API key uses `SecretStr`. Bolna settings are loaded only when the adapter is explicitly constructed; the application route remains MockProvider-only.
- Added conservative error handling: documented 400/401/403/422 responses are treated as rejection; timeouts, transport uncertainty, server/redirect/undocumented responses, malformed 2xx bodies, and missing/malformed `execution_id` require reconciliation. No retry or Bolna idempotency behavior is assumed.
- Added `reconciliation_required` and `disconnected` normalized statuses, blocked new idempotency keys for the same unresolved candidate/provider, and an internal explicit reconciliation operation that never calls the provider.
- Added Alembic revision `0004_call_outcomes` after `0003_call_lifecycle` to expand the status check constraints and status columns from 16 to 32 characters. Downgrade refuses while new statuses exist. The migration was not applied.
- Added architecture/configuration documentation and recorded the owner-supplied API evidence plus unresolved details in the evaluation journey.
- Promoted existing `httpx` requirement from test-only to runtime; no new package was added or installed.

### Validation
- Backend suite: `python -m pytest -q` from `backend`, with `TEST_DATABASE_URL` removed for safety - 62 passed, 1 PostgreSQL integration test skipped, 3 deprecation warnings.
- Mocked contract coverage includes exact request/body/auth, identifier parsing, malformed responses, auth/validation/server/unknown HTTP status handling, timeout, status mapping, unknown status, configuration redaction, disabled adapter, ambiguous-outcome guard, explicit reconciliation, and no resubmission.
- Alembic graph tests confirm `0004_call_outcomes` follows `0003_call_lifecycle`; no migration or database connection was made.
- Frontend tests/build not run because no frontend files changed.
- No credentials were requested, displayed, or sent; no provider account, network request, outbound call, webhook, voice sample/clone, paid usage, or dependency installation occurred. Nothing was staged or committed.

### Remaining unknowns
- The supplied evidence names `execution_id` but does not establish its JSON nesting or type. The adapter expects a top-level non-empty string.
- Exact execution retrieval endpoint/response, status-field location, webhook contract, and provider idempotency support remain unverified and are not implemented.
- The meaning of `call-disconnected` is not defined by the supplied evidence; it remains distinct from completed/failed.

## Phase 3 Milestone 3 - Retell adapter (offline only) - 2026-11-26
**Status:** Implemented with mocked contract tests only. Retell remains disabled and is not connected to an application route.

### Implemented
- Added `RetellAdapter` behind the existing provider interface for the verified `POST /v2/create-phone-call` endpoint. The request includes E.164 `from_number` and `to_number`, optional `override_agent_id`, and Bearer authentication. No job data or local idempotency key is sent.
- Maps `call_id` to the internal provider call reference and validates the documented response fields `call_status`, `agent_id`, and `call_type`.
- Added mappings: `registered` → `queued`; `not_connected` → `no_answer`; `ongoing` → `in_progress`; `ended` → `completed`; `error` → `failed`. Unknown status does not map to success; it makes call creation ambiguous.
- Added `RetellSettings`, using `SecretStr`, E.164 caller-number validation, timeout validation, and `RETELL_CALLS_ENABLED=false` by default. The API continues to use only MockProvider.
- Timeouts, transport failures, 429, server/other undocumented HTTP responses, malformed success responses, and unknown call statuses require reconciliation. No retry is attempted. Existing lifecycle protection prevents a new idempotency key from resubmitting an unresolved candidate/provider call.
- Documented that Retell GET retrieval is not implemented because the verified contract does not specify sufficient response fields or reconciliation semantics. No database migration was needed.

### Validation
- Full backend suite: 96 passed, 1 PostgreSQL integration test skipped, 3 existing deprecation warnings. Static compilation and `git diff --check` passed.
- Mock contract tests cover request/auth formation, optional agent override, IDs and statuses, validation/auth/rate-limit/server failures, malformed responses, timeout/transport ambiguity, configuration redaction, and disabled-by-default behavior. Lifecycle coverage confirms a Retell timeout blocks resubmission under a new key.
- PostgreSQL test remained skipped because the dedicated test database was not configured; no database connection or migration was attempted. All provider contract tests use `httpx.MockTransport` and synthetic values.
- No migration, provider request, account, call, voice sample/clone, dependency installation, staging, commit, or push occurred.

## Phase 3 Milestone 4 - Recruitment screening workflow foundation - 2026-11-26
**Status:** Implemented as provider-neutral backend persistence and APIs. Live calling, transcript processing, LLM extraction, and frontend work remain out of scope.

### Implemented
- Added reusable question schema and an initial BRD/POC-scope question set. Sessions snapshot the configuration, allowing role-specific changes without embedding questions in provider adapters.
- Added candidate-linked screening sessions and optional call links with a same-candidate ownership check. Added guarded session states: created, in_progress, completed, declined, disconnected, and incomplete. Completion is blocked until every required question has a recorded non-missing answer.
- Added answer persistence with original response, optional normalized value, explicit/inferred provenance, confidence, and missing/unanswered marker. Validation rejects unsupported provenance and missing-answer values.
- Added structured evaluation persistence and validation for candidate/job details, experience, skills, compensation, notice period, location/work arrangement, interest, availability, missing information, summary, advisory recommendation, reason, and suggested next action. Populated candidate facts require provenance; candidate name and job title are sourced from the candidate record.
- Added session create/read/status APIs, answer upsert/list APIs, and evaluation save/read APIs. No automatic extraction or hiring decision is performed.
- Added Alembic revision `0005_screening_workflow` after `0004_call_outcomes`, creating session, answer, and evaluation tables. Migration file only; not applied.

### Validation
- Full backend suite: 112 passed, 1 PostgreSQL integration test skipped, 4 deprecation warnings. Python compilation and `git diff --check` passed. PostgreSQL integration remained skipped because the dedicated test database was not configured.
- No provider requests, outbound calls, webhooks, LLM usage, recordings, real candidate data, dependency installation, database migration, or Git staging/commit/push occurred.

## Phase 3 Milestone 5 - Screening conversation orchestrator - 2026-11-26
**Status:** Implemented as a deterministic text-only simulation. No provider, LLM, audio, or external service is used.

### Implemented
- Added a pure orchestration state machine in `app/conversations/orchestrator.py`, separate from FastAPI routes, persistence models, call lifecycle, and provider adapters. `ConversationService` handles the SQL persistence boundary.
- Added a persisted one-to-one conversation for each screening session and ordered text-only turn history with UUIDs, turn number, speaker, message, optional question key, type, and timestamp.
- Added start/resume, state/history retrieval, response submission, repeat, clarification request, simulated interruption, and end APIs. Start is idempotent for an active conversation; resuming an interrupted one repeats the active question.
- Prompts use the session's configured questions and include spoken wording, follow-up guidance, required status, position, and total count. Initial wording identifies the AI recruitment assistant and role.
- Simulated response submissions require an explicit disposition and matching active question key. No semantic classification or extraction occurs. Accepted text is saved as an explicit answer; unclear/empty raw text remains in turn history.
- Required questions are asked in configured order before optional questions. Clarification attempts default to 2 and are configurable from 1 to 5. At the limit, the answer is marked missing and the flow advances; a required missing answer produces an incomplete session. Skip/refusal continues; candidate stop produces declined; interruption is resumable; explicit end is incomplete.
- Added Alembic revision `0006_screening_conversations` after `0005_screening_workflow` for conversation and turn tables. Migration file only; not applied.
- Updated README, architecture, decisions, plan, and work log. No frontend changes.

### Validation
- Full backend suite: 123 passed, 1 PostgreSQL integration test skipped, 5 deprecation warnings. Python compilation and `git diff --check` passed. The PostgreSQL test was skipped because the dedicated test database was not configured.
- Conversation tests use only the existing isolated SQLite test database and synthetic candidate data. No migration was applied.
- No provider requests, outbound calls, webhooks, LLM usage, audio/recordings, dependency installation, staging, commit, push, reset, or branch switching occurred.

## Phase 3 Milestone 6 - AI intelligence layer (offline) - 2026-11-26
**Status:** Implemented with deterministic fixture interpretation only. Actual LLM integration remains a future milestone.

### Implemented
- Added a provider-neutral `ResponseInterpreter` protocol, validated `ResponseInterpretation` schema, bounded provider-independent context builder, explicit deterministic mock scenarios, and a workflow composition service under `backend/app/intelligence/`.
- Reused the conversation engine's `ResponseDisposition` values. The intelligence workflow verifies active question identity and original response, then passes an interpretation to the existing conversation service. The deterministic orchestrator remains responsible for all state changes, question order, clarification limits, and termination.
- Extended the existing response API to accept either its backward-compatible manual disposition or an explicit `intelligence_scenario`. The mock does not inspect arbitrary language; a fixed experience example only demonstrates output shape.
- Added a safe fallback for mock/provider/context/schema errors. It preserves candidate text in conversation history, requests clarification, and stores no extracted values. Existing answer persistence now receives validated normalized value, explicit/inferred provenance, and confidence when supplied.
- Added non-secret intelligence settings to repository-root `.env.example`. Mock is the only supported default; there is no LLM adapter or key. No schema change was required because screening answer fields already support extraction metadata; no migration was created or applied.
- Updated README, architecture, decisions, and project plan. No frontend work.

### Validation
- Full backend suite: 141 passed, 1 PostgreSQL integration test skipped, 5 dependency deprecation warnings. The PostgreSQL test was not run because `TEST_DATABASE_URL` was deliberately unset; no development or test database was contacted.
- Python compilation completed successfully. `git diff --check` completed without whitespace errors; Git emitted only existing LF-to-CRLF working-copy warnings.
- Tests use only explicit synthetic fixtures and the existing isolated SQLite test fixture. PostgreSQL integration remains skipped unless its dedicated test database is explicitly configured.
- No external API/provider request, credential, outbound call, audio/transcription/speech, voice clone, dependency installation, migration, or Git state-changing operation was performed.

## Phase 3 Milestone 7 - Native voice AI evaluation and POC configuration - 2026-11-27
**Status:** Public-source evaluation and disabled configuration preparation documented; provider choice and controlled evaluation remain open.

### Implemented
- Compared Bolna and Retell official public sources for managed agent construction, bundled/configurable LLM/STT/TTS, conversation flow, extraction, transcript/results, webhooks, Hindi/English/Hinglish, interruptions, APIs, India telephony, and pricing. The evidence date is 2026-11-27; vendor claims, documented capabilities, measured behavior, and unknowns are explicitly distinguished in `docs/MILESTONE_7_NATIVE_VOICE_AI_EVALUATION.md`.
- Confirmed public evidence is insufficient to pass the mandatory India outbound gate for either platform. Bolna has stronger India-specific carrier/SIP listings, but the project's number route, permitted recruitment-call classification, carrier setup, and actual mobile termination remain unverified. Retell's generic SIP support does not establish an India mobile route.
- Recorded a platform-first decision: test native/bundled capabilities first; defer separate LLM integration unless evidence demonstrates a critical P0 gap and separate owner approval is given. No provider is selected.
- Added `docs/native_recruitment_agent.example.json`, a disabled, provider-neutral template that references existing screening question snapshots and dynamic context placeholders. It is not loaded by application code and contains no IDs, credentials, numbers, or candidate data.
- Identified that existing call requests carry job title/description, but both offline adapters ignore those values and do not pass screening questions. Exact verified dynamic context mappings are needed before later integration; no undocumented payload field was added.
- Proposed measurable thresholds and a controlled exploratory plan (24 scenarios × 3 runs per provider), with sample expansion based on variance/intervals and decision sensitivity. No experiment or calls were conducted.
- Updated README, architecture, decisions, and project plan. The BRD was not modified; Hindi/Hinglish remain P1 there and are documented as POC-specific validation scenarios.

### Validation and restrictions
- Full backend suite: 141 passed, 1 PostgreSQL integration test skipped, 5 dependency deprecation warnings. `TEST_DATABASE_URL` was deliberately unset; no database was contacted.
- Python compilation completed successfully. The native agent JSON template was parsed successfully. `git diff --check` passed without whitespace errors; Git emitted LF-to-CRLF working-copy warnings only.
- No provider account, credential, API request, agent deployment, paid use, candidate-data transfer, call, webhook/tunnel, LLM integration, voice sample/clone, dependency installation, database migration, staging, commit, or push occurred.

## Phase 3 Milestone 8 - Native voice AI integration foundation - 2026-11-27
**Status:** Implemented as a provider-neutral, offline configuration preparation path. Provider selection remains undecided and call execution remains disabled.

### Implemented
- Added validated schemas for candidate/application context, existing job context, ordered screening question snapshots, saved answers with explicit/inferred/missing provenance, configurable agent instructions, language behavior, and requested extraction fields.
- Added a deterministic builder that loads existing candidate, screening session, and answer records; validates their relationship; preserves configured question ordering and metadata; and omits phone unless explicitly requested. It does not invent job requirements or screening answers.
- Added `RecruitmentAgentPreparationService` and a separate optional configuration-consumer protocol. The local mock validates and retains a deep copy in memory for inspection; it is not an AI agent and cannot start a call. The existing `CallProvider` and routes are unchanged.
- No API endpoint, database migration, dependency, provider translation, frontend change, or persisted configuration was needed. Bolna/Retell native agent formats remain unverified by this implementation. Language behavior is a prompt instruction only; quality has not been tested.

### Validation
- Full backend test suite: 150 passed, 1 PostgreSQL integration test skipped, 5 deprecation warnings. The dedicated PostgreSQL test database was not configured; the suite used the existing isolated SQLite setup.
- Python compilation passed. `git diff --check` passed; Git reported existing LF-to-CRLF working-copy warnings only.
- All configuration tests use synthetic data and an isolated SQLite database. No live candidate data is needed.
- No provider request, outbound call, account, credential, paid usage, voice/audio operation, database migration, dependency installation, or Git state-changing operation occurred.

## Phase 3 Milestone 9A - Bolna provider selection and integration readiness - 2026-11-27
**Status:** Public-source readiness report completed. Bolna is the preferred M9B target and Retell the backup, but final provider selection remains provisional.

### Findings and documentation
- Reviewed current official Bolna API, execution, webhook, extraction, retry, telephony, and Exotel integration documentation, plus Exotel requirements and current TRAI material. Source URLs, access date, evidence type, confidence, and unknowns are recorded in `docs/MILESTONE_9A_BOLNA_READINESS.md`.
- Verified that the existing adapter matches the documented minimum `/call` request, Bearer authentication, and `execution_id` mapping. Identified missing M8 context mapping, caller-number/version configuration, execution retrieval, transcript/extraction handling, and webhooks.
- Identified a lifecycle mismatch: Bolna treats `call-disconnected` as interim and emits final `completed` later, while the current normalized `disconnected` state is terminal. M9B must resolve this before consuming final data.
- India outbound readiness is UNKNOWN. Bolna/Exotel document plausible technical routes, but project account/number/KYC, A2P sender declaration, applicable caller-number series, and classification of recruitment screening calls remain unverified. No source reviewed definitively classifies this use case.
- M9A recommends GO for offline/disabled M9B code and mocked tests only; NO-GO for provider activation or calls until listed legal, carrier, privacy, cost, security and approval gates are closed.
- Updated project plan and decision log. No implementation code changed.

### Validation and restrictions
- Documentation consistency and existing adapter boundaries were inspected. No tests were run because no code changed.
- No account, credential, API request, provider contact, call, paid usage, candidate-data transfer, webhook/tunnel, migration, dependency installation, Git staging, commit, push, branch change, or destructive operation occurred.
## Phase 3 Milestone 9B - Bolna recruitment integration - 2026-11-27
**Status:** Implemented behind disabled-by-default controls. No live provider activity occurred.

### Implemented
- Connected the existing M8 configuration builder to a screening-session-scoped Bolna call route through `CallLifecycleService`. The adapter sends only documented call fields and `user_data`; call request replay returns the existing local record, and no provider retry configuration is sent. A partial unique index limits each candidate application to one Bolna call, including attempts through a new screening session.
- Added deterministic context serialization for candidate name, existing candidate context/answers, job title/description, ordered screening questions, and agent instructions. Candidate phone and email are excluded from context; the normalized phone is used only as the required call destination. Provider-side agent placeholders/configuration are not created by the application.
- Added documented execution retrieval and an explicit sync route. Provider execution IDs are stored in `Call.provider_call_id`; completed transcript, summary, duration, and raw extraction are retained on the linked screening session. Extracted data is not mapped into answers or evaluation because the output/provenance contract is not sufficiently specific.
- Added normalized Bolna statuses. `call-disconnected` now maps to nonterminal `finalizing`; completed execution sync can record the interim state when an event was missed, and later events cannot regress a completed call. Unknown statuses and uncertain call-creation responses are not treated as success.
- Added an offline webhook-processing service with shared-secret validation and local deduplication. No webhook HTTP route is exposed; signature and delivery semantics remain unverified.
- Added Alembic revision `0007_bolna_finalization` after `0006_screening_conversations`. It preflights duplicate Bolna calls and reports affected candidate IDs, adds the `finalizing` status to database constraints, creates a partial unique Bolna-call index, and adds nullable transcript, summary, raw extraction, and duration fields. Downgrade refuses to drop populated provider results or finalizing statuses. Migration was not applied.
- Added mocked API, mapping, status, retrieval, ambiguity, idempotency, and webhook tests. Updated README, architecture, decisions, plan, and this work log. Added the optional `BOLNA_WEBHOOK_SECRET` placeholder to `.env.example`; no secret value is present.

### Validation
- Full backend suite: **170 passed, 1 PostgreSQL integration test skipped, 6 warnings** (existing Starlette/httpx and Alembic configuration deprecations). PostgreSQL integration was skipped because its dedicated test database was not configured; no PostgreSQL database was contacted.
- Python compilation passed. Alembic head inspection reports `0007_bolna_finalization`; this reads migration metadata only. `git diff --check` passed with existing LF-to-CRLF working-copy warnings.
- Tests use synthetic values and `httpx.MockTransport`/isolated SQLite only. No Alembic upgrade or downgrade was run.
- No API request, account, credential, paid use, candidate transfer, outbound call, webhook exposure, voice sample/clone, dependency installation, staging, commit, push, branch switch, reset, or destructive Git action occurred.

### Remaining gates
- Configure and validate a Bolna agent with the emitted `user_data` placeholders before any separately approved trial.
- Resolve India carrier route, number/KYC, A2P/recruitment-call classification, consent, retention, cost, and security requirements.
- Confirm webhook authentication/delivery details before adding an HTTP ingress route.
- Review/apply migration `0007_bolna_finalization` only through the normal owner-approved database migration process.
