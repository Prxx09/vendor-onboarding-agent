import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.integrations.bank import (
    BankVerificationProvider,
    BankVerificationResult,
    RoutingLookupResult,
)
from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.circuit_breaker import CircuitBreaker
from app.integrations.http.generic import GenericHttpProvider
from app.integrations.local.bank import LocalBankProvider
from app.integrations.local.registry import LocalRegistryProvider
from app.integrations.local.sanctions import LocalSanctionsProvider
from app.integrations.local.tax import LocalTaxProvider
from app.integrations.registry import BusinessRegistryProvider, CompanyVerificationResult
from app.integrations.sanctions import SanctionsResult, SanctionsScreeningProvider
from app.integrations.tax import TaxIdVerificationProvider, TaxVerificationResult
from app.schemas.domain import SanctionsEntry


@dataclass
class VerificationRegistry:
    registry: BusinessRegistryProvider
    tax: TaxIdVerificationProvider
    bank: BankVerificationProvider
    sanctions: SanctionsScreeningProvider


class _OffProvider:
    provider_name = "off"

    @staticmethod
    def _base(capability, result_type):
        return result_type(
            capability=capability, provider_name="off", mode=VerificationMode.LOCAL_SIMULATED,
            status=VerificationStatus.NOT_CONFIGURED, error="Provider is disabled.",
        )

    def verify_company(self, registration_number, legal_name, country):
        return self._base("company_registry", CompanyVerificationResult)

    def verify_tax_id(self, tax_id, country, legal_name):
        return self._base("tax_id", TaxVerificationResult)

    def verify_account(self, account_number, routing_code, account_holder_name, bank_name, country, currency):
        return self._base("bank_account", BankVerificationResult)

    def lookup_routing_code(self, routing_code):
        return self._base("bank_routing", RoutingLookupResult)

    def screen(self, name, aliases, country):
        return self._base("sanctions", SanctionsResult)


def load_integrations_config(path: str | Path | None = None) -> dict[str, Any]:
    configured = Path(path or os.getenv("INTEGRATIONS_CONFIG_PATH", "config/integrations.yaml"))
    if not configured.exists():
        configured = Path("config/integrations.example.yaml")
    if not configured.exists():
        return {"capabilities": {}}
    with configured.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"capabilities": {}}


def build_verification_registry(*, sanctions_entries: list[SanctionsEntry] | None = None,
                                config_path: str | Path | None = None,
                                transport=None) -> VerificationRegistry:
    config = load_integrations_config(config_path)
    http = GenericHttpProvider(
        config, transport=transport,
        store_raw=os.getenv("STORE_RAW_VERIFICATION_RESPONSES", "false").casefold() == "true",
        circuit_breaker={name: CircuitBreaker(failure_threshold=3) for name in (
            "company_registry", "tax_id", "bank_account", "bank_routing", "sanctions"
        )},
    )

    def selected(variable: str, capability: str, local, off):
        choice = os.getenv(variable, "local").casefold()
        if choice == "local":
            return local
        if choice == "http":
            return http
        if choice == "off":
            return off
        raise ValueError(f"Invalid {variable}: expected local, http or off")

    off = _OffProvider()
    return VerificationRegistry(
        registry=selected("KYC_REGISTRY_PROVIDER", "company_registry", LocalRegistryProvider(), off),
        tax=selected("TAX_PROVIDER", "tax_id", LocalTaxProvider(), off),
        bank=selected("BANK_PROVIDER", "bank_account", LocalBankProvider(), off),
        sanctions=selected("SANCTIONS_PROVIDER", "sanctions", LocalSanctionsProvider(sanctions_entries), off),
    )
