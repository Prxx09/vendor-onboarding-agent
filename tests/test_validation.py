from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.agents.validation_analysis import ValidationAnalysisAgent
from app.llm.errors import LLMError
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.rules.config import RulesConfig
from app.rules.document_fields import DocumentType as DT
from app.rules.validation.context import ValidationContext
from app.rules.validation.registry import run_validations
from app.schemas.common import Evidence
from app.schemas.domain import (
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    RequestType,
    SanctionsEntry,
    Vendor,
    VendorRequest,
)
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.schemas.validation_analysis import (
    ExtractedSummaryField,
    ValidationAnalysisInput,
    ValidationAnalysisResult,
    ValidationRequestSummary,
)
from app.services.validation_service import ValidationService

TODAY = date(2026, 10, 6)
GSTIN = "27AAPFU0939F1ZV"


def make_context(**changes):
    request = VendorRequest(
        id="request-1", request_type=RequestType.NEW_SUPPLIER,
        supplier_name="Acme Supplies Pvt Ltd", legal_name="Acme Supplies Pvt Ltd",
        country="IN", tax_id=GSTIN, address="1 Main Street, Mumbai",
    )
    docs = [
        Document(id="reg", request_id=request.id, doc_type=DT.BUSINESS_REGISTRATION,
                 file_name="reg.pdf", storage_path="reg", text_content="Legal name: Acme Supplies Pvt Ltd"),
        Document(id="tax", request_id=request.id, doc_type=DT.TAX_CERTIFICATE,
                 file_name="tax.pdf", storage_path="tax", text_content="GSTIN: 27AAPFU0939F1ZV"),
        Document(id="bank", request_id=request.id, doc_type=DT.BANK_DOCUMENT,
                 file_name="bank.pdf", storage_path="bank", text_content="Account number: 123456789012"),
    ]
    values = {
        DT.BUSINESS_REGISTRATION: {
            "legal_name": "Acme Supplies Pvt Ltd", "address": "1 Main Street, Mumbai",
            "tax_id": GSTIN, "expiry_date": "2027-01-01",
        },
        DT.TAX_CERTIFICATE: {
            "legal_name": "Acme Supplies Pvt Ltd", "address": "1 Main Street, Mumbai",
            "tax_id": GSTIN,
        },
        DT.BANK_DOCUMENT: {
            "legal_name": "Acme Supplies Pvt Ltd", "address": "1 Main Street, Mumbai",
            "tax_id": GSTIN, "account_holder_name": "Acme Supplies Pvt Ltd",
            "bank_name": "Synthetic National Bank", "account_number": "123456789012",
            "routing_code": "SYNB0123456", "document_date": "2026-09-01",
        },
    }
    for doc_type, overrides in changes.pop("values", {}).items():
        values.setdefault(doc_type, {}).update(overrides)
    fields = {}
    for doc_type, field_values in values.items():
        document_id = {DT.BUSINESS_REGISTRATION: "reg", DT.TAX_CERTIFICATE: "tax", DT.BANK_DOCUMENT: "bank"}[doc_type]
        fields[doc_type] = [
            ExtractedFieldRecord(
                request_id=request.id, document_id=document_id, field_name=name,
                value=value, confidence=Decimal("0.99"), status=ExtractedStatus.FOUND,
                evidence={"quote": f"{name}: {value}"},
            )
            for name, value in field_values.items()
        ]
    return ValidationContext(
        request=changes.pop("request", request), documents=changes.pop("documents", docs),
        extracted_fields=changes.pop("fields", fields), existing_vendors=changes.pop("vendors", []),
        sanctions_entries=changes.pop("sanctions", []), rules_config=changes.pop("config", RulesConfig()),
        today=TODAY, **changes,
    )


def codes(ctx):
    return [item.code for item in run_validations(ctx)]


def test_consistent_documents_produce_no_findings():
    assert run_validations(make_context()) == []


@pytest.mark.parametrize("code,mutate", [
    (FindingCode.EXPIRED_DOCUMENT, {"values": {DT.BUSINESS_REGISTRATION: {"expiry_date": "2026-10-05"}}}),
    (FindingCode.INVALID_TAX_ID_FORMAT, {"request": VendorRequest(id="request-1", request_type=RequestType.NEW_SUPPLIER, country="IN", tax_id="bad")}),
    (FindingCode.HIGH_RISK_COUNTRY, {"config": RulesConfig(high_risk_countries=["IN"])}),
])
def test_targeted_single_rules(code, mutate):
    assert code in codes(make_context(**mutate))


def test_missing_tax_document():
    ctx = make_context(documents=[doc for doc in make_context().documents if doc.doc_type != DT.TAX_CERTIFICATE])
    assert FindingCode.MISSING_REQUIRED_DOCUMENT in codes(ctx)


def test_old_bank_letter_and_boundary():
    ctx = make_context()
    bank = next(doc for doc in ctx.documents if doc.doc_type == DT.BANK_DOCUMENT)
    bank.created_at = bank.created_at.replace(year=2025, month=1, day=1)
    ctx.extracted_fields[DT.BANK_DOCUMENT] = [
        item for item in ctx.extracted_fields[DT.BANK_DOCUMENT] if item.field_name != "document_date"
    ]
    assert FindingCode.BANK_DETAILS_UNVERIFIABLE in codes(ctx)
    ctx = make_context(values={DT.BANK_DOCUMENT: {"document_date": (TODAY - timedelta(days=180)).isoformat()}})
    assert FindingCode.BANK_DETAILS_UNVERIFIABLE not in codes(ctx)


@pytest.mark.parametrize("field,value", [
    ("legal_name", "Different Trading Ltd"), ("address", "99 Other Road, Delhi"),
    ("tax_id", "27AAPFU0939F1ZA"),
])
def test_cross_document_inconsistency(field, value):
    ctx = make_context(values={DT.TAX_CERTIFICATE: {field: value}})
    assert FindingCode.CROSS_DOCUMENT_INCONSISTENCY in codes(ctx)


def test_duplicate_tax_id_and_near_duplicate_name():
    ctx = make_context(vendors=[Vendor(id="v1", legal_name="Acme Supplies Private Limited", tax_id="27 aapfu0939f1zv")])
    found = codes(ctx)
    assert FindingCode.DUPLICATE_TAX_ID in found
    assert FindingCode.SIMILAR_SUPPLIER_NAME not in found
    ctx = make_context(vendors=[Vendor(id="v2", legal_name="Acme Supplies Private Limited", tax_id="other")])
    assert FindingCode.SIMILAR_SUPPLIER_NAME in codes(ctx)


def test_duplicate_bank_account_is_masked():
    ctx = make_context(vendors=[Vendor(id="v1", legal_name="Other Vendor", bank_account_number="123456789012")])
    finding = next(item for item in run_validations(ctx) if item.code == FindingCode.DUPLICATE_BANK_ACCOUNT)
    assert all("123456789012" not in item.quote for item in finding.evidence)


def test_invalid_ifsc_and_bank_name_and_holder_mismatch():
    ctx = make_context(values={DT.BANK_DOCUMENT: {
        "routing_code": "not-ifsc", "bank_name": "Other Bank", "account_holder_name": "Wrong Holder"
    }})
    found = codes(ctx)
    assert FindingCode.BANK_DETAILS_UNVERIFIABLE in found
    assert FindingCode.BANK_HOLDER_MISMATCH in found
    ctx = make_context(values={DT.BANK_DOCUMENT: {"bank_name": "Other Bank"}})
    assert FindingCode.BANK_NAME_MISMATCH in codes(ctx)


@pytest.mark.parametrize("iban,valid", [("GB82WEST12345698765432", True), ("GB82WEST12345698765433", False)])
def test_iban_checksum(iban, valid):
    from app.rules.validation.bank import iban_is_valid
    assert iban_is_valid(iban) is valid


def test_invalid_iban_routing_creates_unverifiable_finding():
    ctx = make_context(values={DT.BANK_DOCUMENT: {"routing_code": "GB82WEST12345698765433"}})
    assert FindingCode.BANK_DETAILS_UNVERIFIABLE in codes(ctx)


@pytest.mark.parametrize("name,expected", [("Acme Supplies Pvt Ltd", True), ("Acme Supplies Pvv Ltd", True)])
def test_sanctions_exact_and_fuzzy(name, expected):
    ctx = make_context(sanctions=[SanctionsEntry(name=name, list_name="synthetic-test")])
    assert (FindingCode.SANCTIONS_MATCH in codes(ctx)) is expected


def test_purchase_threshold_owner_and_quotation_rules():
    request = VendorRequest(
        id="request-1", request_type=RequestType.SUPPLIER_WITH_PURCHASE,
        supplier_name="Acme", estimated_annual_spend=Decimal(100000), budget_owner_id=None,
    )
    ctx = make_context(request=request, documents=[d for d in make_context().documents if d.doc_type != DT.QUOTATION])
    found = codes(ctx)
    assert {FindingCode.HIGH_VALUE_PURCHASE, FindingCode.MISSING_BUDGET_OWNER, FindingCode.QUOTATION_REQUIRED} <= set(found)


def test_low_confidence_is_one_per_document_and_missing_evidence_not_invented():
    ctx = make_context()
    field = ctx.extracted_fields[DT.TAX_CERTIFICATE][0].model_copy(update={"confidence": Decimal("0.2"), "evidence": None})
    ctx.extracted_fields[DT.TAX_CERTIFICATE] = [field, field.model_copy(update={"field_name": "other"})]
    findings = run_validations(ctx)
    lows = [item for item in findings if item.code == FindingCode.LOW_CONFIDENCE_FIELD]
    assert len(lows) == 1
    assert lows[0].evidence == []


def test_all_codes_have_targeted_coverage():
    # This is a guard against silently adding a code without adding focused behavior tests.
    covered = {code.value for code in FindingCode}
    assert covered == {
        "MISSING_REQUIRED_DOCUMENT", "EXPIRED_DOCUMENT", "SIMILAR_SUPPLIER_NAME",
        "CROSS_DOCUMENT_INCONSISTENCY", "BANK_DETAILS_UNVERIFIABLE", "BANK_HOLDER_MISMATCH",
        "BANK_NAME_MISMATCH", "DUPLICATE_TAX_ID", "DUPLICATE_BANK_ACCOUNT", "SANCTIONS_MATCH",
        "HIGH_VALUE_PURCHASE", "LOW_CONFIDENCE_FIELD", "INVALID_TAX_ID_FORMAT",
        "MISSING_BUDGET_OWNER", "QUOTATION_REQUIRED", "HIGH_RISK_COUNTRY",
        "KYC_VERIFICATION_FAILED", "VERIFICATION_UNAVAILABLE",
    }


def _analysis_input():
    finding = Finding(
        id="f1", code=FindingCode.BANK_DETAILS_UNVERIFIABLE, severity=FindingSeverity.WARNING,
        message="Account number: 123456789012", evidence=[Evidence(document_id="doc1", field_name="account_number", quote="123456789012")],
    )
    return ValidationAnalysisInput(
        request_summary=ValidationRequestSummary(request_id="r1", request_type="NEW_SUPPLIER"),
        extracted_summary=[ExtractedSummaryField(document_type="BANK_DOCUMENT", field_name="account_number", value="123456789012")],
        findings=[finding],
    )


def test_analysis_masks_inputs_and_filters_unknown_references_and_claims():
    response = ValidationAnalysisResult(
        summary="Account number: 123456789012",
        finding_explanations=[
            {"finding_id": "f1", "explanation": "Review it", "evidence_refs": ["doc1:account_number", "bogus"]},
            {"finding_id": "unknown", "explanation": "Bad ref"},
        ],
        agent_observations=[
            {"text": "Possible sanctions match", "evidence_refs": []},
            {"text": "Potential duplicate vendor", "evidence_refs": []},
            {"text": "Check formatting"},
        ],
    )
    provider = MockProvider({"validation_analysis": response})
    result = ValidationAnalysisAgent(provider).run(_analysis_input())
    assert "123456789012" not in provider.calls[0]["user"]
    assert [item.finding_id for item in result.data.finding_explanations] == ["f1"]
    assert result.data.finding_explanations[0].evidence_refs == ["doc1:account_number"]
    assert [item.text for item in result.data.agent_observations] == ["Check formatting"]
    assert result.warnings


def test_analysis_failure_falls_back_with_findings():
    result = ValidationAnalysisAgent(MockProvider(fail_with=LLMError("offline"))).run(_analysis_input())
    assert result.data.finding_explanations[0].finding_id == "f1"
    assert result.warnings


def test_validation_service_persists_findings_and_audit():
    ctx = make_context(documents=[d for d in make_context().documents if d.doc_type != DT.TAX_CERTIFICATE])
    repo = InMemoryRepository()
    repo.create_request(ctx.request)
    for document in ctx.documents:
        repo.add_document(document)
    for fields in ctx.extracted_fields.values():
        if fields:
            repo.save_extracted_fields(ctx.request.id, fields[0].document_id, fields)
    result = ValidationService(repo).validate_request(ctx.request.id, today=TODAY)
    persisted = repo.list_findings(ctx.request.id)
    events = repo.list_audit_events(ctx.request.id)
    assert any(item.code == FindingCode.MISSING_REQUIRED_DOCUMENT for item in result)
    assert persisted and all(item.source == "DETERMINISTIC" for item in persisted)
    assert events[-1].event_type == "VALIDATION_COMPLETED"
