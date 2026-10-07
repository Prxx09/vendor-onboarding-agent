# Vendor Onboarding Agent

Deterministic vendor onboarding workflow with LLM-assisted document extraction and explanations. The backend supports intake, extraction, verification, validation, risk, human approvals, vendor and PO drafts, reports, and append-only audit history. It does not submit to an ERP or call real external services in its demo/test paths.

## Architecture

```mermaid
flowchart TD
  F[Frontend (future)] --> C[Stable Backend Contract]
  C --> S[VendorOnboardingAgentService]
  S --> E[Extraction]
  S --> V[Verification]
  S --> VA[Validation]
  S --> R[Risk]
  S --> H[Human Review and Approvals]
  S --> D[Vendor and PO Drafts]
  S --> RP[Reports and Audit]
  E --> L[LLM: extraction and explanation only]
  VA --> Rules[Deterministic rules]
  R --> Rules
  H --> Rules
  V --> LP[Local simulated providers]
  V --> HP[Generic HTTP providers]
  S --> DB[(Supabase or in-memory repository)]
```

Deterministic Python rules own findings, risk, hard blocks, workflow status, and approval routing. LLM output is schema validated and limited to extraction or explanation.

## Setup and configuration

```powershell
pip install -e ".[dev]"
python -m pytest -q
ruff check .
```

The default `LLM_PROVIDER=mock` is offline; `LLM_PROVIDER=groq` requires `GROQ_API_KEY`. `REPOSITORY_BACKEND=memory` is process-local; `REPOSITORY_BACKEND=supabase` uses server-side `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Keep `.env` and `config/integrations.yaml` out of source control. See [Supabase setup](docs/supabase_setup.md).

Verification switches are `KYC_REGISTRY_PROVIDER`, `TAX_PROVIDER`, `BANK_PROVIDER`, and `SANCTIONS_PROVIDER` (`local`, `http`, or `off`). Local providers are `LOCAL_SIMULATED`. A configured generic provider emits `LIVE`; its result must still be surfaced with status and provider provenance. See [going live](docs/going_live.md).

## Demo cases and CLI

All case inputs and documents in `demo/cases/` are fictional.

```powershell
python -m app.cli list-cases
python -m app.cli run-case clean_supplier --approve-all
python -m app.cli run-case duplicate_tax_id
python -m app.cli run-case clean_supplier --verification-mode fake-live
python -m app.cli run-case clean_supplier --json
python -m app.cli reset-demo --repo memory
python scripts/generate_demo_pdfs.py
```

`run-case` options: `--provider mock|groq`, `--repo memory|supabase`, `--verification-mode local|fake-live`, `--approve-all`, `--json`. Fake-live uses `GenericHttpProvider` with in-process `httpx.MockTransport`; it makes no network calls. `--approve-all` records explicitly labeled synthetic demo reviewer/approver actions and still runs normal review and approval policy. It cannot approve hard-blocked requests. Supabase reset removes only `is_demo=true` requests with no audit history; synthetic rows with immutable audit history are preserved.

`VendorOnboardingAgentService` is the stable future integration surface. See the [integration contract](docs/integration_contract.md) for schema serialization, errors, idempotency, and invocation patterns. A future frontend must call this backend and must never implement risk, verification, or approval logic. The service-role key is server-side only.

## Safety guarantees

- Human review and all required approvals remain enforced; requester self-approval and duplicate approvers are rejected.
- Hard blocks prevent approval and draft generation. Provider failures route to manual review.
- Account numbers are masked in user-facing output; raw provider payload storage defaults to false.
- Evidence and verification provenance remain in reports and audit history; audit history is append-only.
- Local checks are visibly labeled simulated. Demo and test modes do not contact real providers.
