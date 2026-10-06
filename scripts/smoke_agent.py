from app.agents.smoke import SmokeAgent
from app.llm.mock_provider import MockProvider


def main() -> None:
    provider = MockProvider({"smoke": {"summary": "A short smoke test.", "word_count": 3}})
    result = SmokeAgent(provider).run({"text": "A short smoke test."})
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
