-- Preserve the complete deterministic Phase 4 result for later consumers.
alter table public.risk_assessments
    add column if not exists blocked boolean not null default false,
    add column if not exists simulated_checks jsonb not null default '[]'::jsonb,
    add column if not exists config_snapshot jsonb not null default '{}'::jsonb;
