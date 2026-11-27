# Project Plan and Status

## Delivery constraint
Two-day MVP. Build incrementally; obtain owner approval before each phase and before significant changes.

## Phase 0 — Foundation (documentation scaffold)
**Status: Completed; documentation accepted by the owner.** The scaffold is tracked in the local repository, and the initial setup commit has been pushed to `origin/main`.
- README, AGENTS, scope, plan, architecture, decisions, work log
- Ignore rules and environment-variable template
- No application code

Acceptance: owner reviewed and accepted the documentation.

## Phase 1 — Candidate input and backend foundation
**Status: Complete; accepted by the owner.**
- FastAPI skeleton
- PostgreSQL connection and initial schema
- Candidate create/list endpoints
- Prevent duplicate applications for the same normalized phone number and job title
- Add optional PostgreSQL integration testing against a dedicated empty test database only
- Require `DATABASE_URL` from environment or repository-root `.env`; keep local services loopback-only
- React/Vite/Material UI candidate form and list
- Basic validation and tests

Acceptance: candidate can be entered and retrieved from database/UI. Owner acceptance was confirmed on 2026-11-26 based on completed implementation, testing, validation, and review.

## Phase 2 - AI voice provider and technology evaluation
**Status: Public-source research complete; Bolna and Retell approved for Phase 3 controlled evaluation; final provider selection remains undecided.**

### Completed scope
- Platform-first public-source evaluation with India outbound telephony as a mandatory separate gate.
- Documented vendor/component comparison, current pricing snapshots, evidence ledger, benchmark methodology, thresholds for owner review, and voice-cloning feasibility research.
- No provider account, API, paid use, third-party data transfer, integration, voice sample, clone, or call was used during research.

Acceptance: public-source evaluation and shortlist reviewed. Controlled comparative testing and any provisional provider recommendation belong to Phase 3. No provider is selected.

## Phase 3 - Controlled implementation and testing
**Status: In progress; Milestones 1-8 are implemented, Milestone 9A readiness research is complete, and Milestone 9B Bolna integration is implemented with provider activation disabled by default. No real provider request or call has been made.**

### Milestone 1 - Call lifecycle foundation (implemented)
- Provider-neutral call/event records with application UUIDs and candidate foreign keys.
- Normalized call statuses, validated transitions, request idempotency, and event deduplication.
- Local mock provider only; `MOCK_CALLS_ENABLED=false` by default. No live adapter, outbound dial, or webhook endpoint.

### Milestone 2 - Bolna adapter (offline implementation complete)
- Implemented the documented call create request/response mapping behind the provider interface, with mock HTTP contract tests only.
- `BOLNA_CALLS_ENABLED=false` by default. The adapter was initially offline-only; Milestone 9B later connected it to explicitly gated Bolna routes. No provider credentials or live network request were used during implementation.
- Timeouts, uncertain statuses, malformed success responses, and undocumented response codes require reconciliation; no automatic retry or provider idempotency support is assumed.
- New revision `0004_call_outcomes` expands call status constraints and status-column width for `disconnected` and `reconciliation_required`. It has not been applied to a database.

### Milestone 3 - Retell adapter (offline implementation complete)
- Implemented the verified Retell create-call contract behind the same provider interface, with mocked HTTP contract tests only.
- Validates E.164 caller/recipient numbers and maps documented call IDs and statuses. `RETELL_CALLS_ENABLED=false`; generic call creation remains MockProvider-only, and no Retell route is registered.
- Timeouts, transport failures, rate limiting, server/unknown outcomes, malformed responses, and unknown statuses require reconciliation; no retry is attempted.
- No migration was required. Retell retrieval was not implemented because the verified response schema and reconciliation semantics are incomplete.

### Milestone 4 - Recruitment screening workflow foundation (implemented)
- Added configurable, reusable screening question schemas and an initial question set from the POC screening topics. Each session stores its own question snapshot.
- Added candidate-linked screening sessions with optional same-candidate call association and guarded created/in-progress/completed/declined/disconnected/incomplete transitions.
- Added structured answer persistence with original response, optional normalized value, explicit/inferred provenance, confidence, and missing-answer handling.
- Added validated structured advisory evaluation persistence; populated candidate facts require provenance and candidate name/job title are sourced from the candidate record.
- Added create/read session, status update, answer upsert/list, and evaluation save/read API endpoints. No LLM, automatic extraction, provider calls, transcript processing, or frontend changes.
- Added revision `0005_screening_workflow` after `0004_call_outcomes`; migration file created but not applied.

### Milestone 5 - Screening conversation orchestrator (simulated; implemented)
- Added a deterministic provider-independent text state machine and persistence adapter; no LLM, speech, telephony, provider API, or external service is used.
- Supports start/resume, configured question progression, explicit response dispositions, repeat/clarify, bounded clarification attempts, decline, interruption, completion, incomplete termination, and ordered text turn history.
- Validates conversation/screening status consistency and requires response `question_key` to match the active question. Raw unclear response text remains in turn history; no semantic extraction occurs.
- Added conversation and turn models plus revision `0006_screening_conversations` after `0005_screening_workflow`. Migration file created only, not applied.
- Added simulated conversation API endpoints. No frontend changes.

### Milestone 6 - AI intelligence layer (LLM-ready, offline; implemented)
- Added provider-neutral `ResponseInterpreter`, bounded context builder, validated structured interpretation schema, and deterministic mock fixtures. The mock does not infer meaning from arbitrary candidate text.
- Integrated explicit mock scenarios into the existing conversation response endpoint while preserving the manual disposition request format. The active question key and original response are checked before orchestration.
- The workflow attaches validated normalized value, explicit/inferred provenance, and confidence to existing screening answer persistence. The conversation service/orchestrator alone control state, ordering, clarification limits, and termination.
- Provider/context/schema failures use a safe unclear fallback, preserve the raw response in text history, and save no extracted answer. Existing deterministic clarification policy remains authoritative.
- Added non-secret mock configuration for provider identifier, model label, timeout, response size, context turns, and context size. No external model adapter, API key, dependency, database migration, or frontend change was added.

### Milestone 7 - Native voice AI evaluation and POC configuration (public-source preparation)
- Prioritize each managed provider's built-in/recommended conversation stack; do not add an independent LLM by default. Only revisit a separate LLM after controlled evidence shows a critical P0 gap and separate owner approval.
- Compared Bolna and Retell public documentation for native agent setup, bundled/selectable AI components, configurable question flow, structured extraction, transcripts, webhooks, languages, interruptions, APIs, India telephony, and pricing. Claims and unknowns are classified in `docs/MILESTONE_7_NATIVE_VOICE_AI_EVALUATION.md` with sources/access date.
- Added a disabled, provider-neutral example agent configuration at `docs/native_recruitment_agent.example.json`. It references per-session screening questions and context placeholders; application code does not load it.
- Bolna public pages document Indian carrier/SIP routes, but actual route/number/compliance/rate for recruitment calls remains unverified. Retell's generic SIP support does not verify India mobile reachability. Neither passes the mandatory India route gate; no provider is selected.
- Hindi/Hinglish are POC-specific validation conditions, while their original BRD P1 priority remains unchanged. All quality, latency, Hindi/Hinglish performance, extraction, and webhook claims remain unmeasured.
- Controlled testing, accounts, paid usage, candidate-data transfer, calls, and public webhook exposure have not started and require separate explicit approval. Proposed thresholds and the 24×3 exploratory test plan are recorded for review.

### Milestone 8 - Native voice AI integration foundation (provider-neutral, offline)
- Added validated recruitment agent configuration schemas and a deterministic builder from existing candidate, job, screening question snapshot, and saved answer records. Question order/required status/follow-up guidance and answer provenance are preserved; candidate phone is omitted by default.
- Added an optional configuration-consumer protocol and local in-memory mock consumer. The mock validates and retains an isolated configuration copy; it is not an AI agent and does not initiate calls. The preparation service connects the builder to this mock-only path.
- No provider-specific payload, application API endpoint, call lifecycle change, database migration, or dependency was needed. Bolna/Retell translation remains unimplemented pending verified native configuration contracts. Provider selection remains undecided.
- Tests use synthetic records and isolated SQLite only. Hindi, English, and Hinglish are represented as configurable instruction behavior and have not been evaluated for quality.

### Milestone 9A - Bolna provider selection and integration readiness (research complete)
- Bolna is the preferred M9B provider and Retell remains backup; this is not a final selection. Provider selection remains subject to controlled comparative testing.
- Current official Bolna docs verify `/call`, Bearer auth, minimum request fields, `execution_id`, `user_data`, execution retrieval, statuses, transcript/extraction response, webhook setup, and provider retry configuration. Existing adapter gaps and current docs changes are recorded in `docs/MILESTONE_9A_BOLNA_READINESS.md`.
- India outbound readiness is UNKNOWN: a technical provider route is documented, but the project's route/number/KYC, A2P/DLT declaration, and recruitment-call classification are not confirmed. No account, API, call, payment, or candidate-data transfer was used.
- M9A recommends GO only for disabled offline M9B implementation and mocked tests; NO-GO for activation or calls until regulatory/carrier, route, consent, cost, and security gates are approved.

### Milestone 9B - Bolna recruitment integration (implemented; live use remains disabled)
- Connect the M8 builder to the Bolna adapter using only the documented `/call` fields and `user_data`; candidate phone/email are excluded from context, and phone is sent only as the required recipient.
- Add session-scoped idempotency, a database uniqueness guard limiting each candidate application to one Bolna call, and persist the provider `execution_id` on the application call record linked to the screening session. The migration preflights existing Bolna call duplicates and stops with candidate IDs if found.
- Add explicit execution retrieval/status sync and retain completed transcript, summary, duration, and raw extracted data. Raw extraction is not mapped into answer/evaluation fields without verified structure and provenance.
- Map `call-disconnected` to nonterminal `finalizing`; preserve no-retry and ambiguous-outcome reconciliation behavior. Unknown status and uncertain create outcomes cannot trigger another call.
- Add an offline webhook processor and shared-secret validation helper only. No webhook HTTP route is exposed; signature/delivery semantics remain unverified.
- Alembic revision `0007_bolna_finalization` adds the status constraint and screening result columns. Migration file only; not applied.
- `BOLNA_CALLS_ENABLED` defaults to false. No account, credentials, API request, paid usage, external candidate transfer, or outbound call was used. India and compliance gates remain unresolved.

### Remaining milestones / follow-up work
- Local testing UI for configured provider, agent, status, conversation, transcript, and result review.
- Transcript retrieval/processing, AI purpose/consent dialogue execution, actual LLM integration, semantic extraction, and result generation.
- Optional voice-cloning feasibility trial after separate approval and explicit speaker authorization.
- Controlled Bolna/Retell comparison with matched scenarios, frozen thresholds, and exploratory samples expanded if uncertainty could change the decision.

Milestone 9B implements documented Bolna execution retrieval and maps `call-disconnected` to nonterminal `finalizing`. Webhook processing is a service foundation only; no route is exposed because authentication and delivery details remain unverified. Bolna extracted data is retained raw until output and provenance mapping are validated.

Retell's create-call request/response and status names are implemented from the verified contract. Its GET retrieval endpoint is documented, but response details needed for reconciliation remain unverified and retrieval is not implemented.

Live accounts/credentials, paid use, third-party data transfer, public callback access, voice samples/cloning, and outbound calls require the relevant explicit approval. Use fictional test data and an authorized test recipient only after the call test is approved. No automatic call retries.

Acceptance: compare both shortlisted providers under the approved test plan and record evidence, limitations, and uncertainty. Final provider selection remains an owner decision.

## Phase 4 — Transcript and evaluation
**Status: Not started.**
- Retrieve and persist transcript
- Extract structured candidate fields
- Mark missing information
- Distinguish candidate-stated facts from inference
- Generate concise summary and advisory recommendation

Acceptance: completed test call produces validated JSON and summary.

## Phase 5 — Results dashboard
**Status: Not started.**
- Candidate list/status
- Candidate details
- Call status/duration
- Extracted profile and summary
- Transcript display

Acceptance: user can inspect the results of a screening call in the UI.

## Phase 6 — End-to-end POC validation and closeout
**Status: Not started.**
- POC scenario testing and results
- Extraction accuracy review against manually labelled test conversations
- End-to-end acceptance, outstanding issues, and closeout after implementation phases

Acceptance: end-to-end POC scenarios and extraction are reviewed against agreed criteria; limitations and remaining issues are recorded. Provider and pricing evaluation deliverables belong to Phase 2.

## Status convention
- Not started
- In progress
- Blocked
- Prepared for review
- Complete

## Current blockers / open decisions
- Confirm compliant, priced India outbound routes for both shortlisted providers before call tests.
- Approve test data, authorized recipient, provider use, callback exposure strategy, and voice-cloning sample separately before those actions.
- Confirm deployment target and its database/service options before deployment work.
- Keep the final provider choice open until controlled Phase 3 results support a recommendation.
