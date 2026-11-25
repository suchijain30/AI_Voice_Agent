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
- Initial voice-provider candidate: Bolna, subject to verification and approval
- Provider abstraction: application code should not be coupled to one vendor

## Project status
- [x] Scope and BRD reviewed
- [x] Phase 0 project instructions and documentation scaffold
- [ ] Phase 1 candidate form and backend foundation
- [ ] Phase 2 outbound voice integration
- [ ] Phase 3 screening conversation
- [ ] Phase 4 transcript, extraction, summary
- [ ] Phase 5 dashboard
- [ ] Phase 6 tests, vendor comparison and pricing

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

## Candidate consent and compliance
Use only test candidates who have agreed to participate in the POC. The calling agent must disclose that it is an AI recruitment assistant, explain the purpose, and ask whether the candidate is willing to continue. Recording/transcription disclosures and applicable Indian telecom/privacy requirements must be validated before any real deployment.

## Definition of Done
A candidate can be entered, receive an AI outbound call, complete an initial HR screening conversation, and have the call converted into a structured profile and summary displayed in the dashboard. The POC must also include documented vendor/pricing evidence, test outcomes, and limitations.

## Current implementation
This Phase 0 scaffold contains documentation and development rules only. No application code or provider integration has been implemented yet.
