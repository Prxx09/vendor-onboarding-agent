"""Offline demonstration of stable verification contracts and provider swapping."""

import json

from app.integrations.http.generic import GenericHttpProvider
from app.integrations.http.testing import MockReply, mock_transport
from app.integrations.local.bank import LocalBankProvider
from app.integrations.local.registry import LocalRegistryProvider
from app.integrations.local.sanctions import LocalSanctionsProvider
from app.integrations.local.tax import LocalTaxProvider
from app.schemas.domain import SanctionsEntry

INPUTS = {
    "registration_number": "DEMO-IN-0001",
    "legal_name": "Example Vendor India Pvt Ltd",
    "country": "IN",
    "tax_id": "27AAPFU0939F1ZV",
    "account_number": "123456789012",
    "routing_code": "SYNB0123456",
    "account_holder_name": "Example Vendor India Pvt Ltd",
    "bank_name": "Synthetic National Bank",
    "currency": "INR",
}


def local_results():
    entries = [SanctionsEntry(name="Fictional Restricted Entity", list_name="demo-only")]
    return [
        LocalRegistryProvider().verify_company(INPUTS["registration_number"], INPUTS["legal_name"], INPUTS["country"]),
        LocalTaxProvider().verify_tax_id(INPUTS["tax_id"], INPUTS["country"], INPUTS["legal_name"]),
        LocalBankProvider().verify_account(
            INPUTS["account_number"], INPUTS["routing_code"], INPUTS["account_holder_name"],
            INPUTS["bank_name"], INPUTS["country"], INPUTS["currency"],
        ),
        LocalSanctionsProvider(entries).screen(INPUTS["legal_name"], [], INPUTS["country"]),
    ]


def http_results():
    endpoint = "https" + "://mock.invalid"
    capabilities = {}
    for key in ("company_registry", "tax_id", "bank_account", "sanctions"):
        capabilities[key] = {
            "provider_name": "fictional_mock_vendor",
            "base_url": endpoint,
            "method": "POST",
            "path": f"/{key}",
            "auth": {"type": "none"},
            "request_body_template": {},
            "status_field": "result",
            "status_mapping": {"clear": "VERIFIED", "mismatch": "MISMATCH", "missing": "NOT_FOUND"},
            "response_mapping": {"matches": "matches"} if key == "sanctions" else {},
        }
    def respond(request):
        return MockReply(payload={"result": "clear", "matches": []})

    adapter = GenericHttpProvider(
        {"capabilities": capabilities}, transport=mock_transport(respond)
    )
    return [
        adapter.verify_company(INPUTS["registration_number"], INPUTS["legal_name"], INPUTS["country"]),
        adapter.verify_tax_id(INPUTS["tax_id"], INPUTS["country"], INPUTS["legal_name"]),
        adapter.verify_account(
            INPUTS["account_number"], INPUTS["routing_code"], INPUTS["account_holder_name"],
            INPUTS["bank_name"], INPUTS["country"], INPUTS["currency"],
        ),
        adapter.screen(INPUTS["legal_name"], [], INPUTS["country"]),
    ]


def main():
    for label, results in (("local", local_results()), ("mock-http", http_results())):
        print(label)
        for result in results:
            print(json.dumps({
                "capability": result.capability,
                "provider": result.provider_name,
                "mode": result.mode.value,
                "status": result.status.value,
            }))


if __name__ == "__main__":
    main()
