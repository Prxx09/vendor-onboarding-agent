-- Add the Global Vendor Master to projects created before the master-dashboard feature.

create table if not exists public.vendor_master (
    id uuid primary key default gen_random_uuid(),
    vendor_code text not null unique,
    source_case_id uuid unique references public.verification_vendors(id) on delete set null,
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

create index if not exists idx_vendor_master_legal_name on public.vendor_master(lower(legal_name));
create index if not exists idx_vendor_master_tax on public.vendor_master(tax_id);
create index if not exists idx_vendor_master_registration on public.vendor_master(registration_number);
create index if not exists idx_vendor_master_status on public.vendor_master(status);
create index if not exists idx_vendor_master_categories on public.vendor_master using gin(categories);

notify pgrst, 'reload schema';
