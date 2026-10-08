-- Persist runtime application settings such as the auto-approval threshold.

create table if not exists public.app_settings (
    key text primary key,
    value_json jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

insert into public.app_settings (key, value_json)
values ('auto_approval_threshold', '{"value": 80}'::jsonb)
on conflict (key) do nothing;

notify pgrst, 'reload schema';
