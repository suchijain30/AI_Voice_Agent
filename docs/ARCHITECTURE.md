# Architecture (Proposed)

## POC flow
Candidate input UI → FastAPI → PostgreSQL → provider adapter → voice provider/telephony → candidate conversation → provider webhook/transcript → extraction and summary → PostgreSQL → results UI.

## Components
- React/Vite + Material UI: candidate input and results dashboard
- FastAPI: API, orchestration, webhook receiver
- PostgreSQL: candidate, call, transcript, extraction and summary persistence
- Pydantic: API contracts and structured extraction validation
- Voice provider adapter: encapsulates provider-specific call initiation/status/transcript operations needed for the MVP
- Screening service: provider-independent screening question and evaluation logic

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
