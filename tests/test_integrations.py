import os
from pathlib import Path

from app.integrations.bank import BankVerificationResult
from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.bundle import VerificationBundle
from app.integrations.circuit_breaker import CircuitBreaker
from app.integrations.factory import (
    VerificationRegistry,
    build_verification_registry,
    load_integrations_config,
)
from app.integrations.http.generic import GenericHttpProvider
from app.integrations.http.testing import MockReply, mock_transport
from app.integrations.local.bank import LocalBankProvider
from app.integrations.local.registry import LocalRegistryProvider
from app.integrations.local.sanctions import LocalSanctionsProvider
from app.integrations.local.tax import LocalTaxProvider
from app.integrations.registry import CompanyVerificationResult
from app.repositories.memory import InMemoryRepository
from app.rules.validation.context import ValidationContext
from app.rules.validation.external import validate_external
from app.schemas.domain import (
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    RequestType,
    ReviewStatus,
    SanctionsEntry,
    VendorRequest,
)
from app.schemas.findings import FindingCode
from app.services.validation_service import ValidationService
from app.services.verification_service import VerificationService


def _config(**overrides):
    capability = {
        "provider_name": "fictional_test_provider",
        "base_url": "https" + "://mock.invalid",
        "method": "POST",
        "path": "/verify",
        "timeout": 0.01,
        "retries": 1,
        "auth": {"type": "none"},
        "request_body_template": {"name": "{legal_name}"},
        "status_field": "state",
        "status_mapping": {"ok": "VERIFIED", "bad": "MISMATCH", "missing": "NOT_FOUND"},
        "response_mapping": {"registered_name": "company.name", "active": "company.active"},
    }
    capability.update(overrides)
    return {"capabilities": {"company_registry": capability}}


def test_local_provider_contract_statuses_and_simulated_mode():
    registry = LocalRegistryProvider()
    assert registry.verify_company("DEMO-IN-0001", "Example Vendor India Pvt Ltd", "IN").status == VerificationStatus.VERIFIED
    assert registry.verify_company("unknown", "Example", "IN").status == VerificationStatus.NOT_FOUND
    assert registry.verify_company("DEMO-IN-0001", "Other Company", "IN").status == VerificationStatus.MISMATCH
    tax = LocalTaxProvider()
    assert tax.verify_tax_id("27AAPFU0939F1ZV", "IN", "Example").status == VerificationStatus.VERIFIED
    assert tax.verify_tax_id("invalid", "IN", "Example").status == VerificationStatus.MISMATCH
    assert tax.verify_tax_id("x", "ZZ", "Example").status == VerificationStatus.NOT_CONFIGURED
    bank = LocalBankProvider()
    assert bank.lookup_routing_code("SYNB0123456").status == VerificationStatus.VERIFIED
    assert bank.lookup_routing_code("NOPE0123456").status == VerificationStatus.NOT_FOUND
    sanctions = LocalSanctionsProvider([SanctionsEntry(name="Example Restricted Trading Company", list_name="fixture")])
    assert sanctions.screen("Completely Clear Supplier", [], "IN").status == VerificationStatus.VERIFIED
    assert sanctions.screen("Example Restricted Trading Company", [], "IN").status == VerificationStatus.MISMATCH
    assert LocalSanctionsProvider([]).screen("Clear Name", [], "IN").status == VerificationStatus.NOT_CONFIGURED
    for result in (
        registry.verify_company("DEMO-IN-0001", "Example Vendor India Pvt Ltd", "IN"),
        tax.verify_tax_id("27AAPFU0939F1ZV", "IN", "Example"),
        bank.lookup_routing_code("SYNB0123456"),
        sanctions.screen("Clear Name", [], "IN"),
    ):
        assert result.mode == VerificationMode.LOCAL_SIMULATED


def test_factory_defaults_local_supports_off_and_loads_example_fallback(monkeypatch):
    for name in ("KYC_REGISTRY_PROVIDER", "TAX_PROVIDER", "BANK_PROVIDER", "SANCTIONS_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    missing_config = Path(__file__).with_name("missing-integrations-config.yaml")
    configured = build_verification_registry(config_path=missing_config)
    assert isinstance(configured.registry, LocalRegistryProvider)
    assert isinstance(configured.tax, LocalTaxProvider)
    assert isinstance(configured.bank, LocalBankProvider)
    monkeypatch.setenv("TAX_PROVIDER", "off")
    disabled = build_verification_registry(config_path=missing_config)
    assert disabled.tax.verify_tax_id("x", "IN", "fixture").status == VerificationStatus.NOT_CONFIGURED
    example = load_integrations_config(missing_config)
    assert {"company_registry", "tax_id", "bank_account", "sanctions"} <= set(example["capabilities"])


def test_http_verified_mapping_and_default_raw_response_discarded():
    seen = []

    def handler(request):
        seen.append(request)
        return MockReply(payload={"state": "ok", "company": {"name": "Mapped Corp", "active": True}, "secret_payload": "discard"})

    provider = GenericHttpProvider(_config(), transport=mock_transport(handler))
    result = provider.verify_company("R-1", "Legal", "IN")
    assert result.status == VerificationStatus.VERIFIED
    assert result.registered_name == "Mapped Corp" and result.active is True
    assert result.mode == VerificationMode.LIVE and result.details == {}
    assert seen[0].read()


def test_http_mismatch_not_found_mapping_and_malformed_payload():
    provider = GenericHttpProvider(_config(), transport=mock_transport(
        lambda request: MockReply(payload={"state": "bad"})
    ))
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.MISMATCH
    provider = GenericHttpProvider(_config(), transport=mock_transport(lambda request: MockReply(status=404)))
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.NOT_FOUND
    provider = GenericHttpProvider(_config(), transport=mock_transport(lambda request: MockReply(text="not json")))
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.UNAVAILABLE
    provider = GenericHttpProvider(_config(), transport=mock_transport(
        lambda request: MockReply(payload={"unexpected": "shape"})
    ))
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.UNAVAILABLE


def test_http_retries_server_error_and_rate_limit_then_unavailable():
    for code in (500, 429):
        attempts = []

        def handler(request, status_code=code, call_log=attempts):
            call_log.append(1)
            return MockReply(status=status_code)

        provider = GenericHttpProvider(_config(), transport=mock_transport(handler))
        result = provider.verify_company("R", "L", "IN")
        assert result.status == VerificationStatus.UNAVAILABLE
        assert len(attempts) == 2


def test_http_timeout_retries_then_unavailable_and_circuit_breaks():
    breaker = CircuitBreaker(failure_threshold=2)
    transport = mock_transport(lambda request: MockReply(exception="ReadTimeout"))
    provider = GenericHttpProvider(_config(), transport=transport, circuit_breaker=breaker)
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.UNAVAILABLE
    assert breaker.consecutive_failures == 1
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.UNAVAILABLE
    assert breaker.is_open
    assert provider.verify_company("R", "L", "IN").status == VerificationStatus.UNAVAILABLE


def test_missing_secret_is_not_configured_and_circuit_breaker_resets():
    old = os.environ.pop("MISSING_FAKE_TOKEN", None)
    try:
        cfg = _config(auth={"type": "bearer", "secret_env": "MISSING_FAKE_TOKEN"})
        provider = GenericHttpProvider(cfg, transport=mock_transport(lambda request: MockReply()))
        assert provider.verify_company("R", "L", "IN").status == VerificationStatus.NOT_CONFIGURED
    finally:
        if old is not None:
            os.environ["MISSING_FAKE_TOKEN"] = old
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure()
    breaker.record_success()
    assert not breaker.is_open and breaker.consecutive_failures == 0


def test_verification_service_uses_reviewed_values_persists_and_audits_without_account():
    repo = InMemoryRepository(sanctions_entries=[
        SanctionsEntry(name="Fictional Restricted Company", list_name="fixture-list")
    ])
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER, status="EXTRACTED",
        supplier_name="Example Vendor India Pvt Ltd", legal_name="Example Vendor India Pvt Ltd",
        country="IN", tax_id="27AAPFU0939F1ZV",
    ))
    inputs = {
        "BUSINESS_REGISTRATION": {"registration_number": "DEMO-IN-0001", "legal_name": "Example Vendor India Pvt Ltd"},
        "TAX_CERTIFICATE": {"tax_id": "27AAPFU0939F1ZV"},
        "BANK_DOCUMENT": {
            "account_number": "123456789012", "routing_code": "SYNB0123456",
            "account_holder_name": "Example Vendor India Pvt Ltd", "bank_name": "Synthetic National Bank",
            "currency": "INR",
        },
    }
    for doc_type, values in inputs.items():
        doc = repo.add_document(Document(
            request_id=request.id, doc_type=doc_type, file_name="fictional.pdf",
            storage_path="fictional", text_content="Account number: 123456789012",
        ))
        repo.save_extracted_fields(request.id, doc.id, [
            ExtractedFieldRecord(
                request_id=request.id, document_id=doc.id, field_name=name, value=value,
                status=ExtractedStatus.FOUND, confidence=0.99, review_status=ReviewStatus.CONFIRMED,
                evidence={"quote": f"{name}: {value}"},
            ) for name, value in values.items()
        ])
    provider_registry = VerificationRegistry(
        registry=LocalRegistryProvider(), tax=LocalTaxProvider(), bank=LocalBankProvider(),
        sanctions=LocalSanctionsProvider(),
    )
    bundle = VerificationService(repo, provider_registry).run_all(request.id)
    assert bundle.registry.status == VerificationStatus.VERIFIED
    assert bundle.tax.status == VerificationStatus.VERIFIED
    assert bundle.bank.status == VerificationStatus.VERIFIED
    assert bundle.sanctions.status == VerificationStatus.VERIFIED
    assert len(repo.list_verification_results(request.id)) == 4
    audit = repo.list_audit_events(request.id)
    assert len(audit) == 4
    serialized = str([event.details for event in audit])
    assert "123456789012" not in serialized
    assert all("input_hash" in event.details for event in audit)
    assert all(set(event.details) == {"provider", "capability", "status", "latency_ms", "input_hash"} for event in audit)


def test_external_rules_make_unavailable_non_pass_and_label_simulated_results():
    ctx = ValidationContext(
        request=VendorRequest(request_type=RequestType.NEW_SUPPLIER, legal_name="New Vendor"),
        extracted_fields={}, existing_vendors=[], sanctions_entries=[],
        verification=VerificationBundle(
            registry=CompanyVerificationResult(
                capability="company_registry", provider_name="mock", mode=VerificationMode.LIVE,
                status=VerificationStatus.UNAVAILABLE,
            ),
            bank=BankVerificationResult(
                capability="bank_account", provider_name="local", mode=VerificationMode.LOCAL_SIMULATED,
                status=VerificationStatus.NOT_FOUND, account_active=False,
            ),
        ),
    )
    findings = validate_external(ctx)
    assert FindingCode.VERIFICATION_UNAVAILABLE in {finding.code for finding in findings}
    assert FindingCode.KYC_VERIFICATION_FAILED not in {finding.code for finding in findings}
    bank = next(finding for finding in findings if finding.code == FindingCode.BANK_DETAILS_UNVERIFIABLE)
    assert "(simulated)" in bank.message
    assert bank.evidence[0].verification_mode == VerificationMode.LOCAL_SIMULATED.value


def test_verification_bundle_round_trip_drives_simulated_rules():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER, status="EXTRACTED",
        legal_name="Example Vendor India Pvt Ltd", country="IN", tax_id="27AAPFU0939F1ZV",
    ))
    for doc_type, values in {
        "BUSINESS_REGISTRATION": {"registration_number": "DEMO-IN-0001", "legal_name": "Example Vendor India Pvt Ltd"},
        "TAX_CERTIFICATE": {"tax_id": "27AAPFU0939F1ZV"},
        "BANK_DOCUMENT": {"account_number": "123456789012", "routing_code": "SYNB0123456",
                           "account_holder_name": "Example Vendor India Pvt Ltd", "bank_name": "Wrong Bank"},
    }.items():
        doc = repo.add_document(Document(
            request_id=request.id, doc_type=doc_type, file_name="fixture", storage_path="fixture"
        ))
        repo.save_extracted_fields(request.id, doc.id, [ExtractedFieldRecord(
            request_id=request.id, document_id=doc.id, field_name=name, value=value,
            status=ExtractedStatus.FOUND, confidence=1, review_status=ReviewStatus.CONFIRMED,
            evidence={"quote": f"{name}: {value}"},
        ) for name, value in values.items()])
    providers = VerificationRegistry(
        registry=LocalRegistryProvider(), tax=LocalTaxProvider(), bank=LocalBankProvider(),
        sanctions=LocalSanctionsProvider(),
    )
    VerificationService(repo, providers).run_all(request.id)
    findings = ValidationService(repo).validate_request(request.id)
    bank_finding = next(item for item in findings if item.code == FindingCode.BANK_NAME_MISMATCH)
    assert "(simulated)" in bank_finding.message
    assert any(item.verification_mode == VerificationMode.LOCAL_SIMULATED.value for item in bank_finding.evidence)


def test_unavailable_provider_routes_request_to_manual_review():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER, status="DRAFT", legal_name="Fictional Company", country="IN",
    ))
    doc = repo.add_document(Document(
        request_id=request.id, doc_type="BUSINESS_REGISTRATION", file_name="fixture", storage_path="fixture"
    ))
    repo.save_extracted_fields(request.id, doc.id, [
        ExtractedFieldRecord(
            request_id=request.id, document_id=doc.id, field_name=field_name, value=value,
            status=ExtractedStatus.FOUND, confidence=1, review_status=ReviewStatus.CONFIRMED,
            evidence={"quote": value},
        ) for field_name, value in {
            "registration_number": "DEMO-IN-0001", "legal_name": "Fictional Company",
        }.items()
    ])

    class UnavailableRegistry:
        def verify_company(self, registration_number, legal_name, country):
            return CompanyVerificationResult(
                capability="company_registry", provider_name="fixture_http", mode=VerificationMode.LIVE,
                status=VerificationStatus.UNAVAILABLE, error="timeout",
            )

    providers = VerificationRegistry(
        registry=UnavailableRegistry(), tax=LocalTaxProvider(), bank=LocalBankProvider(),
        sanctions=LocalSanctionsProvider(),
    )
    results = VerificationService(repo, providers).run_all(request.id)
    assert results.registry.status == VerificationStatus.UNAVAILABLE
    assert repo.get_request(request.id).status == "NEEDS_MANUAL_REVIEW"
    assert len(repo.list_verification_results(request.id)) == 4

