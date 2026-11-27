# Architecture and Product Decisions

## Decision log

### D-001: Keep the POC HR-only
**Status:** Accepted from owner scope.
Implement recruitment screening only. Other use cases are future vision, not this MVP.

### D-002: Frontend stack
**Proposed:** React + Vite + Material UI.
Reason: quick local development and a straightforward dashboard.

### D-003: Backend
**Proposed:** FastAPI.
Reason: Python ecosystem for webhook handling, orchestration, and structured extraction.

### D-004: Database
**Proposed:** PostgreSQL.
Reason: deployment-friendly relational storage and JSONB for structured extraction/provider payloads. Owner approval required before changing.

### D-005: Voice provider
**Status:** Final selection undecided; Bolna and Retell are approved candidates for controlled evaluation.
Phase 2 public-source research is complete. Phase 3 will compare Bolna and Retell with the same recruitment workflow where feasible. India outbound telephony is a mandatory separate gate. No provider is selected based on documentation or score alone. Phase 3 Milestone 1 uses only a local mock; live accounts, paid use, external data transfer, callbacks, voice samples/cloning, and outbound calls remain approval-gated.

### D-006: Provider abstraction
**Accepted requirement:** keep vendor integration replaceable, but implement only what the POC needs. Do not over-engineer a multi-provider framework.

### D-007: Coding-agent independence
Repository instructions and project state must be maintained in Markdown files so Codex, Cursor, Claude, or other agents can continue without relying on chat history.

### D-008: Phase 1 application identity
**Status:** Accepted for the POC.
An application is unique by E.164-normalized phone number plus a whitespace-collapsed, case-folded job title. There is no jobs table in Phase 1, so distinct openings with the same normalized title are treated as the same role. Do not add job IDs without an approved scope change.

### D-009: Normalization migration policy
**Status:** Accepted.
Phone and job-title normalization changes that affect persisted normalized keys require a new Alembic migration that backfills and checks for collisions. Do not modify an already-applied historical migration.

### D-010: Local-only POC access
**Status:** Accepted.
Authentication is out of scope for this POC. Keep the frontend, API, and database bound to the local machine; do not expose candidate data or services publicly.

### D-011: Phase 3 Milestone 1 call lifecycle
**Status:** Accepted for the current milestone.
Persist calls and normalized event history behind a provider interface, with application UUIDs, database idempotency, and validated state transitions. The only implemented provider is a local mock. Mock execution is disabled by default; no live provider integration, webhook endpoint, or outbound call is part of Milestone 1. Provider selection remains open between Bolna and Retell.

### D-012: Phase 3 Milestone 2 Bolna adapter boundary
**Status:** Offline adapter implemented; not wired into the application API.
The adapter sends only documented `agent_id` and `recipient_phone_number` fields to the documented call-create endpoint and maps `execution_id` to the internal provider call reference. It does not send a local idempotency key. Unknown statuses are rejected; `call-disconnected` remains distinct from completed. Ambiguous outcomes require explicit reconciliation and block a new request for the same candidate/provider. M9A's review of current official docs now verifies execution retrieval, transcript/extraction fields, dynamic `user_data`, status webhooks, and retry configuration; it does not verify a Bolna idempotency guarantee, webhook signature/retry semantics, or the project's India route. No live request or provider selection is implied.

### D-013: Phase 3 Milestone 3 Retell adapter boundary
Implement Retell's verified call-create contract offline behind the existing provider interface. Send E.164 `from_number` and `to_number`, with optional `override_agent_id`, and map `call_id` to the provider call reference. Keep Retell disabled and unwired from application routes. Unknown statuses, timeouts, transport errors, rate limits, server errors, and malformed success responses require reconciliation; never retry automatically. Existing normalized lifecycle states map documented Retell labels. Retell GET retrieval is deferred until its response contract and reconciliation semantics are verified. No provider selection or live use is implied.

### D-014: Phase 3 Milestone 4 screening persistence
Keep question definitions reusable and provider-independent. Snapshot a validated question list on each screening session; store answers separately with original response, optional normalized value, explicit/inferred provenance, confidence, and missing status. Validate and persist advisory evaluation data without automatic extraction or hiring decisions. Sessions may reference an existing call only when it belongs to the same candidate. No call/provider integration, transcript processing, LLM, or frontend work is part of this milestone.

### D-015: Phase 3 Milestone 5 deterministic simulated conversation
Conversation flow is a provider-independent deterministic state machine, not an AI agent. Simulated response submissions must identify the active question and provide an explicit disposition; the application does not infer meaning from text. Required unclear/empty answers get a bounded number of clarification attempts, then remain missing with raw text preserved in turn history. Skip/refusal continues the flow; a required missing answer results in an incomplete session. A candidate stop maps to declined; interruption is resumable and repeats the active question. Persist text-only ordered turns. No speech, transcript, provider, or LLM integration is included.

### D-016: Phase 3 Milestone 6 offline interpretation boundary
Use a provider-neutral, validated response interpretation contract and keep conversation state ownership in the deterministic orchestrator. The only implementation is an explicitly selected fixture mock that does not interpret arbitrary natural language. Reuse existing response dispositions; verify the interpreter cannot change the active question key or original response. Bound context before any future model integration. Invalid or unavailable interpretation falls back to unclear, preserves raw text in turn history, and does not store fabricated answer values. Actual LLM integration is a separate future milestone and requires its own approval.

### D-017: Phase 3 Milestone 7 native voice stack first
For the 2-day POC, evaluate Bolna and Retell using each provider's native/bundled conversational stack as the first baseline. Do not add a separate LLM API unless a controlled evaluation demonstrates a critical P0 gap and the owner approves its additional dependency, cost, latency, and data transfer. Provider selection remains undecided. Hindi and Hinglish are POC validation scenarios only; original BRD priorities remain unchanged. The native agent JSON is a disabled, non-runtime template. No provider is enabled and India outbound feasibility is a hard gate that neither candidate has yet passed.

### D-018: Phase 3 Milestone 8 provider-neutral agent configuration
**Status:** Accepted for the current coding milestone.
At Milestone 8, prepare a validated provider-neutral recruitment configuration from existing candidate, job, screening question, and answer data. Preserve explicit/inferred/unknown distinctions, omit phone by default, and do not invent absent job requirements. Use a separate optional configuration-consumer contract and an in-memory deterministic mock; do not couple that configuration-consumer flow to `CallProvider`. No API endpoint or migration was needed for M8. **Superseded for Bolna by D-020:** M9B adds a documented adapter mapping and gated call/sync routes. Retell remains offline-only, and provider selection remains undecided.

### D-019: Phase 3 Milestone 9A Bolna preference and readiness gate
**Status:** Preferred implementation direction; not final provider selection.
Bolna is the primary target for M9B and Retell is the backup based on the project owner's direction. The recommendation remains provisional pending controlled comparative evidence. M9B may proceed as disabled, offline implementation with mocked tests. Do not activate Bolna or make calls until the India A2P/caller-number classification, carrier route/KYC, candidate consent/data handling, costs, and required approvals are resolved. Preserve no-retry and reconciliation protections. The documented `call-disconnected` → `completed` progression must be represented safely before final transcript/extraction handling.

### D-020: Phase 3 Milestone 9B Bolna integration boundary
**Status:** Implemented, not activated; provider selection remains provisional.
The Bolna route uses the existing call lifecycle and M8 recruitment configuration. Only documented `/call` fields (`agent_id`, `recipient_phone_number`, and `user_data`) and execution retrieval are implemented. The provider agent itself must be configured separately to consume the dynamic variables; the application does not create or alter it. Candidate phone and email are excluded from context, and no `retry_config` is sent. Session-scoped idempotency, a candidate-application/provider unique index, and the lifecycle's reconciliation lock prevent duplicate Bolna call submissions, including retries with a different local key or screening session.

Bolna `call-disconnected` is represented by nonterminal `finalizing`; completed is persisted only after a later completion event/retrieval. Completed transcript, summary, duration, and raw extracted data are retained on the screening session. Raw extraction is not converted to answers/evaluation until field mapping and explicit/inferred provenance are established. A webhook processor and shared-secret helper exist without a registered HTTP endpoint; Bolna's signature and delivery semantics remain unknown. Revision `0007_bolna_finalization` is created but unapplied. Provider activation is disabled by default. No call, external request, or paid use was performed. India outbound, legal, carrier, consent, data-retention, cost, and owner-approval blockers remain; no final provider decision is made.
