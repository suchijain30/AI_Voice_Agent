# POC Scope and Requirements

## Objective
Demonstrate an AI-powered outbound HR screening call, collect candidate information, retrieve the transcript, and generate a structured profile and screening summary. This is a two-day proof of concept, not a recruitment platform.

## P0 — Implement
- Candidate input form (manual entry)
- Outbound telephone call
- AI introduction and purpose disclosure
- Ask whether candidate is willing to proceed; handle decline politely
- Natural two-way interaction
- Configurable screening questions based on job requirements
- Contextual responses and basic follow-up for vague/incomplete answers
- Candidate information extraction
- Call status/outcome tracking
- Transcript storage/retrieval
- Structured candidate JSON
- Screening summary and advisory recommendation
- Basic dashboard showing candidate details, call status, summary, extracted fields, and transcript

## Candidate inputs
- Name
- Phone number
- Email (optional)
- Job title
- Job description
- Required skills/experience
- Preferred location/work arrangement

## Initial screening topics
- Currently exploring opportunities?
- Total professional experience
- Relevant experience
- Technologies and skills
- Current compensation and expected salary
- Notice period
- Location and work-arrangement fit
- Interview availability

Questions should be configurable and not hardcoded into provider-specific calling logic.

## Candidate output
Structured fields should include candidate name, job title, call status, total experience, relevant experience, current/expected salary, notice period, location, skills, interest level, interview availability, missing information, screening summary, advisory recommendation, recommendation reason, and next action.

Explicitly stated facts must be distinguishable from inferred values. The recommendation is advisory only; recruiter makes the final decision.

## P1 — Research/document only
- English, Hindi, regional languages
- Scheduling
- Retry rules
- Human transfer
- Interruption handling
- Webhooks
- Function calling
- Custom LLM
- Custom STT/TTS
- Recording storage/retrieval
- Concurrency
- Analytics
- HRMS/ATS integrations

For each vendor, mark support as Native, Integration, Custom, Unsupported, or Unverified and provide evidence.

## Explicit exclusions
No ATS/HRMS implementation, multi-tenancy, authentication, RBAC, scheduling workflow, WhatsApp, SMS, candidate pipeline, multiple use cases, visual builder, calendar integrations, enterprise access controls, or advanced reporting.

## POC test scenarios
- Candidate answers all questions
- Vague answers trigger a follow-up
- Candidate declines
- Candidate asks an unrelated question
- Candidate interrupts
- Candidate corrects a previous answer
- Candidate does not answer
- Candidate gives incomplete information
- Call disconnects
- Call completes successfully and generates output

## Success criteria
- Outbound call initiation demonstrated
- End-to-end screening demonstrated
- Transcript retrieval works
- Structured extraction evaluated against manually labelled test calls
- Summary generation works
- Dynamic follow-up demonstrated
- Call statuses recorded
- Vendor comparison completed
- Pricing analysis completed
