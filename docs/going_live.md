# Going live with external verification

The project currently defaults to fictional local simulations. A verification result always carries its mode; callers should surface `LOCAL_SIMULATED` clearly so it cannot be mistaken for a government, bank, or sanctions-list check.

## Capability configuration

| Capability | Provider switch | Config section | What an approved provider supplies | What stays unchanged |
|---|---|---|---|---|
| Company registry / KYC | `KYC_REGISTRY_PROVIDER=http` | `capabilities.company_registry` | Registration lookup, active state, registered name, and normalized evidence/reference | Validation rules, risk, orchestration, approval policy, drafts, facade |
| Tax ID | `TAX_PROVIDER=http` | `capabilities.tax_id` | Tax identifier status and normalized registered-name fields | Same deterministic rule and service contracts |
| Bank verification | `BANK_PROVIDER=http` | `capabilities.bank_account`, `capabilities.bank_routing` | Account and routing result fields over an approved secure channel | Same bank validation, risk, review, and draft logic |
| Sanctions | `SANCTIONS_PROVIDER=http` | `capabilities.sanctions` | Screening disposition and normalized match records | Same hard-block rules and human approval workflow |

The intended change is `configuration + provider switch + an adapter under app/integrations/ if necessary`. No changes are needed to rules, agents, orchestrator, approval policy, draft generation, or facade.

## Configuration-only migration

1. Obtain an approved endpoint, request contract, response contract, rate limits, and data-processing terms for each capability.
2. Set `KYC_REGISTRY_PROVIDER`, `TAX_PROVIDER`, `BANK_PROVIDER`, or `SANCTIONS_PROVIDER` to `http` only for the approved provider. The default is `local`; `off` records a `NOT_CONFIGURED` result.
3. Copy `config/integrations.example.yaml` to the ignored `config/integrations.yaml`. Configure capability base URLs, method, path, request templates, normalized response mappings, status mappings, timeout, retries, and auth type.
4. Put only secret environment-variable names in YAML. Store actual credentials in the deployment secret manager and set those environment variables. Never commit `config/integrations.yaml` or `.env`.
5. Run `python scripts/run_verification_demo.py` for the offline contract demonstration, then validate the provider against a vendor-approved sandbox using `MockTransport`-style contract tests before switching production configuration.

The HTTP adapter maps provider payloads to normalized result fields. It retries only timeouts, HTTP 5xx, and 429 responses. Exhausted failures become `UNAVAILABLE`; they cannot be treated as a pass and are routed to manual review. The `LIVE` label means an external adapter was selected; it does not itself imply a real provider has been configured or contacted.

## Data protection

Transmit only fields required for the requested capability and only after a human has reviewed the values. Account numbers are sent only to a configured bank provider when reviewed values are available. They are never included in audit details: audit events contain only a SHA-256 input hash, provider, capability, status, mode, and latency. Application code does not log request bodies or raw response bodies. Raw provider responses are discarded by default; `STORE_RAW_VERIFICATION_RESPONSES=true` is an explicit opt-in and should be enabled only after retention, access, and legal review. Persisted verification details are normalized fields, except that opt-in raw-response storage may retain provider data.

Use least-privilege credentials, TLS endpoints, short timeouts, restricted server access, and provider-specific retention policies. `SUPABASE_SERVICE_KEY` and provider credentials are server-side only and must never be exposed to a frontend. Audit events remain append-only. `LOCAL_SIMULATED` identifies fictional local checks; `LIVE` identifies configured adapter provenance, and provider failure remains `UNAVAILABLE`. The sample endpoints and response mappings are fictional and are not usable integrations.
