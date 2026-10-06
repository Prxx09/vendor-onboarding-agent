create or replace view public.case_overview with (security_invoker = true) as
select c.*,
  coalesce(jsonb_agg(distinct jsonb_build_object(
    'code', v.code, 'result', v.result, 'score', v.score, 'severity', v.severity, 'message', v.message
  )) filter (where v.id is not null), '[]'::jsonb) as checks,
  coalesce(jsonb_agg(distinct jsonb_build_object(
    'approval_type', a.approval_type, 'sequence_no', a.sequence_no, 'status', a.status, 'approver_name', a.approver_name
  )) filter (where a.id is not null), '[]'::jsonb) as approvals
from public.onboarding_cases c
left join public.validation_checks v on v.case_id = c.id
left join public.approval_steps a on a.case_id = c.id
group by c.id;
