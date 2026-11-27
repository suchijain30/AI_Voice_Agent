# Milestone 7 — Native Voice AI Evaluation and POC Configuration

**Status:** Public-source review and configuration preparation completed for owner review. Controlled tests have not started. No provider is selected.

**Evidence date:** 2026-11-27. Sources below are official product documentation/pages unless explicitly identified as vendor marketing. Official documentation verifies that a feature or integration is described; it does not prove operational availability, quality, or suitability for this POC.

## 1. Decision and scope

Use each managed platform's built-in/recommended conversation stack as the baseline. Do not add a separate LLM by default. A standalone LLM is a later fallback only if a controlled test demonstrates a material miss against a pre-agreed P0 threshold and the owner approves the resulting cost, latency, data flow, and integration.

The two comparison candidates remain **Bolna and Retell**. This is not a provider selection. Both have offline adapters, but neither adapter is wired to the application call route. `MOCK_CALLS_ENABLED`, `BOLNA_CALLS_ENABLED`, and `RETELL_CALLS_ENABLED` default to false. The route currently constructs `MockProvider` only.

This is a configuration and evidence milestone, not a live integration milestone. No agent/account was configured, no credential was used, and no call or provider simulation was performed.

## 2. Evidence interpretation

| Label | Meaning |
|---|---|
| Native | Described as a capability of the managed platform. |
| Integration | Depends on a named external model, telephony provider, or carrier connection. |
| Custom | Requires application-owned implementation/configuration. |
| Unsupported | Documentation says the capability is unavailable. |
| Unverified | Public evidence is insufficient or actual operation has not been tested. |
| Vendor claim | Product/marketing claim; not an independent or measured result. |
| Official docs | Technical/product documentation. Still not proof of our configuration working. |

Confidence is about whether the cited source supports the narrow documented claim, not about real-call performance.

## 3. Managed platform comparison

| Capability | Bolna | Retell | POC assessment |
|---|---|---|---|
| Agent construction | **Native.** Agent Studio has identity, conversation/guardrails, and closing configuration; graph agents offer explicit nodes. Auto Build's 5–8 minute creation claim is vendor-provided. | **Native.** Supports single/multi-prompt agents and structured conversation-flow agents. The official docs recommend choosing the type based on required control. | Both have an appropriate native authoring path. The fastest configuration claim is not measured for our questions. |
| LLM / conversation intelligence | **Native platform capability with configurable/bundled models and BYOK integrations.** Exact current default model/version and pricing for our account: **UNKNOWN**. | **Native platform capability with selectable model configurations;** custom LLM is also documented. Exact default model/version and selected plan: **UNKNOWN**. | Use bundled/native default in the first comparison. Do not assume either native stack is identical to its competitors' model quality. |
| STT and TTS | Managed pipeline with selectable/bundled model options and language-specific integrations. Exact default STT/TTS/model pair for a new agent: **UNKNOWN** until the dashboard/account is inspected. | Platform voice and ASR options are listed by language; provider combinations vary. Exact selected pair: **UNKNOWN** until configured. | Freeze and record the precise model IDs/settings before controlled tests. |
| Dynamic conversation / follow-ups | Native prompt/graph workflow features; recruitment follow-up behavior is a **vendor claim** and unmeasured. | Native single-prompt and conversation-flow options; dynamic dialogue is documented, actual recruitment relevance unmeasured. | Compare the end-to-end result, not feature lists. |
| Question flow | Graph agents and configurable conversation flow are documented. Exact ability to consume our per-session question list at call time is **UNKNOWN**. | Conversation flows and dynamic variables are documented. Exact ability to consume our per-session question list through the current adapter is **not implemented**. | Keep questions in `ScreeningSession.question_config`; do not copy them into provider adapters. A later integration needs an approved context mapping. |
| Context / corrections | Per-call context and multilingual starting-language options are described in Bolna outbound materials. Correction quality and cross-turn retention are **unverified**. | Dynamic variables, conversation memory/features, and multi-turn flows are documented. Recruitment answer correction behavior is **unverified**. | Test correction cases and ensure the final value follows the candidate's latest explicit correction. |
| Structured extraction | Bolna documents post-call **Extractions**. Older `agent_extraction`/custom analytics approaches are described as retired in the current docs. Confidence/field outputs are described, but provenance compatible with our `explicit`/`inferred` schema is **UNKNOWN**. | Native Post Call Extraction supports custom structured fields and result access through call analysis/API/webhooks. Exact ability to reliably label explicit vs inferred facts is **UNKNOWN**. | Map only after measuring field accuracy. Keep transcript/raw answers as evidence; never treat an unsupported inference as an explicit candidate fact. |
| Transcript / call outcomes | Call API quickstart describes retrieving call details/transcript; execution lifecycle and transcript retrieval are documented. Exact API integration is not in our application. | Get Call, call history, and transcript-related webhooks are documented. | Both appear capable on documentation; our app has no provider retrieval/webhook integration yet. |
| Webhooks | Call lifecycle/execution webhooks documented; delivery, retry, signature/authentication, and payload stability for our use must be verified. | `call_started`, `call_ended`, `call_analyzed`, transcript updates and transfer events documented. Provider docs state webhook endpoint must be publicly reachable and retries may occur. | No public endpoint/tunnel exists in this POC. Webhook implementation requires a later security-reviewed milestone and explicit public exposure approval. |
| Interruption / turn handling | Settings and provider pipeline support are described; actual barge-in performance **unmeasured**. | Interruption and turn behavior are configurable; actual performance **unmeasured**. | Measure end-of-candidate-speech to first agent audio, barge-in stop time, recovery, and lost/repeated content. |
| English / Indian English | English is documented; accent accuracy **unmeasured**. | `en-IN` is listed for ASR and TTS provider combinations; quality **unmeasured**. | Use Indian English audio in benchmark, including names, amounts, skills, and notice periods. |
| Hindi | Vendor lists Hindi support; specific bundled provider/model and real call quality **unverified**. | `hi-IN` is listed for several ASR/TTS providers. Retell states that the dashboard's available combination picker is the current compatibility source of truth. | Capability listing is not a quality result. Test Hindi end-to-end using the exact provider combination. |
| Hinglish / code-switching | Bolna explicitly advertises Hinglish and mid-call language switching across supported Indian languages (**vendor claim**). | Retell documents multilingual language selection and says Deepgram/Soniox support code-switching across their listed languages. Exact Hindi-English code-switch combination and agent response quality **unverified**. | Include the approved Hinglish scenario. For Retell, confirm the exact ASR/TTS combination in the live dashboard before freezing a test. |
| India outbound | Bolna lists India telephony integrations (including Exotel, Plivo, Vobiz and SIP/carrier choices) and +91 routing. Actual number availability, recruitment-call classification, DLT/carrier approval, and successful mobile termination are **not verified**. | Retell documents custom SIP and outbound calling generally. The reviewed evidence does not confirm a compliant Indian mobile route, number, or carrier for this use case. | **Mandatory gate not passed for either.** Bolna has more India-specific public evidence, but that does not establish a permitted, provisioned route. |
| API fit | Existing offline adapter sends only documented `agent_id` and `recipient_phone_number`; it does not send candidate/job/question context. | Existing offline adapter sends `from_number`, `to_number`, and optional `override_agent_id`; it does not send candidate/job/question context. | The provider-neutral `ProviderCallRequest` already includes job title/description, but both adapters currently ignore them. This is a real integration gap for role-aware agents, not a reason to invent undocumented API fields. |
| Cost for 5 minutes | Public headline $0.06/min gives **$0.30 arithmetic** for 5 minutes. Current Bolna pricing page and detailed pricing docs conflict about whether telephony/platform are included; actual all-in India cost is **UNKNOWN**. | Public managed voice-agent range $0.07–$0.31/min gives **$0.35–$1.55 arithmetic** for 5 minutes before any unpriced/route-specific telephony or additions. Actual India all-in cost is **UNKNOWN**. | These are not quotes or complete estimates. Before testing, request a written configuration-specific breakdown and set a spend ceiling. No credits were used. |

### Evidence notes and confidence

- **Bolna workflow/extraction/telephony evidence — official documentation, medium-high confidence for documented availability; low confidence for actual POC suitability.** [Agent Studio](https://www.bolna.ai/docs/agent-setup/studio), [platform capabilities](https://www.bolna.ai/ai-voice-agent-platform), [recruitment product page](https://www.bolna.ai/recruitment), [call analytics](https://www.bolna.ai/call-analytics), [outbound calling](https://www.bolna.ai/ai-outbound-calling), [telephony integrations](https://www.bolna.ai/integrations/telephony), [SIP trunking](https://www.bolna.ai/sip-trunking), and [Exotel integration](https://www.bolna.ai/integrations/exotel). Recruitment, language quality, latency, and compliance statements on product pages are vendor claims.
- **Bolna API/pricing evidence — official docs, medium confidence; account-specific pricing unknown.** [API quickstart](https://www.bolna.ai/docs/quickstarts/api), [pricing page](https://www.bolna.ai/pricing), [cost overview](https://www.bolna.ai/docs/get-started/what-it-costs), [detailed component pricing](https://www.bolna.ai/docs/pricing/call-pricing), and [migration to Extractions](https://www.bolna.ai/docs/migrating-to-extractions/overview). Pricing-page copy and detailed pricing documentation do not describe inclusions consistently; the all-in rate must be confirmed in writing.
- **Retell language evidence — official docs, high confidence that language options are listed; low confidence in actual quality.** [Multilingual agents](https://docs.retellai.com/agent/multilingual) and [supported ASR/TTS languages](https://docs.retellai.com/build/language-support). The docs list `en-IN` and `hi-IN`, describe code-switch ASR options, and warn that multilingual ASR may reduce accuracy compared with a single-language setup.
- **Retell agent/extraction/telephony/webhook evidence — official docs, medium-high confidence for documented features; actual integration/India route unknown.** [Agent type guidance](https://docs.retellai.com/build/choose-agent-type), [Post Call Extraction](https://docs.retellai.com/features/post-call-analysis-overview), [analysis field configuration](https://docs.retellai.com/features/post-call-analysis-create), [call analysis consumption](https://docs.retellai.com/features/post-call-analysis-consumption), [webhooks](https://docs.retellai.com/features/webhook-overview), [custom telephony](https://docs.retellai.com/deploy/custom-telephony), and [create phone call API](https://docs.retellai.com/api-references/create-phone-call).
- **Retell pricing evidence — official pricing page, high confidence in the displayed range, low confidence as an all-in India quote.** [Retell pricing](https://www.retellai.com/pricing). The page shows $0.07–$0.31/min for voice agents and itemizes telephony separately in its estimator. Model, voice, add-ons, number/carrier route, and volume change the price.

All linked pages were accessed 2026-11-27. They are public-source evidence only. No capability above is marked experimentally verified.

## 4. India outbound mandatory gate

| Gate | Bolna | Retell |
|---|---|---|
| Publicly documented Indian telephony path | Yes: provider pages list India-focused carriers and SIP/Exotel paths. | Generic custom SIP / imported-number path is documented; India-specific compatible route was not confirmed. |
| Actual +91 mobile termination available to this project | **UNKNOWN** | **UNKNOWN** |
| Correct number series and classification for recruitment screening | **UNKNOWN**; carrier/compliance confirmation needed. | **UNKNOWN**; carrier/compliance confirmation needed. |
| Required registration, consent, permitted hours, caller ID and recording/transcript disclosures resolved | **No** | **No** |
| Gate result | **Not passed** | **Not passed** |

Do not initiate calls until the selected carrier/provider confirms in writing the number type, permitted recruitment-screening use, registration/consent requirements, rate, geography, and route. Bolna's public India carrier listing is a lead for verification, not evidence that this project's call is approved. Retell's generic SIP interoperability is not proof of India mobile access.

## 5. BRD P0 coverage and POC-specific language validation

The original BRD priority structure is unchanged. Hindi/Hinglish remain P1 in the BRD; this POC separately requires them as validation scenarios. This is a POC test overlay, not an edit to the BRD.

| Original P0 capability | Native platform evidence | Current application state / gap |
|---|---|---|
| Outbound call | Both document call initiation; India gate unresolved. | Offline adapters exist; application call route is mock-only and disabled. |
| AI introduction and willingness/consent | Prompt/agent configuration allows welcome/guardrails; vendor language does not prove compliance. | No live agent or test; exact consent phrasing and stop behavior require controlled checks. |
| Two-way conversation, questions, contextual replies and follow-up | Both describe configurable agents/workflows. | Native quality and per-call context are untested; current adapters do not pass job or question context. |
| Information extraction and structured summary | Bolna Extractions and Retell Post Call Extraction are documented. | Output schema mapping, field accuracy, confidence semantics, and explicit/inferred provenance unverified. |
| Transcript retrieval/storage | Both document transcript access/artifacts. | No provider transcript retrieval, webhook, or storage integration exists. No real candidate transcript is stored. |
| Basic result output/dashboard | Provider analytics pages exist; app has candidate intake/list and screening APIs. | Provider call results are not connected to the app; results dashboard is not implemented. |

## 6. Proposed acceptance thresholds — freeze before testing

These are **proposals for owner review**, not achieved results. Freeze or revise them before controlled testing; do not tune them after viewing comparative results.

1. **India route hard gate:** written provider/carrier confirmation of permitted +91 mobile outbound recruitment-screening calls, approved number series/registration path, caller identity, permitted calling window, and complete itemized rate. Failure blocks the provider regardless of score.
2. **Disclosure / candidate control:** 100% correct AI identity and call purpose in scripted checks; 100% respect of refusal/stop with no subsequent screening questions. Any violation blocks the configuration.
3. **Extraction:** at least 90% field-level exact/normalized accuracy on the manually labelled POC fields, using the BRD reference target. Report per-field and language results; do not treat a small exploratory sample as statistical proof.
4. **Fabrication / provenance:** zero critical fabricated candidate facts in the benchmark; every returned field must be supported by candidate-stated content or marked inferred/uncertain/missing. Unsupported provider provenance must be preserved as unknown, not upgraded to explicit.
5. **Conversation behavior:** all expected actions in the frozen scenarios must match the rubric for consent, refusal, stop, correction, clarification, follow-up, and completion. Report raw pass counts and confidence intervals.
6. **Hindi/Hinglish validation overlay:** report language-specific field accuracy and behavior separately; proposed minimum 90% field accuracy for the manually labelled Hindi and Hinglish subsets, with the same no-fabrication gate. Exact sample count must be expanded if uncertainty could change the decision.
7. **Latency:** proposed P95 of no more than 3.0 seconds from end-of-candidate-turn to first audible agent response for connected test turns. Measure end-to-end on the actual route; vendor estimates do not count.
8. **Reliability/artifacts:** for accepted completed test calls, call status, full transcript, and structured output must be retrievable and correlated to the correct internal call/session. Record webhook/API delivery failures; no call is silently considered complete without artifacts.

Owner confirmation is needed for the proposed latency threshold and acceptance of 90% as the field-level operational definition of the BRD's extraction target.

## 7. Native agent configuration proposal

The non-runtime template is [native_recruitment_agent.example.json](native_recruitment_agent.example.json). It has no provider ID, API key, phone number, company name, candidate record, or active/enabled setting. It references the existing per-session `question_config` rather than duplicating questions in provider adapters.

Initial stack policy:

- Use the provider's bundled/default LLM, STT, and TTS for the first baseline; record exact model IDs before each test.
- Do not add a separate LLM, external STT/TTS key, or voice cloning unless a frozen P0 result demonstrates a material gap and the owner approves the change.
- Configure English (India) and Hindi as the language test conditions. Hinglish is a test condition, not assumed to be a separately selectable language or to work because the vendor lists Hindi and English.
- Pass candidate/job/question context dynamically only through provider fields/API behavior that is verified. The current adapters do not implement that mapping; do not add speculative payload fields.
- Treat extraction output as advisory. The application retains final decision authority; providers do not hire, reject, rank, or schedule candidates.

## 8. Controlled test plan proposal (not authorized/executed)

1. Freeze the acceptance thresholds, question set, prompt revision, exact provider agent/model/voice/ASR configuration, language, telephony route, sample selection, and scoring rubric.
2. Resolve both India route gates in writing and obtain the necessary owner/compliance approval before opening provider accounts or paying.
3. Use only fictional candidate/job data and internal adult test participants who explicitly authorize the specific call, language, data transfer, transcript/recording, retention, and deletion conditions. Never use production candidate data.
4. Start with safe provider simulation, if the vendor confirms whether it incurs charges and whether any real telephony is involved. Do not send data until the provider's data handling is reviewed.
5. If approved, compare native default configurations on the same 24 scenarios, with three randomized exploratory runs per scenario/provider. At a five-minute planning duration this is 72 calls / 360 connected minutes per provider (144 calls / 720 minutes total if every run is connected). Actual call count/duration may differ.
6. Cost arithmetic for this illustrative baseline: Bolna headline model rate `$0.06 × 360 = $21.60` per provider, but India telephony/platform inclusion is contradictory in public pages; total is **UNKNOWN**. Retell headline range `$0.07–$0.31 × 360 = $25.20–$111.60` per provider, before route-specific telephony and additions; total is **UNKNOWN**. These calculations do not authorize spend and are not quotes.
7. Preserve exact model/config version, timestamps, audio/test script, transcript, output, error, per-turn latency, and cost. Score blinded human judgments for conversation quality where feasible; compute field accuracy against manually labelled expected values.
8. Treat 24×3 as exploratory only. Report n, mean/median/SD, min/max, P50/P90/P95 latency, field-level rates and 95% intervals where meaningful. Expand paired scenario runs if variance or intervals leave open a decision-changing ranking/threshold result. Do not claim significance from the baseline alone.
9. Do not run the controlled experiment until a separate plan specifies actual participant numbers, precise data, provider endpoints, number series, configuration, retention, maximum spend, and explicit approvals.

## 9. Minimum integration work identified (not implemented)

- Keep the current provider abstraction and call lifecycle. The current route must remain mock-only until separate integration approval.
- Add a provider-neutral call context object derived from the candidate and screening-session snapshot (candidate name, company/role/job description, configured questions, session/call IDs). The server—not the frontend—must select and validate these values.
- Extend each adapter only with request fields that the corresponding current official API documents and that are verified for dynamic runtime context. Current Bolna and Retell adapters do not send the per-call job description or question configuration. If a provider requires a static dashboard agent, that limitation must be tested against different role question sets.
- Add provider result ingestion only after the provider webhook/API contract, signature verification, retries/idempotency, transcript data handling, and secure public callback strategy have been approved. Do not expose a tunnel as part of this milestone.
- Map provider extraction fields to existing `ScreeningAnswer` / `ScreeningEvaluation` models, preserving original transcript/answer evidence and marking provenance accurately. A provider's confidence score is not itself a correctness guarantee.
- Keep mock as default and all live-call flags false. No schema changes are currently justified by this evaluation; transcript retention design requires a separate privacy/data-retention decision before implementation.

## 10. Unknowns and next approvals

- Actual India mobile route, number allocation, recruitment-call compliance, caller ID, DLT/carrier process, calling-hour policy, and complete local call rates for both candidates.
- Exact default bundled models/voices and price inclusions on each account/plan; Bolna public pricing descriptions conflict about telephony/platform inclusion.
- Native Hindi/Hinglish and Indian English understanding, transcription, naturalness, latency, barge-in, correction handling, and extraction accuracy.
- Whether extraction returns reliable field-level provenance and evidence spans compatible with this project's explicit/inferred distinction.
- Dynamic per-call question/job context for both providers through exact supported API fields.
- Data retention, transcript/recording storage, deletion, residency, subprocessors, and security terms for the chosen plan.
- Owner approval of proposed thresholds, experiment participants/test numbers, route, data, maximum spend, account creation, and controlled calls.

**Recommendation:** keep both vendors in the controlled test shortlist; prioritize verifying Bolna's India carrier path because official pages name Indian integrations, but do not select it. Retell remains a comparison candidate only if an India-compatible route is verified. A final recommendation is premature until the mandatory India gate and controlled quality/cost testing pass.
