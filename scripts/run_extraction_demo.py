import json
from pathlib import Path

from app.agents.document_understanding import DocumentUnderstandingAgent
from app.llm.mock_provider import MockProvider

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CASES = (
    "business_registration",
    "tax_certificate",
    "bank_document",
    "quotation",
    "missing_field",
    "prompt_injection",
    "scanned_like",
)


def main() -> None:
    for name in CASES:
        text = (FIXTURES / "documents" / f"{name}.txt").read_text(encoding="utf-8")
        canned = json.loads((FIXTURES / "llm" / f"{name}.json").read_text(encoding="utf-8"))
        agent = DocumentUnderstandingAgent(MockProvider({"document_extraction": canned}))
        result = agent.run(
            {"document_id": f"demo-{name}", "file_name": f"{name}.txt", "text": text}
        )
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
