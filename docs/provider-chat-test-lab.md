# Provider Dry-Run Test Lab

## Ownership

- Actor: Provider User
- Dashboard route: `/sqlexplore/chat-test-lab`
- API boundary: `/api/v1/provider/chat/dry-run/*`
- Permission: `provider.chat_test_lab.manage`
- Tenant scope: the Provider selects a Client and device; the API verifies that the device belongs to that Client.

The feature is intentionally unavailable from the Client Dashboard. It needs cross-Client access to inspect catalogs, conversation state, pipeline configuration, and candidate Learn Mappings.

## Safety model

The runner reuses the production native agent, knowledge retriever, LLM response generator, and conversation-state finalizer. It never calls the production persistence methods or `FonnteClient`.

The output lists the writes and external calls that production would attempt, but marks all database writes and the Fonnte send as blocked. Candidate mappings are copied into an in-memory catalog overlay and are never published.

Copy actions use the sanitized report. Phone numbers, email addresses, URLs, tokens, and address fields are redacted before the audit summary or JSON is copied.

## Implemented scope

- Client and device selection
- Fresh or custom conversation state
- Registration business state
- Published, candidate, and before/after mapping modes
- Native-only and full-pipeline execution
- Knowledge and registration-invitation switches
- Intent, candidates, entities, slot inference, knowledge, native reply, LLM reply, state, and planned-side-effect trace
- Expected-result validation
- Automated before/after diff and conclusion
- Sanitized audit summary and JSON copy

## Deferred phases

Production trace replay, conversation sequences, persisted dry-run results, and regression-suite storage remain follow-up phases. They require dedicated immutable test-result tables and audit policy rather than writing into production conversation tables.
