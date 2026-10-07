-- Keep the submitted human role alongside the approval decision for auditability.
alter table public.approvals
    add column if not exists approver_role text
    check (approver_role is null or approver_role in ('PROCUREMENT', 'BUDGET_OWNER', 'FINANCE_HEAD'));
