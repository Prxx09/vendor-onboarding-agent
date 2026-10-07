# Supabase setup

1. Create a Supabase project for this environment.
2. In the Supabase SQL Editor, run `supabase/migrations/0001_init.sql`, then `supabase/seed.sql`.
3. In Project Settings → API, copy the project URL and the `service_role` key.
4. Copy `.env.example` to `.env`; set `REPOSITORY_BACKEND=supabase`, `SUPABASE_URL`, and `SUPABASE_SERVICE_KEY`. Keep `LLM_PROVIDER` independent of this choice.
5. Run `python scripts/check_supabase.py` from the repository root. The script creates a temporary request and deletes it after checks; its audit event is retained with a null request reference.

The `service_role` key is server-side only. It bypasses Row Level Security and must never be included in frontend code, a browser bundle, or sent to an untrusted client. Keep `.env` out of version control.
