create table if not exists public.verification_results (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    capability text not null,
    provider_name text not null,
    mode text not null check (mode in ('LOCAL_SIMULATED', 'LIVE')),
    status text not null check (status in ('VERIFIED', 'MISMATCH', 'NOT_FOUND', 'UNAVAILABLE', 'NOT_CONFIGURED')),
    reference_id text,
    details jsonb not null default '{}'::jsonb,
    latency_ms integer not null default 0,
    error text,
    checked_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists verification_results_request_id_idx
    on public.verification_results (request_id);

alter table public.verification_results enable row level security;
