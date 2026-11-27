# Milestone 9A — Bolna Provider Selection & Integration Readiness

**Research date:** 2026-11-27

**Status:** Public documentation review complete. No accounts, APIs, calls, or telephony configuration were used.

**Decision posture:** Bolna is the preferred provider for M9B implementation planning; Retell remains the backup. This is a provisional preference, not a final provider selection.

## Executive summary

Bolna's current public API documentation verifies a basic `POST /call` contract, execution retrieval, per-call dynamic variables, and status webhooks. This is enough to plan a Bolna adapter extension and a staged integration. The current adapter implements the minimal create call correctly, but it does not pass recruitment context, choose a caller number, retrieve execution results, or receive webhooks. Its current status model also cannot represent Bolna's documented two-step call ending safely: `call-disconnected` is an interim event and `completed` follows after final transcript/extraction data is assembled.

Bolna documents India-oriented telephony through Plivo, Exotel, Vobiz and customer SIP. Exotel documents the account, KYC, ExoPhone and app setup needed for outbound routes. This establishes a plausible technical path, not a verified route for this project. Current TRAI material defines A2P calls broadly and requires prior declaration to the originating access provider for relevant commercial communications. The classification of candidate-recruitment calls, assigned number series, consent evidence, and the actual account route remain unconfirmed.

**India outbound readiness: UNKNOWN.**

**M9B recommendation:** GO for disabled-by-default integration code and mocked contract tests. NO-GO for enabling the adapter, sending candidate data to Bolna, or initiating controlled calls until the gates below are satisfied.

## Provider decision

| Role | Provider | Status |
|---|---|---|
| Primary for M9B readiness and implementation | Bolna | Preferred by project owner; not activated; final selection pending controlled comparison |
| Backup | Retell | Retained as comparison/backup; no provider winner declared |

This preference directs the next engineering effort only. India route feasibility, measured screening quality, language performance, latency, and cost per completed screening have not been experimentally validated.

## Verified Bolna API facts

Sources were accessed on **2026-11-27**. “Verified” below means stated in current public documentation, not independently exercised against a Bolna account.

| Area | Publicly documented fact | Evidence type / confidence | Limitation |
|---|---|---|---|
| Create call | `POST https://api.bolna.ai/call`; `agent_id` and `recipient_phone_number` are required. Recipient must be E.164. | Official API reference; high | No request has been sent by this project. |
| Authentication | `Authorization: Bearer <token>`. | Official API reference; high | Credentials are not held or configured for this research. |
| Optional call fields | `from_phone_number`, `scheduled_at`, `user_data`, `agent_data`, `agent_version_id`, `retry_config`, and `bypass_call_guardrails` are listed. `from_phone_number` selects a purchased/registered number; omitted means account default. `agent_data` documents `voice_id` and `language` overrides, but says they are not used together. | Official API reference; high | Which combinations work with the specific India route/account must be confirmed. Do not use `bypass_call_guardrails`. |
| Dynamic values | `user_data` provides dynamic variables referenced in the configured agent prompt/welcome message using placeholders such as `{{customer_name}}`. | Official API reference; high | Variable substitution is documented; structured arrays, prompt loops, or arbitrary dynamic dialogue plans are not. Validate a conservative string-based question representation before using real calls. |
| Agent setup | A call requires an existing `agent_id`. Official quickstart shows agent creation at `POST /v2/agent` with `agent_config` (tasks/toolchain/model/transcriber/synthesizer/input/output) and `agent_prompts`. Agent versions can be selected by optional `agent_version_id`. | Official API quickstart/reference; high | Agent configuration is a separate setup step. Exact production configuration and supported model/locale choices need an offline configuration review and then controlled validation. |
| Create response | Example response contains `message`, `status: queued`, and UUID-shaped `execution_id`. | Official API reference; high | Existing adapter accepts any nonblank string, not the documented UUID pattern, and ignores returned status. |
| Execution retrieval | `GET https://api.bolna.ai/executions/{execution_id}` returns execution details, including status, transcript, `extracted_data`, telephony data, cost, duration, and summary when enabled. | Official API reference; high | Some fields are populated only after final `completed`; payload includes sensitive transcript/recording and telephony information. |
| Status flow | Documented path: `queued → initiated → ringing → in-progress → call-disconnected → completed`; hard-failure statuses include `no-answer`, `busy`, `failed`, `canceled`, `stopped`, `error`, and `balance-low`. Wait for `completed` for finalized data. | Official API reference; high | No live status observations. The current adapter maps only five statuses. |
| Structured extraction | Bolna supports configured extraction templates/categories and places resulting `extracted_data` in the completed execution. | Official agent/extraction docs; high for feature existence | Extraction schema, exact output reliability, field provenance, Hindi/Hinglish accuracy, and recruiting-specific quality require testing. Do not treat vendor extraction as truth. |
| Webhooks | Agent webhook posts execution payloads as statuses change; custom headers can be configured; docs list three sender IPs. Payload aligns with execution response and may include pre-call events. HTTPS endpoint must be publicly reachable. | Official webhook docs; high | No documented HMAC/signature scheme was found. Delivery retry guarantees and event identifiers are not established by the reviewed pages. Custom shared-header auth and IP allowlisting should be defense-in-depth, not assumed signature verification. |
| Errors | API docs show 400 validation errors and 401 for absent/invalid Bearer key. A newly purchased number may return 429 with `retry_after_seconds`, explicitly stating no call was queued and that retry after activation is safe. | Official API reference; high for listed cases | General 403, rate-limit, and 5xx semantics are not completely specified. The adapter currently treats 403 as an authentication rejection even though this status was not established by the reviewed API reference. Timeout/5xx outcomes must remain ambiguous; do not resend without reconciliation. |
| Idempotency | No idempotency key/header or create-call idempotency guarantee appears in the reviewed create-call reference. | Official API reference search; high confidence that no guarantee is documented there | This is not proof that Bolna lacks an internal mechanism. Treat provider idempotency as unsupported until Bolna documents it. |
| Automatic retries | `retry_config` can retry `no-answer`, `busy`, `failed`, and `error`; documented maximum is 1–3 attempts, intervals configurable. | Official API docs; high | M9B must omit this field and leave provider retries disabled for the POC. No automatic retries are approved. |

Official API references: [Make Call](https://www.bolna.ai/docs/api-reference/calls/make), [API quickstart](https://www.bolna.ai/docs/quickstarts/api), [Get Execution](https://www.bolna.ai/docs/api-reference/executions/get_execution), [Webhook and call status](https://www.bolna.ai/docs/post-call/polling-call-status-webhooks), [Extractions setup](https://www.bolna.ai/docs/agent-setup/analytics-tab), [Auto-retry](https://www.bolna.ai/docs/outbound/auto-retry).

## India outbound telephony readiness — UNKNOWN

### Technical route

- Bolna's telephony integration documentation lists Plivo, Exotel, and Vobiz for India, plus customer SIP trunks. This establishes documented integration choices, not that this project has an active route or number.
- Bolna's Exotel setup guide requires an active Exotel account, ExoPhone, Exotel API key/token/account SID/domain, and separate outbound/inbound app IDs; the outbound app must be configured with Bolna's outbound Voicebot endpoint. The standard Bolna `/call` endpoint is used after the connection is configured.
- Exotel documentation says KYC approval is needed for Indian number allocation/outbound calling. It describes 140-series numbers for promotional calls and DLT registration; transactional/service DID use has separate conditions. Caller ID masking is not permitted.
- Bolna's official outbound page says trial accounts are limited to two concurrent calls to verified numbers. This is a provider-published account constraint, not a tested fact. Trial eligibility, account route, and number availability for this POC remain unknown.
- SIP/BYOT is a documented option, but SIP security, media encryption, geography, carrier termination, number assignment, and the project's engineering setup have not been validated. Exotel's own integration guide should be the primary path to verify before choosing SIP.

### Regulatory and recruitment classification

- The current TRAI consolidated TCCCPR text defines A2P voice calls to include calls initiated by an application/software/automated platform, including artificial-voice technologies. It states that a sender must declare A2P use and CLI ranges in advance to its originating access provider; a call without that declaration is treated as UCC. The Third Amendment text is reflected in the official consolidated material accessed 2026-11-27.
- TRAI lists registered-sender and commercial-communication controls. Exotel's current support guidance says it does not allow cold calling, distinguishes promotional 140-series from transactional/service DIDs, and expects supporting consent/inquiry records in relevant cases.
- No reviewed official source assigns a clear category specifically to AI recruitment screening calls to job applicants. Whether this particular use is commercial communication, service/inquiry communication, or another category—and which CLI series, consent/registration, DLT, calling-hour, and recipient-preference rules apply—must be confirmed by the originating carrier and qualified compliance counsel. An application by a candidate is not assumed to resolve this classification.
- The Fourth Amendment dated 2026-11-04 postpones commencement of the Third Amendment's regulation 35A call charge until a further notification. That affects charges, not the need to resolve sender/route classification. Verify the latest commencement notices before any call.

**Conclusion:** A plausible technical route exists, but legal classification, sender declaration, eligible caller ID/series, KYC/account allocation, and real route termination have not been confirmed. Treat readiness as **UNKNOWN / not cleared for calls**, not as a pass or a definitive technical failure.

Official references: [Bolna telephony integrations](https://www.bolna.ai/docs/telephony-integrations), [Bolna + Exotel setup](https://www.bolna.ai/docs/exotel/connect-provider), [Bolna outbound calling](https://www.bolna.ai/ai-outbound-calling), [Exotel onboarding and DND/call-type guidance](https://docs.exotel.com/business-phone-system/onboarding), [Exotel outbound calls and KYC](https://docs.exotel.com/business-phone-system/outbound-calls), [TRAI consolidated TCCCPR text (Nov 2026)](https://trai.gov.in/sites/default/files/2026-11/CR_10112026.pdf), [TRAI amendment register](https://trai.gov.in/release-publication/regulations/amendments-page/7617), [Fourth Amendment (Nov 4, 2026)](https://trai.gov.in/sites/default/files/2026-11/Regulation_TCCCPR_04112026.pdf).

## Existing adapter and integration gap analysis

### Confirmed alignment

- Existing adapter targets `POST https://api.bolna.ai/call`, uses Bearer authentication, sends the documented minimum `agent_id` and `recipient_phone_number`, and maps `execution_id` to the existing provider-call ID.
- It has no automatic retries. Transport errors, undocumented response codes, malformed success bodies, and unknown status values are handled conservatively. Credentials are kept as `SecretStr` and not added to provider error text.
- Call execution remains disabled by default; the call API currently constructs only `MockProvider`.

### Gaps to address in M9B

| Priority | Gap | M9B implication |
|---|---|---|
| Blocker | Existing `CallStatus.DISCONNECTED` is terminal and lifecycle transitions do not allow `disconnected → completed`. Bolna documents `call-disconnected` as interim, followed by `completed` with finalized transcript/extractions. | Add a normalized finalizing/interim state or otherwise safely permit this provider sequence; decide if a migration/check-constraint update is necessary before coding. Do not label the interim event completed. |
| High | M8 configuration builder is not connected to `CallLifecycleService` or `ProviderCallRequest`; adapter ignores job title/description. | Design explicit mapping for candidate/job/session/question/instruction context to Bolna `user_data` placeholders and configured static agent prompt. Do not send arbitrary PII; phone is needed for the call but stays server-side. |
| High | Adapter sends no `from_phone_number`, has no `agent_version_id` pinning, and settings only carry API key, agent ID, timeout, enabled flag. | Add configuration only after route/account choice; make caller number and agent version explicit, validated, server-only values. Exotel caller ID must be authorized and compatible with the account route. |
| High | No execution retrieval, transcript/extraction parser, polling/reconciliation service, or webhook route exists. | Implement authenticated GET retrieval and normalize only documented fields. Add webhook only after separate approval of public HTTPS ingress and security controls. |
| High | Existing normalizer maps only `queued`, `ringing`, `in-progress`, `call-disconnected`, and `completed`. | Add mappings for initiated, scheduled, no-answer, busy, failed, canceled, stopped, error, and balance-low. Keep unknown values non-successful and reconciliation-required. |
| Medium | `execution_id` validation accepts any nonblank string, while current docs specify a UUID-shaped value. Adapter doesn't validate the returned queued status. | Validate documented response shape conservatively; treat malformed/ambiguous success as reconciliation required. |
| Medium | Adapter treats 403 as a definitive authentication failure, while the reviewed API reference explicitly describes 401 but not 403. | Keep error classes sanitized and conservative until 403 behavior is confirmed; ensure the response does not leak provider text or secrets. |
| High | No provider idempotency guarantee is documented. Local idempotency only protects requests through this application; timeouts can still occur after Bolna accepts a request. | Preserve ambiguous-outcome lock by candidate and provider; never automatically resend. Reconcile by GET/search/manual review before a new request. |
| High | Current official docs support custom webhook headers and list IPs but do not document an HMAC signature; no Bolna event ID/retry contract was verified. | Use stable local deduplication keyed from execution ID + status + provider update timestamp where present, validate a configured secret header in constant time, restrict source IPs as a secondary control, and poll/reconcile missed outcomes. Confirm delivery/event semantics before launch. |
| High | Provider auto-retry is available through `retry_config`. | Always omit/disable `retry_config` for this POC; add regression tests proving request payload has no retry configuration. |

No code was changed in M9A. The existing test suite was not run because this milestone is a documentation/research-only readiness review; no implementation changed.

## M9B technical implementation plan

1. **Prepare and pin a native agent:** Establish the approved Bolna account/agent out of band after separate approval. Configure static system instructions, consent/introduction, language rules, question-following, no-fabrication, stop behavior, and post-call extraction templates. Pin `agent_version_id` where the account supports it. Keep provider selection provisional until testing.
2. **Map M8 context:** Add Bolna-specific translation inside the Bolna adapter. Map candidate name, job title/description and a bounded string representation of configured questions to documented `user_data` placeholders. Keep static persona/rules in the Bolna agent prompt. Do not assume array iteration or pass email/unneeded fields. Include normalized recipient phone only as the required call destination; configure an approved caller number separately.
3. **Call request:** Keep `POST /call`; send `agent_id`, `recipient_phone_number`, approved `from_phone_number`, `agent_version_id`, and `user_data` only when each field is verified/configured. Omit `retry_config` and `bypass_call_guardrails`. Use application-owned call UUID/idempotency and preserve no-retry behavior.
4. **Persist provider execution:** Store `execution_id` in existing `Call.provider_call_id`; persist selected agent/version and non-secret configuration version metadata only. If schema needs extension for screening association, propose migration and review first; don't add transcript to CallEvent.
5. **Status synchronization:** Support polling GET first, with explicit mapping and terminal/finalization distinction. `call-disconnected` must not prematurely end processing. Respect idempotent updates and duplicate events; unknown statuses go to reconciliation, never success.
6. **Retrieve transcript/extractions:** Fetch after final `completed`; validate payload shape and map transcript, summary, `extracted_data`, duration/cost metadata into existing screening answer/evaluation structures only where provenance can be represented. Store minimum needed data, avoid recording URL persistence/access until retention/security are approved. Do not treat extraction as verified fact.
7. **Webhook:** Defer public webhook activation until a separately approved, HTTPS, authenticated route exists. Validate secret custom header and Bolna source IPs, enforce payload bounds, deduplicate, acknowledge quickly, and enqueue/record for idempotent processing. The provider's signature and delivery retries remain unverified; retain GET reconciliation as fallback. Never expose a tunnel for this milestone.
8. **Failures and uncertain outcomes:** Map known validation/auth errors safely. Only retry a documented 429 number-activation response after its `retry_after_seconds` if a human explicitly chooses the one safe retry; do not retry other 429s, timeouts, connection loss, 5xx, malformed 2xx, or unknown status. Mark ambiguous and reconcile via execution retrieval/manual process; a new idempotency key must not bypass the lock.
9. **Mock tests:** Extend mocked HTTP tests for documented optional fields, `user_data` mapping, UUID/queued response validation, GET payload parsing, all documented statuses, finalization sequence, provider errors, retry omissions, sanitized logs/errors, duplicate webhooks, missing/duplicate payload fields, and ambiguous timeout lockout. No credentials or network required.
10. **Controlled-testing prerequisites:** Separate approval for Bolna account and spend, approved Exotel/Plivo/Vobiz route/number, written carrier and compliance classification (including A2P declaration/DLT and CLI rules), test recipients who explicitly consent, test scripts/data, call window and volume, recording/transcript retention and access, privacy/security review, webhook ingress, and rollback/contact plan. Only then propose an experiment plan and cost cap; no real-candidate use by default.

## Risks, blockers, and go/no-go

### Blockers before any controlled/live call

- Confirm in writing with the originating carrier (and counsel) how AI recruitment screening fits current TCCCPR/A2P rules and the applicable caller ID/number series, sender registration, declaration, consent/preference and operating-hour requirements.
- Confirm active account, approved India route, caller-number allocation, KYC, recipient eligibility, costs, and verified-number requirements.
- Resolve the `call-disconnected → completed` lifecycle representation before consuming final data.
- Agree on webhook authentication/delivery semantics or use polling as initial controlled path.
- Obtain separate approval for provider account creation, credentials, paid use, data transfer, and any calls.

### Recommendation

**GO for M9B offline/disabled implementation and mocked contract tests**, subject to deciding the normalized finalization-state treatment before editing the lifecycle. **NO-GO for enabling Bolna, sending candidate data, configuring public webhooks, or calling numbers** until each operational and compliance blocker is closed and separately approved. The final provider decision remains open pending controlled Bolna-vs-Retell evaluation.

## Evidence ledger

All sources below were accessed **2026-11-27**. Confidence refers to the claim as documented; vendor documentation is not experimental verification.

| Claim | Source / evidence type | Confidence / qualification |
|---|---|---|
| Bolna create-call fields, auth, response ID/status, optional fields, `user_data`, UUID format, 400 and activation 429 behavior | [Bolna Make Call API](https://www.bolna.ai/docs/api-reference/calls/make), official API reference | High for documented contract; no account call performed. |
| Minimal agent creation shape and API endpoints | [Bolna API quickstart](https://www.bolna.ai/docs/quickstarts/api), official API quickstart | High for example; full role-specific agent config still needs validation. |
| Execution retrieval, transcript, extraction payload and status semantics | [Bolna Get Execution](https://www.bolna.ai/docs/api-reference/executions/get_execution), official API reference | High for documented fields; no response obtained from an account. |
| Webhook POST and status configuration, custom headers, allowlist IPs, payload shape | [Bolna webhook guide](https://www.bolna.ai/docs/post-call/polling-call-status-webhooks), official product docs | High for documentation; signature, retries, and unique event IDs unknown. |
| Configurable structured extraction | [Bolna Extractions setup](https://www.bolna.ai/docs/agent-setup/analytics-tab), official product docs | High for feature existence; recruiting accuracy unknown. |
| Provider retry support and statuses | [Bolna Auto-retry](https://www.bolna.ai/docs/outbound/auto-retry), official product docs | High; must remain disabled for POC. |
| India providers and route options | [Bolna telephony integrations](https://www.bolna.ai/docs/telephony-integrations), official product docs | High that choices are listed; project-specific reachability unverified. |
| Exotel connected account requirements | [Bolna–Exotel integration](https://www.bolna.ai/docs/exotel/connect-provider), [Exotel guide](https://docs.exotel.com/exotel-agentstream/bolna-voice-ai-and-exotel-integration-guide), official vendor docs | High for described setup; account access and route not tested. |
| Exotel India KYC, number types and call restrictions | [Exotel outbound](https://docs.exotel.com/business-phone-system/outbound-calls), [Exotel onboarding](https://docs.exotel.com/business-phone-system/onboarding), official carrier docs | High for carrier-published requirements; applicant recruitment classification still uncertain. |
| Commercial sender registration and A2P declaration | [TRAI consolidated TCCCPR text](https://trai.gov.in/sites/default/files/2026-11/CR_10112026.pdf), official regulation text | High for wording; application to recruitment calls needs legal/carrier interpretation. |
| Latest amendment record and regulation 35A delayed commencement | [TRAI amendment register](https://trai.gov.in/release-publication/regulations/amendments-page/7617), [Fourth Amendment](https://trai.gov.in/sites/default/files/2026-11/Regulation_TCCCPR_04112026.pdf), official regulation/publication | High for amendment text; monitor further commencement notification. |
| Trial account two concurrent calls / verified numbers | [Bolna outbound calling page](https://www.bolna.ai/ai-outbound-calling), vendor public product claim | Medium; account-specific current applicability unverified and no account created. |
| Recruitment call category / required number series | No official source found that specifically classifies this use | **UNKNOWN**; must be resolved with carrier and counsel. |
| Provider idempotency guarantee, generic 429/5xx retry semantics, webhook signature/retry/event-ID guarantees | Not documented in reviewed official references | **UNKNOWN**; do not assume support. |

## Sources and research limitations

Public documentation was reviewed only. No vendor was contacted, no account was created, no API was called, no configuration was tested, and no price quote was requested. The report separates documented API behavior and regulatory text from vendor product claims, implementation findings, and unknowns. This is technical readiness research, not legal advice or proof of route availability.
