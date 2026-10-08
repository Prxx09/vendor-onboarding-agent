import asyncio
from datetime import date
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from rapidfuzz.fuzz import token_set_ratio

from app.domain.models import (
    AgentEvent,
    DocumentExtraction,
    ScorecardItem,
    VendorProcessResult,
    VerificationEvidence,
)
from app.providers.base import VerificationProvider
from app.repositories.vendor_repository import VendorRepository
from app.services.document_processor import DocumentProcessor
from app.services.groq_extractor import GroqDocumentExtractor


class AgentState(TypedDict, total=False):
    vendor_id: str
    submitted_legal_name: str
    submitted_data: dict[str, Any]
    files: list[dict]
    extractions: list[DocumentExtraction]
    existing_extractions: list[DocumentExtraction]
    new_extractions: list[DocumentExtraction]
    missing_documents: list[str]
    checks: list[VerificationEvidence]
    reasons: list[str]
    events: list[AgentEvent]
    overall_status: str
    recommendation: str


REQUIRED_DOCUMENTS = {
    "business_registration": "Business Registration",
    "tax_certificate": "Tax Certificate",
    "bank_proof": "Bank Proof",
}

EXTRACTABLE_INTAKE_FIELDS = [
    "legal_name",
    "tax_id",
    "pan",
    "bank_account",
    "ifsc",
    "registered_address",
    "contact_name",
    "contact_email",
    "contact_phone",
    "categories",
]

EXTRACTION_FIELD_MAP = {
    "legal_name": "legal_name",
    "tax_id": "tax_id",
    "pan": "pan",
    "bank_account": "bank_account_number",
    "ifsc": "ifsc_swift",
    "registered_address": "registered_address",
    "contact_name": "contact_name",
    "contact_email": "contact_email",
    "contact_phone": "contact_phone",
    "categories": "vendor_category",
}

CHECK_SCORES = {
    "VERIFIED": 100.0,
    "REVIEW_REQUIRED": 50.0,
    "MISMATCH": 0.0,
    "NOT_FOUND": 0.0,
    "ERROR": 0.0,
}


def _name_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return token_set_ratio(a.lower(), b.lower()) / 100.0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _extraction_coverage_score(extractions: list[DocumentExtraction]) -> float:
    extracted: set[str] = set()
    for item in extractions:
        for intake_field, extraction_field in EXTRACTION_FIELD_MAP.items():
            value = getattr(item, extraction_field, None)
            if value is not None and str(value).strip():
                extracted.add(intake_field)
    if not EXTRACTABLE_INTAKE_FIELDS:
        return 0.0
    return round(len(extracted) / len(EXTRACTABLE_INTAKE_FIELDS) * 100.0, 1)


class VendorVerificationAgent:
    def __init__(
        self,
        document_processor: DocumentProcessor,
        extractor: GroqDocumentExtractor,
        provider: VerificationProvider,
        repository: VendorRepository,
    ) -> None:
        self.document_processor = document_processor
        self.extractor = extractor
        self.provider = provider
        self.repository = repository
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("extract_documents", self._extract_documents)
        graph.add_node("check_completeness", self._check_completeness)
        graph.add_node("verify_external", self._verify_external)
        graph.add_node("cross_validate", self._cross_validate)
        graph.add_node("decide", self._decide)
        graph.add_node("persist", self._persist)

        graph.add_edge(START, "extract_documents")
        graph.add_edge("extract_documents", "check_completeness")
        graph.add_conditional_edges(
            "check_completeness",
            self._route_after_completeness,
            {
                "missing": "persist",
                "complete": "verify_external",
            },
        )
        graph.add_edge("verify_external", "cross_validate")
        graph.add_edge("cross_validate", "decide")
        graph.add_edge("decide", "persist")
        graph.add_edge("persist", END)
        return graph.compile()

    async def run(
        self,
        legal_name: str,
        files: list[dict],
        vendor_id: str | None = None,
        existing_extractions: list[DocumentExtraction] | None = None,
        submitted_data: dict[str, Any] | None = None,
    ) -> VendorProcessResult:
        previous = list(existing_extractions or [])
        intake_data = dict(submitted_data or {})
        if legal_name.strip():
            intake_data["legal_name"] = legal_name.strip()

        is_resume = vendor_id is not None
        intake_message = (
            f"Resumed vendor with {len(previous)} existing document(s) and "
            f"received {len(files)} new document(s)."
            if is_resume
            else f"Received {len(files)} document(s)."
        )
        initial: AgentState = {
            "vendor_id": vendor_id or str(uuid4()),
            "submitted_legal_name": legal_name.strip(),
            "submitted_data": intake_data,
            "files": files,
            "existing_extractions": previous,
            "events": [
                AgentEvent(
                    step="intake",
                    message=intake_message,
                )
            ],
        }
        state = await self.graph.ainvoke(initial)
        confidence_score, scorecard = self._score_state(state)
        return VendorProcessResult(
            vendor_id=state["vendor_id"],
            vendor_name=self._vendor_name(state),
            overall_status=state["overall_status"],
            recommendation=state["recommendation"],
            missing_documents=state.get("missing_documents", []),
            extractions=state.get("extractions", []),
            checks=state.get("checks", []),
            reasons=state.get("reasons", []),
            events=state.get("events", []),
            confidence_score=confidence_score,
            scorecard=scorecard,
            submitted_data=state.get("submitted_data", {}),
        )

    async def _extract_documents(self, state: AgentState) -> dict:
        async def extract_one(item: dict):
            document_text = await self.document_processor.extract_text(
                filename=item["filename"],
                mime_type=item["mime_type"],
                content=item["content"],
            )
            structured = await self.extractor.extract(
                filename=item["filename"],
                raw_text=document_text.text,
            )
            return structured, document_text

        results = await asyncio.gather(
            *(extract_one(item) for item in state["files"]),
            return_exceptions=True,
        )

        new_extractions: list[DocumentExtraction] = []
        events = list(state.get("events", []))
        reasons = list(state.get("reasons", []))

        for file_item, result in zip(state["files"], results):
            if isinstance(result, Exception):
                reasons.append(f"Could not read {file_item['filename']}: {result}")
                events.append(
                    AgentEvent(
                        step="document_extraction",
                        message=f"Extraction failed for {file_item['filename']}: {result}",
                    )
                )
                continue

            structured, document_text = result
            new_extractions.append(structured)
            events.append(
                AgentEvent(
                    step="document_extraction",
                    message=(
                        f"{structured.filename}: text extracted via "
                        f"{document_text.method} across {document_text.page_count} page(s); "
                        f"classified as {structured.document_type}."
                    ),
                )
            )

        return {
            "extractions": [
                *state.get("existing_extractions", []),
                *new_extractions,
            ],
            "new_extractions": new_extractions,
            "events": events,
            "reasons": reasons,
        }

    async def _check_completeness(self, state: AgentState) -> dict:
        present = {item.document_type for item in state.get("extractions", [])}
        missing = [
            label
            for doc_type, label in REQUIRED_DOCUMENTS.items()
            if doc_type not in present
        ]

        events = list(state.get("events", []))
        if missing:
            events.append(
                AgentEvent(
                    step="completeness",
                    message=f"Missing required documents: {', '.join(missing)}.",
                )
            )
            reasons = list(state.get("reasons", []))
            reasons.append(f"Missing required documents: {', '.join(missing)}")
            return {
                "missing_documents": missing,
                "overall_status": "ACTION_REQUIRED",
                "recommendation": "WAIT_FOR_DOCUMENTS",
                "reasons": reasons,
                "events": events,
            }

        events.append(
            AgentEvent(
                step="completeness",
                message="All required document categories are present.",
            )
        )
        return {"missing_documents": [], "events": events}

    def _route_after_completeness(self, state: AgentState) -> str:
        return "missing" if state.get("missing_documents") else "complete"

    def _vendor_name(self, state: AgentState) -> str:
        submitted = state.get("submitted_data", {})
        if submitted.get("legal_name"):
            return str(submitted["legal_name"])
        if state.get("submitted_legal_name"):
            return state["submitted_legal_name"]

        names = [
            item.legal_name
            for item in state.get("extractions", [])
            if item.legal_name
        ]
        return names[0] if names else "Unknown Vendor"

    def _doc(self, state: AgentState, doc_type: str) -> DocumentExtraction | None:
        return next(
            (
                item
                for item in reversed(state.get("extractions", []))
                if item.document_type == doc_type
            ),
            None,
        )

    async def _verify_external(self, state: AgentState) -> dict:
        company = self._doc(state, "business_registration")
        tax = self._doc(state, "tax_certificate")
        bank = self._doc(state, "bank_proof")
        submitted = state.get("submitted_data", {})
        vendor_name = self._vendor_name(state)

        tax_id = submitted.get("tax_id") or (tax.tax_id if tax else None)
        bank_account = submitted.get("bank_account") or (
            bank.bank_account_number if bank else None
        )
        bank_ifsc = submitted.get("ifsc") or (bank.ifsc_swift if bank else None)

        checks: list[VerificationEvidence] = []
        tasks = []

        if company and company.registration_number:
            tasks.append(self.provider.verify_company(company.registration_number))
        else:
            checks.append(
                VerificationEvidence(
                    source="company_registry",
                    status="NOT_FOUND",
                    message="Registration number could not be extracted.",
                )
            )

        if tax_id:
            tasks.append(self.provider.verify_tax(str(tax_id)))
            tasks.append(self.provider.check_duplicate_tax_id(str(tax_id)))
        else:
            checks.append(
                VerificationEvidence(
                    source="tax_registry",
                    status="NOT_FOUND",
                    message="Tax ID could not be extracted or submitted.",
                )
            )

        if bank_account:
            tasks.append(
                self.provider.verify_bank(
                    str(bank_account),
                    str(bank_ifsc) if bank_ifsc else None,
                    vendor_name,
                )
            )
        else:
            checks.append(
                VerificationEvidence(
                    source="bank_account_registry",
                    status="NOT_FOUND",
                    message="Bank account number could not be extracted or submitted.",
                )
            )

        tasks.append(
            self.provider.verify_kyc(
                vendor_name,
                company.registration_number if company else None,
                str(tax_id) if tax_id else None,
            )
        )
        tasks.append(self.provider.check_sanctions(vendor_name))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    checks.append(
                        VerificationEvidence(
                            source="verification_provider",
                            status="ERROR",
                            message=f"Verification provider error: {result}",
                        )
                    )
                else:
                    checks.append(result)

        events = list(state.get("events", []))
        events.append(
            AgentEvent(
                step="external_verification",
                message=f"Completed {len(checks)} registry/KYC/bank checks.",
            )
        )
        return {"checks": checks, "events": events}

    async def _cross_validate(self, state: AgentState) -> dict:
        checks = list(state.get("checks", []))
        extractions = state.get("extractions", [])
        submitted = state.get("submitted_data", {})
        vendor_name = self._vendor_name(state)

        for item in extractions:
            candidate_name = item.legal_name or item.account_holder_name
            if candidate_name:
                score = _name_score(vendor_name, candidate_name)
                if score < 0.80:
                    checks.append(
                        VerificationEvidence(
                            source=f"cross_document:{item.filename}",
                            status="MISMATCH",
                            message=(
                                f"Name on {item.filename} does not sufficiently match "
                                f"the vendor legal name ({score:.0%})."
                            ),
                            data={
                                "vendor_name": vendor_name,
                                "document_name": candidate_name,
                                "name_match_score": score,
                            },
                        )
                    )

        tax = self._doc(state, "tax_certificate")
        bank = self._doc(state, "bank_proof")
        submitted_pairs = [
            ("tax_id", submitted.get("tax_id"), tax.tax_id if tax else None, "tax certificate"),
            (
                "bank_account",
                submitted.get("bank_account"),
                bank.bank_account_number if bank else None,
                "bank proof",
            ),
            ("ifsc", submitted.get("ifsc"), bank.ifsc_swift if bank else None, "bank proof"),
        ]
        for field, submitted_value, document_value, source_label in submitted_pairs:
            if submitted_value and document_value and str(submitted_value).strip() != str(document_value).strip():
                checks.append(
                    VerificationEvidence(
                        source=f"submitted_vs_document:{field}",
                        status="MISMATCH",
                        message=(
                            f"Submitted {field.replace('_', ' ')} does not match the "
                            f"value extracted from the {source_label}."
                        ),
                        data={
                            "submitted_value": submitted_value,
                            "document_value": document_value,
                        },
                    )
                )

        tax_registry_check = next(
            (
                check
                for check in checks
                if check.source == "tax_registry" and isinstance(check.data, dict)
            ),
            None,
        )
        if tax_registry_check:
            registry_data = tax_registry_check.data or {}
            registry_pan = registry_data.get("pan")
            submitted_pan = submitted.get("pan") or (tax.pan if tax else None)
            if (
                registry_pan
                and submitted_pan
                and str(registry_pan).strip().upper()
                != str(submitted_pan).strip().upper()
            ):
                checks.append(
                    VerificationEvidence(
                        source="tax_registry:pan",
                        status="MISMATCH",
                        message="Tax registry PAN does not match the submitted/vendor document PAN.",
                        data={
                            "submitted_pan": submitted_pan,
                            "registry_pan": registry_pan,
                        },
                    )
                )

            registry_name = registry_data.get("legal_name")
            if registry_name:
                registry_name_score = _name_score(vendor_name, registry_name)
                if registry_name_score < 0.80:
                    checks.append(
                        VerificationEvidence(
                            source="tax_registry:legal_name",
                            status="MISMATCH",
                            message=(
                                "Tax ID is registered to a different legal entity "
                                f"(name similarity {registry_name_score:.0%})."
                            ),
                            data={
                                "vendor_name": vendor_name,
                                "registry_legal_name": registry_name,
                                "name_match_score": registry_name_score,
                            },
                        )
                    )

            registry_registration = registry_data.get("registration_number")
            company_registration = company.registration_number if company else None
            if (
                registry_registration
                and company_registration
                and str(registry_registration).strip()
                != str(company_registration).strip()
            ):
                checks.append(
                    VerificationEvidence(
                        source="tax_registry:registration_number",
                        status="MISMATCH",
                        message=(
                            "Tax ID is linked to a different business registration number."
                        ),
                        data={
                            "company_registration_number": company_registration,
                            "tax_registry_registration_number": registry_registration,
                        },
                    )
                )

        if submitted.get("compliance_confirmed") is False:
            checks.append(
                VerificationEvidence(
                    source="compliance_confirmation",
                    status="REVIEW_REQUIRED",
                    message="Vendor compliance was not confirmed on the submitted intake form.",
                )
            )
        elif submitted.get("compliance_confirmed") is True:
            checks.append(
                VerificationEvidence(
                    source="compliance_confirmation",
                    status="VERIFIED",
                    message="Vendor compliance confirmation was provided.",
                )
            )

        if company:
            expiry = _parse_date(company.expiry_date)
            if expiry and expiry < date.today():
                checks.append(
                    VerificationEvidence(
                        source="business_registration_expiry",
                        status="REVIEW_REQUIRED",
                        message=f"Business registration expired on {expiry.isoformat()}.",
                        data={"expiry_date": expiry.isoformat()},
                    )
                )

        events = list(state.get("events", []))
        events.append(
            AgentEvent(
                step="cross_document_validation",
                message="Cross-document and submitted-data consistency checks completed.",
            )
        )
        return {"checks": checks, "events": events}

    def _score_state(self, state: AgentState) -> tuple[float | None, list[ScorecardItem]]:
        scorecard: list[ScorecardItem] = []

        extractions = state.get("extractions", [])
        if extractions:
            extraction_score = _extraction_coverage_score(extractions)
            extracted_count = round(
                extraction_score / 100.0 * len(EXTRACTABLE_INTAKE_FIELDS)
            )
            scorecard.append(
                ScorecardItem(
                    name="Document extraction completeness",
                    score=extraction_score,
                    status="PASS" if extraction_score >= 80 else "REVIEW",
                    message=(
                        f"{extracted_count} of {len(EXTRACTABLE_INTAKE_FIELDS)} "
                        "extractable intake fields were populated from the submitted documents."
                    ),
                )
            )

        for check in state.get("checks", []):
            score = CHECK_SCORES.get(check.status, 0.0)
            status = "PASS" if check.status == "VERIFIED" else (
                "REVIEW" if check.status == "REVIEW_REQUIRED" else "FAIL"
            )
            scorecard.append(
                ScorecardItem(
                    name=check.source.replace("_", " ").replace(":", " / "),
                    score=score,
                    status=status,
                    message=check.message,
                )
            )

        if not scorecard:
            return None, []

        overall = sum(item.score for item in scorecard) / len(scorecard)

        integrity_issue = any(
            check.status == "MISMATCH"
            or (
                check.status == "REVIEW_REQUIRED"
                and check.source in {"vendor_master", "vendor_master_snapshot"}
            )
            for check in state.get("checks", [])
        )
        if integrity_issue:
            # Duplicate identities and registry/document mismatches are hard
            # verification exceptions. They must never appear as a high-
            # confidence auto-approval candidate.
            overall = min(overall, 60.0)

        return round(overall, 1), scorecard

    async def _decide(self, state: AgentState) -> dict:
        checks = state.get("checks", [])
        problematic = [
            check
            for check in checks
            if check.status in {"NOT_FOUND", "MISMATCH", "REVIEW_REQUIRED", "ERROR"}
        ]

        events = list(state.get("events", []))
        reasons = list(state.get("reasons", []))
        confidence_score, _ = self._score_state(state)
        threshold = await self.repository.get_auto_approval_threshold()

        if problematic:
            reasons.extend(check.message for check in problematic)

            integrity_issue = any(
                check.status == "MISMATCH"
                or (
                    check.status == "REVIEW_REQUIRED"
                    and check.source in {"vendor_master", "vendor_master_snapshot"}
                )
                for check in problematic
            )
            if integrity_issue:
                reasons.append(
                    "Duplicate or inconsistent vendor identity data detected; automatic approval is disabled."
                )

            events.append(
                AgentEvent(
                    step="decision",
                    message=(
                        "Duplicate or inconsistent vendor data detected. Sent directly to human review."
                        if integrity_issue
                        else "Issues detected. Sent to human review with reject recommendation."
                    ),
                )
            )
            return {
                "overall_status": "REVIEW_REQUIRED",
                "recommendation": "REJECT",
                "reasons": list(dict.fromkeys(reasons)),
                "events": events,
            }

        if (
            threshold is not None
            and confidence_score is not None
            and confidence_score < threshold
        ):
            reason = (
                f"Overall confidence score {confidence_score:.1f}% is below the "
                f"configured auto-approval threshold of {threshold:.1f}%."
            )
            reasons.append(reason)
            events.append(
                AgentEvent(
                    step="decision",
                    message="Confidence is below the configured threshold; sent to human review.",
                )
            )
            return {
                "overall_status": "REVIEW_REQUIRED",
                "recommendation": "REJECT",
                "reasons": list(dict.fromkeys(reasons)),
                "events": events,
            }

        events.append(
            AgentEvent(
                step="decision",
                message="All required checks passed. Vendor approved by the agent.",
            )
        )
        return {
            "overall_status": "APPROVED",
            "recommendation": "APPROVE",
            "reasons": ["All required verification checks passed."],
            "events": events,
        }

    async def _persist(self, state: AgentState) -> dict:
        confidence_score, scorecard = self._score_state(state)
        result = VendorProcessResult(
            vendor_id=state["vendor_id"],
            vendor_name=self._vendor_name(state),
            overall_status=state["overall_status"],
            recommendation=state["recommendation"],
            missing_documents=state.get("missing_documents", []),
            extractions=state.get("extractions", []),
            checks=state.get("checks", []),
            reasons=state.get("reasons", []),
            events=state.get("events", []),
            confidence_score=confidence_score,
            scorecard=scorecard,
            submitted_data=state.get("submitted_data", {}),
        )
        await self.repository.save_result(
            result,
            documents=state.get("new_extractions", result.extractions),
            file_payloads=state.get("files", []),
            submitted_data=state.get("submitted_data", {}),
        )
        events = list(state.get("events", []))
        events.append(
            AgentEvent(
                step="persist",
                message="Verification result saved to Supabase.",
            )
        )
        return {"events": events}
