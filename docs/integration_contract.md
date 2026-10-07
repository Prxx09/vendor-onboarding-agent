# Backend integration contract

The stable entry point is `app.service.VendorOnboardingAgentService`. It returns Pydantic models or JSON-ready dictionaries and owns no frontend state. Models use Pydantic v2 `model_json_schema()` / `model_dump(mode="json")`; schemas are available from `app.schemas.assessment`, `app.schemas.review`, and `app.schemas.drafts`.

| Method | Purpose and input | Output | Errors / repeat behavior |
|---|---|---|---|
| `process_request(request_id, force=False)` | Run extraction when no extracted fields exist, then verification, validation, risk, and deterministic routing. `force=True` repeats extraction. | `AgentAssessment` | `KeyError` if missing. Default repeats downstream deterministic checks but preserves existing human field decisions by skipping extraction. |
| `resume_after_field_review(request_id)` | Re-run downstream stages after a reviewer has persisted field review changes. | `AgentAssessment` | `KeyError` if missing; `ValueError` if extraction has not produced fields. Does not change review fields itself. |
| `get_review_package(request_id)` | Build current reviewer view. | `ReviewPackage` | `KeyError` when request/risk result is absent. Read-only; contains masked values and evidence. |
| `submit_decision(request_id, decision)` | Persist one `HumanDecision` with stage, approver, role, decision, comment. | `NextRecommendation` | Approval policy errors reject missing/wrong stage, owner, requester self-approval, duplicate approver, or blocked approval. Repeated stage decision is rejected. |
| `generate_drafts(request_id)` | Generate approved vendor and PO draft revisions. | `tuple[VendorDraft, PODraft]` | `DraftGenerationError` unless status, hard-block, and required approval prerequisites pass. No ERP submission. |
| `get_report(request_id)` | Return evidence, findings, risk, provenance, approvals, drafts, and chronological audit. | JSON-ready `dict` | `KeyError` if missing. Safe to serialize with JSON; account values are masked. |

Statuses include `DRAFT`, `DOCUMENTS_UPLOADED`, `EXTRACTED`, `PENDING_FIELD_REVIEW`, `VALIDATED`, `PENDING_PROCUREMENT`, `PENDING_BUDGET`, `PENDING_FINANCE_HEAD`, `APPROVED`, `DRAFTS_GENERATED`, `REWORK`, `BLOCKED`, `REJECTED`, and `NEEDS_MANUAL_REVIEW`. Next actions are `PROCEED_TO_APPROVAL`, `REQUEST_REWORK`, `MANUAL_REVIEW`, and `BLOCKED`.

Human field review is an explicit persistence step performed by a trusted reviewer; `resume_after_field_review` never confirms values itself. Human approvals remain mandatory and use configured stage owners and segregation of duties. Verification provenance labels `LOCAL_SIMULATED` versus `LIVE`; fake-live tests use a local `MockTransport` and do not contact a network service. Live provider failures are `UNAVAILABLE` and route to manual review, never a pass.

All account numbers in prompts and output are masked (last four only). Evidence quotes are retained, but sensitive account text is masked. Raw provider bodies are not stored unless `STORE_RAW_VERIFICATION_RESPONSES=true` is explicitly configured. Keep this false unless a reviewed retention policy requires otherwise.

## Invocation patterns (future adapters)

- **FastAPI route:** construct the facade in application lifespan, inject it into a thin route, validate request identifiers/decision models, serialize returned Pydantic models, and map domain errors to HTTP errors. The route must not implement business rules.
- **Supabase webhook or queue worker:** validate the signed event server-side, load the request ID, call `process_request`, and persist/emit only the service result. Use retries with request-level idempotency controls.
- **Scheduled job:** query eligible request IDs in a worker, invoke the facade per request, and record failures without bypassing manual review or approvals.

`SUPABASE_SERVICE_KEY` is server-side only and must never reach a browser. A frontend must never implement risk, approval, or verification logic; it consumes this backend contract.
