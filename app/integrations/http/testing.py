"""Small MockTransport fixture helpers; importing httpx stays inside integrations."""

from collections.abc import Callable
from typing import Any

import httpx


class MockReply:
    def __init__(self, status: int = 200, payload: Any = None, text: str | None = None,
                 exception: str | None = None):
        self.status = status
        self.payload = payload
        self.text = text
        self.exception = exception


def mock_transport(handler: Callable[[httpx.Request], MockReply]) -> httpx.MockTransport:
    exceptions = {
        "ReadTimeout": httpx.ReadTimeout,
        "ConnectTimeout": httpx.ConnectTimeout,
        "ConnectError": httpx.ConnectError,
    }

    def dispatch(request):
        reply = handler(request)
        if reply.exception:
            error_type = exceptions[reply.exception]
            raise error_type("fictional transport failure", request=request)
        if reply.text is not None:
            return httpx.Response(reply.status, text=reply.text)
        return httpx.Response(reply.status, json=reply.payload or {})

    return httpx.MockTransport(dispatch)


def fake_live_registry(sanctions_entries=None, *, unavailable: str | None = None):
    """Build four GenericHttpProvider adapters whose HTTP is handled in-process."""
    import json

    from app.integrations.factory import VerificationRegistry
    from app.integrations.http.generic import GenericHttpProvider
    from app.integrations.local.bank import LocalBankProvider
    from app.integrations.local.registry import LocalRegistryProvider
    from app.integrations.local.sanctions import LocalSanctionsProvider
    from app.integrations.local.tax import LocalTaxProvider

    def handle(request):
        capability = request.url.path.strip("/").split("/")[0]
        if unavailable == capability:
            return MockReply(status=503)
        values = json.loads(request.content or b"{}")
        local = {
            "company_registry": lambda: LocalRegistryProvider().verify_company(
                values["registration_number"], values["legal_name"], values["country"]),
            "tax_id": lambda: LocalTaxProvider().verify_tax_id(
                values["tax_id"], values["country"], values["legal_name"]),
            "bank_account": lambda: LocalBankProvider().verify_account(
                values["account_number"], values["routing_code"], values["account_holder_name"],
                values.get("bank_name"), values["country"], values.get("currency")),
            "bank_routing": lambda: LocalBankProvider().lookup_routing_code(values["routing_code"]),
            "sanctions": lambda: LocalSanctionsProvider(sanctions_entries or None).screen(
                values["name"], values.get("aliases", []), values["country"]),
        }[capability]()
        body = {key: value for key, value in local.model_dump(mode="json").items()
                if key not in {"capability", "provider_name", "mode", "status", "checked_at",
                               "reference_id", "latency_ms", "error", "details"}}
        return MockReply(payload={"result": local.status.value.casefold(), **body})

    capabilities = {}
    for name in ("company_registry", "tax_id", "bank_account", "bank_routing", "sanctions"):
        capabilities[name] = {
            "provider_name": "fake_live_" + name, "base_url": "http://fake-live.invalid",
            "method": "POST", "path": name,
            "request_body_template": {"_payload": "{unused}"},
            "auth": {"type": "none"}, "status_field": "result",
            "status_mapping": {value.casefold(): value for value in
                               ("VERIFIED", "MISMATCH", "NOT_FOUND", "UNAVAILABLE", "NOT_CONFIGURED")},
            "response_mapping": {},
        }
    # Generic provider must transmit the same typed values as the local adapters.
    for cap, fields in {
        "company_registry": ("registration_number", "legal_name", "country"),
        "tax_id": ("tax_id", "country", "legal_name"),
        "bank_account": ("account_number", "routing_code", "account_holder_name", "bank_name", "country", "currency"),
        "bank_routing": ("routing_code",),
        "sanctions": ("name", "aliases", "country"),
    }.items():
        capabilities[cap]["request_body_template"] = {key: "{" + key + "}" for key in fields}
        capabilities[cap]["response_mapping"] = {
            key: key for key in ({
                "company_registry": ("registered_name", "active", "incorporation_date", "registered_address", "name_match_score"),
                "tax_id": ("registered_legal_name", "tax_status", "registered_address", "name_match_score"),
                "bank_account": ("account_active", "resolved_bank_name", "holder_name_match_score"),
                "bank_routing": ("resolved_bank_name",), "sanctions": ("matches",),
            }[cap])
        }
    generic = GenericHttpProvider(capabilities, transport=mock_transport(handle), store_raw=False)
    return VerificationRegistry(generic, generic, generic, generic)


def local_demo_registry(sanctions_entries=None, *, unavailable: str | None = None):
    """Local simulation registry, optionally failing one capability for a demo case."""
    from app.integrations.bank import BankVerificationResult
    from app.integrations.base import VerificationMode, VerificationStatus
    from app.integrations.factory import VerificationRegistry
    from app.integrations.local.bank import LocalBankProvider
    from app.integrations.local.registry import LocalRegistryProvider
    from app.integrations.local.sanctions import LocalSanctionsProvider
    from app.integrations.local.tax import LocalTaxProvider

    class BankAdapter(LocalBankProvider):
        def verify_account(self, *args, **kwargs):
            if unavailable == "bank_account":
                return BankVerificationResult(
                    capability="bank_account", provider_name="fictional_unavailable_demo",
                    mode=VerificationMode.LOCAL_SIMULATED, status=VerificationStatus.UNAVAILABLE,
                    error="Synthetic demo outage.",
                )
            return super().verify_account(*args, **kwargs)

    return VerificationRegistry(
        LocalRegistryProvider(), LocalTaxProvider(), BankAdapter(),
        LocalSanctionsProvider(sanctions_entries or None),
    )
