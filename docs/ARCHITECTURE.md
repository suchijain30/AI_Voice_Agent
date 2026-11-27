# Architecture

## POC flow
Candidate input UI → FastAPI → PostgreSQL → provider adapter → voice provider/telephony → candidate conversation → provider webhook/transcript → extraction and summary → PostgreSQL → results UI.

## Components
- React/Vite + Material UI: candidate input and results dashboard
- FastAPI: API, orchestration, webhook receiver
- PostgreSQL: candidate, call, transcript, extraction and summary persistence
- Pydantic: API contracts and structured extraction validation
- Voice provider adapter: encapsulates provider-specific call initiation/status/transcript operations needed for the MVP
- Screening service: provider-independent screening question and evaluation logic

## Phase 3 Milestone 6 AI intelligence boundary (offline)
- `app/intelligence` contains the provider-neutral `ResponseInterpreter` protocol, bounded interpretation context, validated response schema, deterministic fixture mock, and workflow composition. It is separate from provider adapters, persistence, and the pure conversation state machine.
- The context builder selects only the active configured question, bounded job context, current raw response, clarification counters, and a configured bounded number/size of recent text turns. No audio, full transcript, or database objects are passed to an interpreter.
- The response schema reuses `ResponseDisposition`, avoiding a duplicate classification enum. It validates active question identity, original-response preservation, explicit/inferred provenance, missing state, and confidence in `[0,1]`.
- The mock is selected by an explicit scenario key and returns fixed fixture results; it does not claim to understand arbitrary text. A fixed experience example demonstrates the extraction contract only.
- `IntelligenceWorkflowService` validates interpretation and verifies that neither the question key nor original response changed. It passes disposition to `ConversationService`; only that service and its deterministic orchestrator advance state or persist answers.
- Invalid outputs/provider errors use an `unclear` safe fallback: preserve raw text in turn history, store no extracted answer, and let the existing clarification cap/termination policy decide next steps. There are no retries, external calls, credentials, migrations, or frontend changes.

## Phase 3 Milestone 7 native voice AI baseline
- The preferred initial POC architecture is a managed provider's bundled agent/LLM/STT/TTS stack. No standalone LLM is added unless controlled results identify a critical P0 gap and the owner approves the extra integration, data flow, latency, and cost.
- `docs/native_recruitment_agent.example.json` is a non-runtime, disabled configuration template. It references the screening session's question snapshot and dynamic context placeholders; it has no provider ID, credentials, phone numbers, or candidate record. It is not loaded by application code.
- The existing `CallProvider` request includes the job title and job description, but the offline Bolna and Retell adapters currently send only their documented call-create fields and ignore that extra context. Neither adapter currently passes the question snapshot or the extraction contract. Do not invent fields; resolve the exact supported dynamic-context mechanism before a later integration milestone.
- The call route still constructs `MockProvider` only; `MOCK_CALLS_ENABLED`, `BOLNA_CALLS_ENABLED`, and `RETELL_CALLS_ENABLED` are false by default. No live route, webhook receiver, or public callback is added here.
- Bolna's public pages identify India-specific carrier/SIP paths; actual +91 mobile route, number series, compliance, and full rate are still unverified. Retell documents generic custom SIP, not a verified India route. Both therefore remain behind the India mandatory gate.
- Native platform extraction must map to existing screening answers/evaluation with accurate explicit/inferred/unknown provenance. Provider confidence does not establish correctness. Transcript retention and webhook security require separate design/approval.

## Phase 3 Milestone 1 call lifecycle
- `Call` records use application UUIDs and reference an existing candidate. They store provider name/reference, idempotency key, normalized status, timestamps, and minimal non-secret configuration metadata.
- `CallEvent` stores normalized event identity/type/status and timestamps. A provider/event uniqueness constraint prevents duplicate processing; raw event payloads are not retained.
- `CallLifecycleService` owns idempotency, state transitions, and event deduplication. `CallProvider` is a narrow interface; `MockProvider` is the only implementation in this milestone.
- Mock execution is disabled by default using `MOCK_CALLS_ENABLED=false`. Enabling it only creates local mock call records/IDs; it does not enable outbound calling.
- No provider webhook route, transcript/recording storage, or live provider adapter is implemented in Milestone 1.

## Phase 3 Milestone 2 Bolna adapter (offline only)
- `BolnaAdapter` implements the existing `CallProvider` protocol and uses an injected `httpx.Client`; contract tests use `httpx.MockTransport`. The adapter is not wired into the application call route, which continues to use `MockProvider` only.
- The implemented documented request is `POST https://api.bolna.ai/call`, Bearer authorization, and exactly `agent_id` plus `recipient_phone_number` in JSON. The documented response identifier `execution_id` maps to `provider_call_id`. No local idempotency key or job data is sent to Bolna.
- Only documented status examples are normalized. `call-disconnected` maps to a distinct `disconnected` value, not `completed`. Unknown statuses are rejected.
- Bolna timeout, transport, 5xx, redirect, other undocumented HTTP responses, and malformed 2xx responses produce `reconciliation_required`; definitive 400/401/403/422 responses are treated as rejections. No retry occurs.
- Unresolved creation outcomes block a new call key for the same candidate/provider. Explicit reconciliation records a known existing execution or a confirmed non-creation and makes no provider request. It is not exposed through an API or webhook.
- Bolna credentials use a separate `BolnaSettings` object and are loaded only when the adapter is explicitly constructed. The key is a `SecretStr`; credentials are absent from API responses and exception text. `BOLNA_CALLS_ENABLED=false` by default, and enabling the setting alone does not connect the adapter to the API route.
- Exact execution-retrieval endpoint/response schema, webhook contract, provider idempotency support, and the business meaning of `call-disconnected` remain undocumented in the evidence supplied; none is implemented or assumed.

## Phase 3 Milestone 3 Retell adapter (offline only)
- `RetellAdapter` implements the existing `CallProvider` protocol. Mock HTTP contract tests use `httpx.MockTransport`; the adapter is not wired into the application call route, which remains mock-only.
- The verified creation request is `POST https://api.retellai.com/v2/create-phone-call` with Bearer authorization, E.164 `from_number` and `to_number`, and optional `override_agent_id`. The adapter sends no job data or local idempotency key.
- Successful responses must contain string `call_id`, `call_status`, `agent_id`, and `call_type`. `call_id` maps to `provider_call_id`. Known statuses map to normalized lifecycle states; an unknown status makes the creation outcome ambiguous.
- `registered` maps to `queued`; `not_connected` to `no_answer`; `ongoing` to `in_progress`; `ended` to `completed`; and `error` to `failed`. These are call-lifecycle mappings, not screening outcomes.
- Timeouts, transport errors, HTTP 429, server/other undocumented HTTP responses, and malformed 2xx responses require explicit reconciliation. No retry occurs. Existing lifecycle safeguards block another call for the same candidate/provider while unresolved.
- `RETELL_CALLS_ENABLED=false` by default. `RETELL_API_KEY` is a `SecretStr`; `RETELL_FROM_NUMBER` is required when explicitly enabled and must be E.164. Configuration does not register Retell with the application route.
- Although `GET /v2/get-call/{call_id}` and Bearer authentication are documented, retrieval is not implemented: the verified contract does not establish the response fields or sufficient reconciliation semantics.

## Phase 3 Milestone 4 screening workflow foundation
- `ScreeningSession` belongs to a candidate and may reference one existing `Call`, with a candidate ownership check. Session question configuration is stored as a validated JSON snapshot so different role-specific question sets can be used without provider coupling.
- Initial reusable questions are in `app/screenings/questions.py` and are derived from the POC screening topics. They cover consent/willingness, interest, experience, skills, compensation, notice period, location/work arrangement, and interview availability. Call adapters contain no question or screening logic.
- `ScreeningAnswer` stores each response independently with question key, original response, optional normalized value, explicit/inferred provenance, confidence, and missing status. Schema and database constraints prevent values from being attached to an explicitly missing answer.
- `ScreeningEvaluation` stores validated structured data as JSON, with candidate name/job title sourced from the candidate record. Every populated candidate information field carries explicit/inferred provenance. Its recommendation enum is advisory; no hiring decision is made automatically.
- Lifecycle transitions are guarded in `ScreeningService`. Terminal sessions cannot accept answer changes. No automatic call/session synchronization, transcript processing, LLM extraction, or call initiation is implemented.
- A session cannot transition to `completed` until every required question has a recorded non-missing answer; unanswered required questions must instead remain unresolved or finish as `incomplete`.
- Revision `0005_screening_workflow` creates the session, answer, and evaluation tables after `0004_call_outcomes`. It is a migration file only and has not been applied.
- API: create/read session, update status, upsert/list answers, and save/read evaluation under `/api/screening-sessions`. Only local application persistence is used.

## Phase 3 Milestone 5 simulated conversation orchestrator
- `app/conversations/orchestrator.py` is a deterministic state machine with no database, FastAPI, provider, LLM, speech, or external-service dependency. `ConversationService` adapts persisted screening sessions/answers to the engine and commits the resulting state, answer, and text turns.
- One `ScreeningConversation` belongs to a screening session; ordered `ScreeningConversationTurn` rows store agent/candidate/system text, turn type, question key, and timestamp. There is no audio or recording field.
- Conversation states are `ready`, `awaiting_response`, `clarification_needed`, `interrupted`, `completed`, `declined`, and `incomplete`. Active states require the screening session to be `in_progress`; terminal conversation states match the corresponding terminal screening status. Start/resume on an interrupted simulation repeats its current question.
- The caller supplies an explicit response disposition; the engine does not infer intent from text. Responses include the active question key to prevent stale responses from being attached to a later question. Accepted text is stored as explicit original response; no normalized value is generated.
- Required questions are selected in configured order before optional questions. Optional questions are then selected in configured order. Skip/refusal marks an answer missing and continues. Required unclear/no-response attempts are bounded by a configurable maximum (default 2, range 1-5); at the limit the raw turn history remains and the answer is missing. If any required answer is missing, the finished session is `incomplete`.
- Candidate stop ends the session as declined. Simulated interruption preserves the in-progress session and current question. Operator end produces an incomplete session. Repeat/clarify actions are deterministic.
- APIs under `/api/screening-sessions/{session_id}/conversation` start/resume, inspect state/history, submit a simulation response, repeat, clarify, interrupt, and end.
- Revision `0006_screening_conversations` creates the conversation/turn tables after `0005_screening_workflow`; file only, not applied. No provider, transcript, LLM, speech, frontend, or live-call behavior is introduced.

## Provider boundary
Keep provider-specific payloads inside the adapter. The application-facing interface should expose only the operations required by the POC, initially:
- initiate_call
- get_call_status
- get_transcript (where supported)
- webhook event normalization

Other methods from the BRD (recording, transfer, termination) are not automatically implemented; verify them and defer unless necessary for the MVP or explicitly approved.

## Deployment
Docker packaging is proposed for reproducibility. Actual deployment provider and configuration are TBD and require owner approval.

## Data handling
Store only POC-needed data. Use consenting test participants. Avoid logging sensitive candidate information. Do not store recordings unless needed and explicitly approved.

## Recruitment agent configuration foundation (Milestone 8)
`app.recruitment_agent.schemas` defines a validated provider-neutral configuration with candidate application context, existing job context, the screening session's ordered question snapshot, saved answer provenance, configurable instructions, language behavior, and requested extraction field names. `RecruitmentAgentConfigurationBuilder` loads the candidate/session relationship and answers from existing tables, rejects missing or mismatched records, and omits the candidate phone by default. It does not derive absent job requirements or candidate answers.

`RecruitmentAgentPreparationService` composes the builder with an explicitly supplied `AgentConfigurationConsumer`. The local `MockAgentConfigurationConsumer` validates and retains a deep copy in memory for tests; it is not an AI agent, makes no requests, and cannot initiate calls. This optional configuration-consumer contract is separate from `CallProvider`, so existing call providers need not implement it. No API route or database schema change is needed. Adapters must translate this model only after their native configuration contract is verified; this milestone defines no Bolna or Retell payload.

## Phase 3 Milestone 9B Bolna integration

The Bolna flow composes the existing M8 `RecruitmentAgentConfigurationBuilder`, the `BolnaAdapter`, and the existing `CallLifecycleService`. `POST /api/screening-sessions/{session_id}/bolna-call` builds context from the candidate, job fields already stored on the candidate application, saved screening answers, and the session's ordered question snapshot. It uses a stable session-derived idempotency key, creates an application-owned call UUID, links the call to the screening session, and sends the request through the Bolna adapter. A partial unique database index allows at most one Bolna call record per candidate application; its migration preflights and reports existing duplicate IDs instead of deleting or merging calls. The mock provider remains the default for generic call creation; Bolna is selected only by the explicit Bolna route and only when `BOLNA_CALLS_ENABLED` is enabled server-side.

Bolna's documented `/call` request accepts `agent_id`, `recipient_phone_number`, and `user_data`. The adapter sends only these supported fields and never sends `retry_config`. It serializes the validated recruitment context as documented dynamic-variable values. Candidate phone and email are excluded from `user_data`; the normalized phone is included only as the required server-side call destination. The external Bolna agent must already contain matching placeholders and instructions: this application does not create or modify provider agents, and runtime behavior of the provider-side prompt still needs validation.

The adapter maps the provider `execution_id` into `Call.provider_call_id`. `POST /api/calls/{call_id}/bolna-sync` uses documented `GET /executions/{execution_id}` to retrieve execution status, transcript, extraction, duration, and summary when present. Results are stored on the linked screening session. Provider extraction is retained as raw JSON and is not converted to `ScreeningAnswer` or `ScreeningEvaluation`, because the exact output schema and explicit/inferred provenance are not guaranteed by the current evidence.

Bolna `call-disconnected` maps to normalized `finalizing`, a nonterminal state. If a completed execution is retrieved after an interim event was missed, the sync service records a local finalizing step before completion. Existing transition guards prevent a delayed finalizing event from regressing a completed call. Provider and local event IDs deduplicate repeated events. Call creation timeouts, 403, 429, 5xx, invalid successful responses, and unknown outcomes remain ambiguous; there is no automatic call retry. Session-scoped idempotency prevents an API replay from issuing a second call.

Webhook handling currently consists only of an offline processor that validates a configured shared-secret value, validates a normalized execution payload, and delegates status updates to the lifecycle service. No webhook route is registered or exposed. Bolna's webhook signature, delivery-retry contract, and unique event IDs remain unverified, so public ingress is deferred. Shared-header authentication is defense-in-depth only and must not be treated as provider signature verification.

Migration `0007_bolna_finalization` follows `0006_screening_conversations`. It adds the nonterminal call status to database check constraints and adds nullable transcript, summary, raw extraction, and duration columns to `screening_sessions`. The migration is created but has not been applied. Provider activation is false by default, and India route/legal readiness, consent, retention, costs, and controlled-test approval remain blockers before any real call.
