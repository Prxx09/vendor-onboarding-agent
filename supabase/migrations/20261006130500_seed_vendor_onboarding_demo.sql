insert into public.onboarding_cases (
  case_key, request_id, title, status, risk_score, risk_label, hard_block,
  supplier_name, legal_name, supplier_type, country, address, tax_id, contact_email,
  purchase_description, estimated_annual_spend, currency, payment_terms,
  requesting_department, budget_owner, procurement_owner, raw_request, expected_result
) values
('clean_supplier','REQ-CLEAN_SUPPLIER','Clean supplier onboarding','PENDING_PROCUREMENT',0,'Low',false,
 'Evergreen Facility Solutions Private Limited','Evergreen Facility Solutions Private Limited','Demo category','India','42 Innovation Park, Mumbai, Maharashtra 400093','GST27EFS9012Z5A','contact@clean_supplier.example.test',
 'Preventive HVAC maintenance services',180000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"PENDING_PROCUREMENT","expected_risk_score":0,"expected_risk_label":"Low","expected_hard_block":false,"expected_findings":[],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('missing_tax_certificate','REQ-MISSING_TAX_CERTIFICATE','Missing mandatory tax certificate','REWORK',20,'Medium',false,
 'Lighthouse Workplace Supplies Private Limited','Lighthouse Workplace Supplies Private Limited','Demo category','India','88 Market Avenue, Mumbai, Maharashtra 400076','', 'contact@missing_tax_certificate.example.test',
 'Ergonomic workstation supplies',95000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"REWORK","expected_risk_score":20,"expected_risk_label":"Medium","expected_hard_block":false,"expected_findings":[{"code":"MISSING_TAX_CERTIFICATE","score":20}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('duplicate_tax_id','REQ-DUPLICATE_TAX_ID','Duplicate tax identifier','BLOCKED',40,'High',true,
 'Blue River Industrial Supplies LLP','Blue River Industrial Supplies LLP','Demo category','India','17 Foundry Road, Bhiwandi, Maharashtra 421302','GST27BRI0002Z5A','contact@duplicate_tax_id.example.test',
 'Industrial fasteners and tools',220000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"BLOCKED","expected_risk_score":40,"expected_risk_label":"High","expected_hard_block":true,"expected_findings":[{"code":"DUPLICATE_TAX_ID","score":40}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('similar_supplier_name','REQ-SIMILAR_SUPPLIER_NAME','Similar supplier name','PENDING_PROCUREMENT',20,'Medium',false,
 'Atlas Office Systems India Private Limited','Atlas Office Systems India Private Limited','Demo category','India','19 Tech Crescent, Mumbai, Maharashtra 400013','GST27AOS9013Z5A','contact@similar_supplier_name.example.test',
 'Meeting-room video equipment',125000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"PENDING_PROCUREMENT","expected_risk_score":20,"expected_risk_label":"Medium","expected_hard_block":false,"expected_findings":[{"code":"SIMILAR_VENDOR_NAME","score":20}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('bank_name_mismatch','REQ-BANK_NAME_MISMATCH','Bank account-holder mismatch','BLOCKED',30,'High',true,
 'Crestline Packaging Private Limited','Crestline Packaging Private Limited','Demo category','India','2 Packaging Estate, Navi Mumbai, Maharashtra 400705','GST27CPP9014Z5A','contact@bank_name_mismatch.example.test',
 'Corrugated packaging material',360000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"BLOCKED","expected_risk_score":30,"expected_risk_label":"High","expected_hard_block":true,"expected_findings":[{"code":"BANK_ACCOUNT_HOLDER_MISMATCH","score":30}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('expired_registration','REQ-EXPIRED_REGISTRATION','Expired registration document','REWORK',20,'Medium',false,
 'Pinecrest Technical Services Private Limited','Pinecrest Technical Services Private Limited','Demo category','India','65 Service Lane, Thane, Maharashtra 400604','GST27PTS9015Z5A','contact@expired_registration.example.test',
 'Network cabling installation',140000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"REWORK","expected_risk_score":20,"expected_risk_label":"Medium","expected_hard_block":false,"expected_findings":[{"code":"EXPIRED_REGISTRATION","score":20}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('sanctions_match','REQ-SANCTIONS_MATCH','Sanctions reference match','BLOCKED',60,'High',true,
 'Northstar Export Trading LLC','Northstar Export Trading LLC','Demo category','Fictionland','12 Harbor Exchange, Port Azure, Fictionland 500001','FX-NS-90216','contact@sanctions_match.example.test',
 'Specialist imported components',500000,'USD','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"BLOCKED","expected_risk_score":60,"expected_risk_label":"High","expected_hard_block":true,"expected_findings":[{"code":"SANCTIONS_MATCH","score":60}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('high_value_purchase','REQ-HIGH_VALUE_PURCHASE','High-value purchase routing','PENDING_FINANCE_HEAD',10,'Low',false,
 'Summit Data Centre Solutions Private Limited','Summit Data Centre Solutions Private Limited','Demo category','India','300 Digital Campus, Navi Mumbai, Maharashtra 400708','GST27SDC9017Z5A','contact@high_value_purchase.example.test',
 'Data-centre network equipment',2500000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"PENDING_FINANCE_HEAD","expected_risk_score":10,"expected_risk_label":"Low","expected_hard_block":false,"expected_findings":[{"code":"HIGH_VALUE_PURCHASE","score":10}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER","FINANCE_HEAD"]}'),
('international_supplier','REQ-INTERNATIONAL_SUPPLIER','International supplier with SWIFT data','PENDING_PROCUREMENT',10,'Medium',false,
 'Aurora Analytics UK Limited','Aurora Analytics UK Limited','Demo category','United Kingdom','18 Wellington Square, London, United Kingdom W1A 1AA','GB-VA-9018','contact@international_supplier.example.test',
 'Annual data-platform subscription',750000,'USD','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"PENDING_PROCUREMENT","expected_risk_score":10,"expected_risk_label":"Medium","expected_hard_block":false,"expected_findings":[{"code":"INTERNATIONAL_SUPPLIER_REVIEW","score":10}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}'),
('multiple_issues','REQ-MULTIPLE_ISSUES','Combined validation failures','BLOCKED',70,'High',true,
 'Vertex Industrial Traders Private Limited','Vertex Industrial Traders Private Limited','Demo category','India','7 Industrial Ring Road, Pune, Maharashtra 411019','GST27VIT9019Z5A','contact@multiple_issues.example.test',
 'Custom fabricated parts',920000,'INR','Net 30 days','Operations','Asha Mehta','Rahul Nair',
 '{"data_classification":"synthetic_demo_data"}', '{"expected_status":"BLOCKED","expected_risk_score":70,"expected_risk_label":"High","expected_hard_block":true,"expected_findings":[{"code":"MISSING_TAX_CERTIFICATE","score":20},{"code":"BANK_NOT_IN_REFERENCE_DATA","score":30},{"code":"CROSS_DOCUMENT_NAME_MISMATCH","score":20}],"expected_approvals":["PROCUREMENT","BUDGET_OWNER"]}')
on conflict (case_key) do update set status = excluded.status, risk_score = excluded.risk_score, risk_label = excluded.risk_label,
  hard_block = excluded.hard_block, updated_at = now();

insert into public.validation_checks (case_id, code, check_name, result, score, severity, message, evidence)
select c.id, f->>'code', replace(initcap(replace(f->>'code','_',' ')),' ',' '),
  case when (f->>'score')::int >= 30 then 'fail' else 'warning' end,
  (f->>'score')::int,
  case when (f->>'score')::int >= 30 then 'high' else 'medium' end,
  'Seeded expected finding from the synthetic demo dataset', f
from public.onboarding_cases c
cross join lateral jsonb_array_elements(c.expected_result->'expected_findings') f
on conflict (case_id, code) do nothing;

insert into public.validation_checks (case_id, code, check_name, result, score, severity, message)
select c.id, 'BASELINE_VALIDATION', 'Baseline validation', 'pass', 0, 'low', 'No seeded finding for this baseline check'
from public.onboarding_cases c
where not exists (select 1 from public.validation_checks v where v.case_id = c.id and v.code = 'BASELINE_VALIDATION')
on conflict (case_id, code) do nothing;

insert into public.approval_steps (case_id, approval_type, sequence_no, status)
select c.id, a.approval_type, a.ordinality::int, case when c.hard_block then 'blocked' else 'pending' end
from public.onboarding_cases c
cross join lateral jsonb_array_elements_text(c.expected_result->'expected_approvals') with ordinality a(approval_type, ordinality)
on conflict (case_id, approval_type) do nothing;

insert into public.audit_events (case_id, sequence_no, event_type, stage, actor_type, actor_id, status_to, correlation_id, evidence)
select c.id, 1, 'case_created', 'intake', 'system', 'seed_loader', c.status, c.request_id,
  jsonb_build_object('source','Vendor_Onboarding_Synthetic_Demo_Data','synthetic_only',true)
from public.onboarding_cases c
where not exists (select 1 from public.audit_events e where e.case_id = c.id and e.sequence_no = 1);

insert into public.audit_events (case_id, sequence_no, event_type, stage, actor_type, actor_id, status_from, status_to, correlation_id, evidence)
select c.id, 2, 'validation_completed', 'validation', 'system', 'seed_loader', 'VALIDATING', c.status, c.request_id,
  jsonb_build_object('risk_score',c.risk_score,'hard_block',c.hard_block)
from public.onboarding_cases c
where not exists (select 1 from public.audit_events e where e.case_id = c.id and e.sequence_no = 2);

do $$
declare
  c record;
  f text;
  doc_names text[];
begin
  for c in select id, case_key from public.onboarding_cases loop
    doc_names := case c.case_key
      when 'clean_supplier' then array['supplier_quotation.pdf','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf','insurance_certificate.docx']
      when 'missing_tax_certificate' then array['supplier_quotation.pdf','business_registration.pdf','bank_letter.pdf']
      when 'duplicate_tax_id' then array['supplier_quotation.pdf','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf']
      when 'similar_supplier_name' then array['address_proof.jpg','supplier_quotation.pdf','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf']
      when 'bank_name_mismatch' then array['supplier_quotation.pdf','bank_letter_mismatch.pdf','business_registration.pdf','tax_certificate.pdf']
      when 'expired_registration' then array['supplier_quotation.pdf','expired_business_registration.pdf','tax_certificate.pdf','bank_letter.pdf']
      when 'sanctions_match' then array['supplier_quotation.pdf','supplier_quotation.xlsx','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf']
      when 'high_value_purchase' then array['supplier_quotation.pdf','purchase_request.xlsx','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf']
      when 'international_supplier' then array['supplier_quotation.pdf','supplier_quotation.xlsx','address_proof.png','business_registration.pdf','tax_certificate.pdf','bank_letter.pdf','bank_confirmation.docx']
      else array['supplier_quotation.pdf','bank_letter_mismatch.pdf','business_registration.pdf','cancelled_cheque.png']
    end;
    foreach f in array doc_names loop
      insert into public.case_documents(case_id, document_type, file_name, extraction_status)
      values (c.id, split_part(f,'.',1), f, 'pending')
      on conflict do nothing;
    end loop;
  end loop;
end $$;
