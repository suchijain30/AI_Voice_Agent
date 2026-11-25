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
**Status:** Not finalized.
Bolna is the initial India-focused candidate; Vapi and Retell remain alternatives. Verify outbound India telephony, available numbers/routes, language performance, transcript access, webhook support, setup friction, and full cost before committing. Vendor statements should be evidence-backed; marketing claims alone are not proof.

### D-006: Provider abstraction
**Accepted requirement:** keep vendor integration replaceable, but implement only what the POC needs. Do not over-engineer a multi-provider framework.

### D-007: Coding-agent independence
Repository instructions and project state must be maintained in Markdown files so Codex, Cursor, Claude, or other agents can continue without relying on chat history.
