# Project Plan and Status

## Delivery constraint
Two-day MVP. Build incrementally; obtain owner approval before each phase and before significant changes.

## Phase 0 — Foundation (documentation scaffold)
**Status: Prepared; repository initialization and owner review pending.**
- README, AGENTS, scope, plan, architecture, decisions, work log
- Ignore rules and environment-variable template
- No application code

Acceptance: owner reviews and approves scaffold.

## Phase 1 — Candidate input and backend foundation
**Status: Not started.**
- FastAPI skeleton
- PostgreSQL connection and initial schema
- Candidate create/list endpoints
- React/Vite/Material UI candidate form and list
- Basic validation and tests

Acceptance: candidate can be entered and retrieved from database/UI.

## Phase 2 — Outbound voice provider
**Status: Not started.**
- Verify provider account/credentials/telephony requirements
- Provider adapter/interface
- Initiate outbound call
- Persist provider call ID and state
- Webhook endpoint for call events
- Test call using consenting test participant

Acceptance: an outbound test call can be initiated and its outcome is recorded.

## Phase 3 — Screening conversation
**Status: Not started.**
- AI disclosure, purpose, role/company context, willingness check
- Configurable question list
- Dynamic contextual responses
- Basic follow-ups
- Decline/exit handling
- Prompt guardrails

Acceptance: test call conducts the initial screening flow.

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

## Phase 6 — Testing and vendor/pricing documentation
**Status: Not started.**
- POC scenario testing and results
- Extraction accuracy review against manually labelled test conversations
- Vendor feature matrix and weighted scorecard
- Pricing/unit economics
- Architecture diagram
- Known limitations
- Final recommendation

Acceptance: evidence-based documentation delivered; unknowns explicitly marked.

## Status convention
- Not started
- In progress
- Blocked
- Prepared for review
- Complete

## Current blockers / open decisions
- Confirm voice provider after checking current India outbound telephony requirements, account access, pricing, and POC testing.
- Confirm deployment target and its database/service options before deployment work.
- Decide the exact LLM/extraction provider only when required for implementation.
