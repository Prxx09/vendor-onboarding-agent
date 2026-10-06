create extension if not exists pgcrypto;

create table if not exists public.onboarding_cases (
  id uuid primary key default gen_random_uuid(),
  case_key text not null unique,
  request_id text not null unique,
  title text not null,
  status text not null,
  risk_score integer not null default 0,
  risk_label text not null default 'Low',
  hard_block boolean not null default false,
  confidence_score numeric(5,2),
  supplier_name text not null,
  legal_name text not null,
  supplier_type text,
  country text not null,
  address text,
  tax_id text,
  contact_email text,
  purchase_description text,
  estimated_annual_spend numeric(14,2),
  currency text,
  payment_terms text,
  requesting_department text,
  budget_owner text,
  procurement_owner text,
  raw_request jsonb not null default '{}'::jsonb,
  expected_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.case_documents (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.onboarding_cases(id) on delete cascade,
  document_type text,
  file_name text not null,
  mime_type text,
  storage_path text,
  file_hash text,
  extraction_status text not null default 'pending',
  extracted_fields jsonb not null default '{}'::jsonb,
  extracted_text text,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_checks (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.onboarding_cases(id) on delete cascade,
  code text not null,
  check_name text not null,
  result text not null,
  score integer not null default 0,
  severity text,
  message text,
  evidence jsonb not null default '{}'::jsonb,
  evaluated_at timestamptz not null default now(),
  unique(case_id, code)
);

create table if not exists public.approval_steps (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.onboarding_cases(id) on delete cascade,
  approval_type text not null,
  sequence_no integer not null,
  status text not null default 'pending',
  approver_name text,
  decided_at timestamptz,
  decision_note text,
  unique(case_id, approval_type)
);

create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  case_id uuid references public.onboarding_cases(id) on delete cascade,
  sequence_no integer not null,
  event_type text not null,
  stage text not null,
  actor_type text not null,
  actor_id text,
  status_from text,
  status_to text,
  correlation_id text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(case_id, sequence_no)
);

create table if not exists public.reference_vendors (
  vendor_id text primary key,
  legal_name text not null,
  tax_id text not null,
  bank_name text,
  account_number text,
  ifsc text,
  country text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.reference_banks (
  bank_name text not null,
  ifsc text,
  swift text,
  country text not null,
  currency text not null,
  primary key(bank_name, country)
);

create table if not exists public.reference_sanctions (
  id uuid primary key default gen_random_uuid(),
  entity_name text not null,
  country text not null,
  risk_level text not null,
  reason text not null
);

create table if not exists public.reference_country_rules (
  country text primary key,
  allowed_currencies jsonb not null,
  bank_code text not null
);

create table if not exists public.reference_approval_thresholds (
  rule_key text primary key,
  rule_value jsonb not null
);

create index if not exists onboarding_cases_status_idx on public.onboarding_cases(status);
create index if not exists audit_events_case_created_idx on public.audit_events(case_id, created_at);
create index if not exists validation_checks_case_idx on public.validation_checks(case_id);

alter table public.onboarding_cases enable row level security;
alter table public.case_documents enable row level security;
alter table public.validation_checks enable row level security;
alter table public.approval_steps enable row level security;
alter table public.audit_events enable row level security;
alter table public.reference_vendors enable row level security;
alter table public.reference_banks enable row level security;
alter table public.reference_sanctions enable row level security;
alter table public.reference_country_rules enable row level security;
alter table public.reference_approval_thresholds enable row level security;

create policy "synthetic cases are readable" on public.onboarding_cases for select to anon, authenticated using (true);
create policy "synthetic documents are readable" on public.case_documents for select to anon, authenticated using (true);
create policy "synthetic checks are readable" on public.validation_checks for select to anon, authenticated using (true);
create policy "synthetic approvals are readable" on public.approval_steps for select to anon, authenticated using (true);
create policy "synthetic audit is readable" on public.audit_events for select to anon, authenticated using (true);
create policy "reference vendors are readable" on public.reference_vendors for select to anon, authenticated using (true);
create policy "reference banks are readable" on public.reference_banks for select to anon, authenticated using (true);
create policy "reference sanctions are readable" on public.reference_sanctions for select to anon, authenticated using (true);
create policy "country rules are readable" on public.reference_country_rules for select to anon, authenticated using (true);
create policy "approval thresholds are readable" on public.reference_approval_thresholds for select to anon, authenticated using (true);

insert into public.reference_vendors (vendor_id, legal_name, tax_id, bank_name, account_number, ifsc, country) values
('VEN-1001','Atlas Office Systems Private Limited','GST27ATL0001Z5A','Northwind Bank','009876543210','NWBK0000123','India'),
('VEN-1002','Blue River Industrial Supply LLP','GST27BRI0002Z5A','Pioneer Bank','001234567890','PNBK0000456','India'),
('VEN-1003','Harbor Safety Equipment India Private Limited','GST29HSE0003Z5A','Cedar Bank','007654321098','CDBK0000789','India'),
('VEN-1004','Silverline Logistics Services Private Limited','GST27SLS0004Z5A','Northwind Bank','003456789012','NWBK0000123','India')
on conflict (vendor_id) do nothing;

insert into public.reference_banks (bank_name, ifsc, swift, country, currency) values
('Northwind Bank','NWBK0000123','NWBDINBB001','India','INR'),
('Pioneer Bank','PNBK0000456','PNBKINBB002','India','INR'),
('Cedar Bank','CDBK0000789','CDBKINBB003','India','INR'),
('Maple Trust Bank','MTBK0000321','MTBKINBB004','India','INR'),
('Meridian International Bank',null,'MIBKGB2L001','United Kingdom','USD')
on conflict (bank_name, country) do nothing;

insert into public.reference_sanctions (entity_name, country, risk_level, reason) values
('Northstar Export Trading LLC','Fictionland','High','Synthetic sanctions match for demo only'),
('Orion Maritime Holdings','Fictionland','High','Synthetic sanctions match for demo only'),
('Redstone Defence Components','Fictionland','Medium','Synthetic watchlist entry for demo only');

insert into public.reference_country_rules (country, allowed_currencies, bank_code) values
('India','["INR"]','IFSC'),
('United Kingdom','["USD","GBP"]','SWIFT'),
('Fictionland','["USD"]','SWIFT')
on conflict (country) do nothing;

insert into public.reference_approval_thresholds (rule_key, rule_value) values
('finance_head_threshold','1000000'),
('procurement_approval_required','true'),
('budget_owner_approval_required','true'),
('requester_cannot_approve','true'),
('same_person_cannot_hold_both_approvals','true')
on conflict (rule_key) do nothing;

create or replace view public.case_overview as
select c.*, coalesce(jsonb_agg(distinct jsonb_build_object(
  'code', v.code, 'result', v.result, 'score', v.score, 'severity', v.severity, 'message', v.message
)) filter (where v.id is not null), '[]'::jsonb) as checks,
coalesce(jsonb_agg(distinct jsonb_build_object(
  'approval_type', a.approval_type, 'sequence_no', a.sequence_no, 'status', a.status, 'approver_name', a.approver_name
)) filter (where a.id is not null), '[]'::jsonb) as approvals
from public.onboarding_cases c
left join public.validation_checks v on v.case_id = c.id
left join public.approval_steps a on a.case_id = c.id
group by c.id;
