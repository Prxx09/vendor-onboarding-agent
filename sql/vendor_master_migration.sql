-- Global Vendor Master migration.
-- Run once in Supabase SQL Editor after pulling this feature.
-- Global enterprise Vendor Master. Only approved onboarding cases are promoted.
create table if not exists vendor_master (
    id uuid primary key default gen_random_uuid(),
    vendor_code text not null unique,
    source_case_id uuid unique references verification_vendors(id) on delete set null,
    legal_name text not null,
    registration_number text,
    tax_id text,
    pan text,
    registered_address text,
    region text,
    categories text[] not null default '{}'::text[],
    primary_contact_name text,
    primary_contact_email text,
    primary_contact_phone text,
    bank_name text,
    account_number text,
    ifsc_swift text,
    bank_verification_status text,
    kyc_status text,
    verification_status text not null default 'VERIFIED',
    risk_level text,
    status text not null default 'ACTIVE'
        check (status in ('ACTIVE', 'SUSPENDED', 'BLOCKED', 'EXPIRED')),
    approved_at timestamptz,
    last_verified_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_vendor_master_legal_name on vendor_master(lower(legal_name));
create index if not exists idx_vendor_master_tax on vendor_master(tax_id);
create index if not exists idx_vendor_master_registration on vendor_master(registration_number);
create index if not exists idx_vendor_master_status on vendor_master(status);
create index if not exists idx_vendor_master_categories on vendor_master using gin(categories);

alter table verification_vendors
    add column if not exists categories text[] not null default '{}'::text[],
    add column if not exists contact_name text,
    add column if not exists contact_phone text;

update verification_vendors
set categories = array[category]
where coalesce(array_length(categories, 1), 0) = 0
  and category is not null
  and btrim(category) <> '';

insert into vendor_master (
    vendor_code, source_case_id, legal_name, tax_id, pan,
    registered_address, region, categories,
    primary_contact_name, primary_contact_email, primary_contact_phone,
    account_number, ifsc_swift, verification_status, status,
    approved_at, last_verified_at
)
select
    'VEN-' || upper(substr(replace(v.id::text, '-', ''), 1, 8)),
    v.id,
    v.legal_name,
    nullif(v.submitted_data->>'tax_id', ''),
    nullif(v.submitted_data->>'pan', ''),
    nullif(v.submitted_data->>'registered_address', ''),
    v.region,
    case
        when jsonb_typeof(v.submitted_data->'categories') = 'array'
        then array(select jsonb_array_elements_text(v.submitted_data->'categories'))
        when v.category is not null and btrim(v.category) <> ''
        then array[v.category]
        else '{}'::text[]
    end,
    nullif(v.submitted_data->>'contact_name', ''),
    coalesce(nullif(v.submitted_data->>'contact_email', ''), v.contact_email),
    nullif(v.submitted_data->>'contact_phone', ''),
    nullif(v.submitted_data->>'bank_account', ''),
    nullif(v.submitted_data->>'ifsc', ''),
    case when v.human_decision = 'APPROVE' then 'VERIFIED_WITH_OVERRIDE' else 'VERIFIED' end,
    'ACTIVE',
    v.updated_at,
    v.updated_at
from verification_vendors v
where v.status = 'APPROVED'
on conflict (source_case_id) do nothing;
