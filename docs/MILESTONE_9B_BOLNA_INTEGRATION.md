# Milestone 9B — Bolna Recruitment Integration

**Status:** Implemented for explicitly enabled integration; disabled by default. No live provider operation was performed.  
**Provider decision:** Bolna is the preferred integration target and Retell is the backup. This remains a provisional direction, not a final provider selection.

## Implementation summary

The application connects the existing recruitment-agent configuration builder to Bolna through the existing call lifecycle. The generic mock provider remains the default for generic call creation. Bolna-specific endpoints are separately gated by `BOLNA_CALLS_ENABLED`, which defaults to `false`.

### API routes

| Route | Purpose | Safety behavior |
|---|---|---|
| `POST /api/screening-sessions/{session_id}/bolna-call` | Build M8 context and create one Bolna execution for an existing screening session. | Disabled with HTTP 503 unless `BOLNA_CALLS_ENABLED=true`. Uses a deterministic session-scoped idempotency key. A database partial unique index permits only one Bolna call per candidate application, even from a new session or concurrent request. Replays return the existing local call and never submit again. |
| `POST /api/calls/{call_id}/bolna-sync` | Explicitly retrieve a Bolna execution and synchronize its current state/results. | Disabled with the same provider flag. Retrieval does not create a call. Repeated syncs are locally idempotent. |

No webhook API route is registered.

## Documented Bolna contract and mapping

The adapter implements the contract documented in the [Bolna Make Call API](https://www.bolna.ai/docs/api-reference/calls/make), [Get Execution API](https://www.bolna.ai/docs/api-reference/executions/get_execution), [webhook guide](https://www.bolna.ai/docs/post-call/polling-call-status-webhooks), and [automatic retry documentation](https://www.bolna.ai/docs/outbound/auto-retry). These references were reviewed 2026-11-27 as part of M9A. These are documentation findings, not account-level verification or performance tests.

| Application value | Bolna field | Notes |
|---|---|---|
| Server-configured Bolna agent | `agent_id` | Existing agent must be configured in Bolna. This application does not create or update it. |
| Candidate's canonical phone | `recipient_phone_number` | Required call destination; not included in `user_data`. |
| Candidate name, job title/description, ordered question snapshot, instructions, and prior answer context | `user_data` | Values are strings for documented dynamic-variable substitution. The Bolna agent must contain corresponding placeholders. Array expansion and automatic agent-prompt configuration are not assumed. |
| Bolna response `execution_id` | `Call.provider_call_id` | Application `Call.id` remains its own UUID. The call is associated with the existing screening session. |
| `GET /executions/{execution_id}` status, transcript, `extracted_data`, duration, summary | Screening session result fields and normalized call status | Only allowlisted fields are retained; recording URLs and unrelated raw payload fields are ignored. |

No undocumented payload field is sent. `retry_config` and provider idempotency headers are omitted. Candidate phone and email are omitted from `user_data`; saved candidate answers and application context are sent to the provider only when the explicitly enabled integration endpoint is invoked. There is no credential in frontend configuration or API output.

**Agent setup limitation:** Dynamic variable support documents per-call substitution, not an API for dynamically changing the provider's full agent prompt. A future approved Bolna agent must be manually configured to consume the emitted `user_data` fields. The exact prompt behavior, Hindi/English/Hinglish performance, question-following, extraction accuracy, and runtime compatibility are unverified until controlled tests.

## Status and uncertain outcomes

Bolna statuses are normalized only when recognized:

| Bolna status | Application status |
|---|---|
| `queued` | `queued` |
| `initiated` | `initiated` |
| `ringing` | `ringing` |
| `in-progress` | `in_progress` |
| `call-disconnected` | `finalizing` (nonterminal) |
| `completed` | `completed` |
| `no-answer` | `no_answer` |
| `busy` | `busy` |
| `failed`, `error`, `balance-low` | `failed` |
| `canceled`, `stopped` | `canceled` |

Unknown status values are rejected and do not become successful states. `call-disconnected` is an interim state; a later `completed` event is accepted. If an explicit GET finds a completed execution before its interim event was received, the synchronizer records the documented nonterminal `finalizing` step first. Existing guards prevent stale events from regressing a terminal completed call. Event IDs are locally derived from execution ID, status, and available timestamp; no Bolna event-ID guarantee is assumed.

Call-creation timeouts, transport loss, 403 (not fully specified in the reviewed docs), 429, 5xx, malformed 2xx responses, and unknown statuses are treated as ambiguous. No automatic retry is performed. A stored reconciliation-required outcome plus session-scoped idempotency prevents an HTTP replay or new request details from causing another call. A human/provider reconciliation process remains necessary.

## Execution results and data handling

The sync path stores transcript, summary, duration, and provider `extracted_data` only when the execution is `completed`. Result columns are nullable and attached to the screening session. Extraction remains raw JSON; it is **not** converted into `ScreeningAnswer` or `ScreeningEvaluation` because the provider's output schema and explicit-versus-inferred provenance have not been established. No answer is fabricated, and no hiring decision is made. Provider recording URLs and unrelated execution payload fields are not persisted.

Alembic revision `0007_bolna_finalization` follows `0006_screening_conversations`. It first checks for existing multiple Bolna calls per candidate; if found, it stops and reports candidate IDs without modifying records. It adds the nonterminal `finalizing` value to call and event check constraints, creates a partial unique Bolna-call index, and adds nullable transcript, summary, raw extraction, and duration fields to screening sessions, including a nonnegative-duration constraint. Downgrade refuses to proceed if any call/event uses `finalizing` or any screening session contains provider results, avoiding silent data loss. **The migration file has not been applied to any database.** Apply it only through the normal reviewed migration process before using these routes against a migrated deployment.

## Webhook security boundary

An offline processing method validates a normalized execution payload and a configured shared-secret header value using constant-time comparison, then delegates event application to the call lifecycle. It is not exposed as a route and cannot initiate calls. Bolna documents configurable custom headers and sender IPs, but the reviewed sources did not verify a provider HMAC/signature, delivery retry guarantees, or unique event IDs. Shared-header validation and IP allowlisting must not be represented as verified signature authentication. No public HTTPS ingress or tunnel is configured.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `BOLNA_CALLS_ENABLED` | Enables the Bolna-specific call and sync routes. | `false` |
| `BOLNA_API_KEY` | Server-side Bearer credential, stored as `SecretStr`. | Empty |
| `BOLNA_AGENT_ID` | Existing provider agent identifier. | Empty |
| `BOLNA_TIMEOUT_SECONDS` | HTTP timeout. | `10` |
| `BOLNA_WEBHOOK_SECRET` | Placeholder for a future configured custom header secret. No endpoint consumes it over HTTP in this milestone. | Empty |

No API key is required to run the mocked test suite. Do not set the enable flag until the owner separately approves account configuration, data transfer, costs, route, and controlled testing.

## Verification performed

- Full backend suite: **170 passed, 1 PostgreSQL integration test skipped, 6 warnings** (existing Starlette/httpx and Alembic configuration deprecations). PostgreSQL integration was not enabled because the dedicated test database was not configured.
- Python compilation passed; Alembic head inspection reports `0007_bolna_finalization`; `git diff --check` passed with line-ending warnings only.
- All HTTP contract tests use `httpx.MockTransport`; the call and sync route tests inject the same local mock transport. No external host is contacted.
- Tests use the repository's isolated SQLite test fixture. PostgreSQL integration was not enabled. Migration metadata was inspected but no Alembic upgrade/downgrade was run.
- No provider account, credential, paid usage, real candidate data, outbound call, cloned voice, dependency installation, Git stage, commit, push, branch change, reset, or destructive operation occurred.

## Limitations and activation prerequisites

- India outbound readiness remains **UNKNOWN**: carrier route, caller number/KYC, A2P and recruitment-call classification, required consent, recipient restrictions, and cost are unresolved. See [M9A readiness research](MILESTONE_9A_BOLNA_READINESS.md).
- Provider-side agent placeholders and native prompt behavior have not been tested. Bolna's dynamic variable format and extraction quality need a controlled account-level validation before relying on them.
- Bolna webhook signature/delivery semantics remain unverified; no ingress route is enabled.
- Raw `extracted_data` has no validated mapping to answers, confidence, or explicit/inferred provenance.
- The migration is outstanding and must be reviewed/applied before a database with this schema can support the new result fields.
- Provider selection remains provisional pending a controlled comparison with Retell, frozen acceptance thresholds, and sufficient measured samples.

## M9C prerequisites

Before a controlled end-to-end POC, obtain separate approval for provider-account setup, credential storage, enabling the provider, permitted candidate/test data transfer, and paid usage. Confirm in writing the India route and recruitment-call compliance with the carrier and qualified counsel; approve the caller ID, consent wording, test participants/numbers, call times and volume, transcript/extraction retention, access control, and cost ceiling. Review and apply migration `0007_bolna_finalization`. Manually configure the Bolna agent placeholders and test that no automatic provider retry is configured. Approve any webhook ingress separately; until its authentication and delivery contract are verified, prefer explicit retrieval/polling. Run the controlled Bolna-versus-Retell benchmark only after these gates are cleared.
