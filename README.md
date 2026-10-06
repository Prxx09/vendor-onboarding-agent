# Vendor Onboarding Agent

Agentic foundation for vendor onboarding, with in-memory and Supabase persistence. See [AGENTS.md](AGENTS.md) for scope and non-negotiable rules and [Supabase setup](docs/supabase_setup.md) for database setup.

## Setup

```powershell
pip install -e ".[dev]"
python -m pytest -q
ruff check .
```

The default `LLM_PROVIDER=mock` uses the offline mock provider. Set `LLM_PROVIDER=groq` and `GROQ_API_KEY` in the environment (or `.env`) to use Groq; `GROQ_MODEL` selects the model. The default `REPOSITORY_BACKEND=memory` uses in-memory storage; set it to `supabase` with server-side Supabase credentials to persist records. The smoke script demonstrates the mock path: `python scripts/smoke_agent.py`.
