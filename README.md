# Vendor Onboarding Agent

Phase 0 foundation for the agentic layer. See [AGENTS.md](AGENTS.md) for scope and non-negotiable rules.

## Setup

```powershell
pip install -e ".[dev]"
python -m pytest -q
ruff check .
```

The default `LLM_PROVIDER=mock` uses the offline mock provider. Set `LLM_PROVIDER=groq` and `GROQ_API_KEY` in the environment (or `.env`) to use Groq; `GROQ_MODEL` selects the model. The smoke script demonstrates the mock path: `python scripts/smoke_agent.py`.
