-- Phase 1 schema. All values in seed.sql are synthetic demonstration data.
create extension if not exists pgcrypto;

create table if not exists public.vendor_requests (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    request_type text not null check (request_type in ('NEW_SUPPLIER', 'SUPPLIER_WITH_PURCHASE')),
    status text not null default 'DRAFT',
    supplier_name text,
    legal_name text,
    country text,
    tax_id text,
    address text,
    currency text,
    estimated_annual_spend numeric,
    requesting_department text,
    requester_id text,
    budget_owner_id text,
    procurement_owner_id text,
    purchase_details jsonb,
    is_demo boolean not null default false,
    updated_at timestamptz not null default now()
);

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    doc_type text not null, file_name text not null, storage_path text not null,
    sha256 text, text_content text, text_quality jsonb
);
create table if not exists public.extracted_fields (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    document_id uuid not null references public.documents(id) on delete cascade,
    field_name text not null, value jsonb, confidence numeric,
    status text not null check (status in ('FOUND', 'MISSING', 'UNVERIFIED')),
    evidence jsonb, review_status text not null default 'PENDING'
        check (review_status in ('PENDING', 'CONFIRMED', 'CORRECTED')),
    reviewed_by text
);
create table if not exists public.validation_findings (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    code text not null, severity text not null, message text not null,
    evidence jsonb, source text not null check (source in ('DETERMINISTIC', 'AGENT'))
);
create table if not exists public.risk_assessments (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    score integer not null, label text not null, hard_blocks jsonb not null default '[]'::jsonb,
    contributions jsonb not null default '[]'::jsonb, explanation jsonb not null default '{}'::jsonb
);
create table if not exists public.approvals (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    stage text not null check (stage in ('PROCUREMENT', 'BUDGET_OWNER', 'FINANCE_HEAD')),
    approver_id text not null, decision text check (decision in ('APPROVE', 'REJECT', 'REQUEST_REWORK')),
    comment text
);
create table if not exists public.audit_events (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid references public.vendor_requests(id) on delete set null,
    actor text not null, actor_type text not null check (actor_type in ('AGENT', 'HUMAN', 'SYSTEM')),
    event_type text not null, details jsonb not null default '{}'::jsonb
);
create table if not exists public.agent_runs (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null references public.vendor_requests(id) on delete cascade,
    agent_name text not null, status text not null, input_hash text not null,
    output jsonb, error text, duration_ms integer not null
);
create table if not exists public.vendors (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    legal_name text not null, tax_id text, country text, address text, bank_name text,
    bank_account_number text, routing_code text, status text
);
create table if not exists public.sanctions_entries (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    name text not null, aliases text[] not null default '{}', country text, list_name text not null
);
create table if not exists public.vendor_drafts (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null unique references public.vendor_requests(id) on delete cascade,
    draft jsonb not null, version integer not null default 1
);
create table if not exists public.po_drafts (
    id uuid primary key default gen_random_uuid(), created_at timestamptz not null default now(),
    request_id uuid not null unique references public.vendor_requests(id) on delete cascade,
    draft jsonb not null, version integer not null default 1
);

create index if not exists idx_documents_request_id on public.documents(request_id);
create index if not exists idx_extracted_fields_request_id on public.extracted_fields(request_id);
create index if not exists idx_extracted_fields_document_id on public.extracted_fields(document_id);
create index if not exists idx_validation_findings_request_id on public.validation_findings(request_id);
create index if not exists idx_risk_assessments_request_id on public.risk_assessments(request_id);
create index if not exists idx_approvals_request_id on public.approvals(request_id);
create index if not exists idx_audit_events_request_id on public.audit_events(request_id);
create index if not exists idx_agent_runs_request_id on public.agent_runs(request_id);
create index if not exists idx_vendor_drafts_request_id on public.vendor_drafts(request_id);
create index if not exists idx_po_drafts_request_id on public.po_drafts(request_id);
create index if not exists idx_vendors_tax_id on public.vendors(tax_id);

create or replace function public.reject_audit_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'audit_events is append-only; % is prohibited', tg_op;
end;
$$;
drop trigger if exists audit_events_append_only on public.audit_events;
create trigger audit_events_append_only
before update or delete on public.audit_events
for each row execute function public.reject_audit_mutation();

-- RLS is enabled without client policies. Server-side service_role access bypasses RLS;
-- the service_role key must never be exposed to a browser or untrusted client.
alter table public.vendor_requests enable row level security;
alter table public.documents enable row level security;
alter table public.extracted_fields enable row level security;
alter table public.validation_findings enable row level security;
alter table public.risk_assessments enable row level security;
alter table public.approvals enable row level security;
alter table public.audit_events enable row level security;
alter table public.agent_runs enable row level security;
alter table public.vendors enable row level security;
alter table public.sanctions_entries enable row level security;
alter table public.vendor_drafts enable row level security;
alter table public.po_drafts enable row level security;

insert into storage.buckets (id, name, public)
values ('vendor-documents', 'vendor-documents', false)
on conflict (id) do update set public = false;
