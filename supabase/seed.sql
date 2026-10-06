-- Entire seed set is synthetic. Names, tax identifiers, banks and lists are fictional.
insert into public.vendors (id, legal_name, tax_id, country, address, bank_name, bank_account_number, routing_code, status) values
('10000000-0000-4000-8000-000000000001', 'ACME Supplies Private Limited', 'SYN-TAX-ACME-001', 'IN', '10 Example Park, Demo City', 'Fictional Test Bank', 'SYNTHETIC-ACCT-0001', 'SYN-ROUTE-01', 'ACTIVE'),
('10000000-0000-4000-8000-000000000002', 'Northstar Office Goods Ltd', 'SYN-TAX-NS-002', 'GB', '2 Sample Lane, Exampleton', 'Imaginary Bank One', 'SYNTHETIC-ACCT-0002', 'SYN-ROUTE-02', 'ACTIVE'),
('10000000-0000-4000-8000-000000000003', 'Blue Fern Components LLC', 'SYN-TAX-BF-003', 'US', '3 Fiction Road, Sampleville', 'Demo National Bank', 'SYNTHETIC-ACCT-0003', 'SYN-ROUTE-03', 'ACTIVE'),
('10000000-0000-4000-8000-000000000004', 'Cedar Cloud Services Pvt Ltd', 'SYN-TAX-CC-004', 'IN', '4 Mockingbird Street, Demo City', 'Fictional Test Bank', 'SYNTHETIC-ACCT-0001', 'SYN-ROUTE-01', 'ACTIVE'),
('10000000-0000-4000-8000-000000000005', 'Pebble & Pine Logistics GmbH', 'SYN-TAX-PP-005', 'DE', '5 Placeholder Platz, Testburg', 'Example Credit Union', 'SYNTHETIC-ACCT-0005', 'SYN-ROUTE-05', 'ACTIVE'),
('10000000-0000-4000-8000-000000000006', 'Copper Kite Analytics Inc', 'SYN-TAX-CK-006', 'CA', '6 Fictional Crescent, Sample City', 'Imaginary Bank Two', 'SYNTHETIC-ACCT-0006', 'SYN-ROUTE-06', 'ACTIVE'),
('10000000-0000-4000-8000-000000000007', 'Orbit Meadow Packaging SAS', 'SYN-TAX-OM-007', 'FR', '7 Test Boulevard, Mock-sur-Mer', 'Demo National Bank', 'SYNTHETIC-ACCT-0007', 'SYN-ROUTE-07', 'ACTIVE'),
('10000000-0000-4000-8000-000000000008', 'Juniper Loop Consulting Pty Ltd', 'SYN-TAX-JL-008', 'AU', '8 Sample Quay, Example Bay', 'Fictional Test Bank', 'SYNTHETIC-ACCT-0008', 'SYN-ROUTE-08', 'ACTIVE'),
('10000000-0000-4000-8000-000000000009', 'ACME Supply Private Limited', 'SYN-TAX-ACME-NEAR', 'IN', '9 Example Park, Demo City', 'Imaginary Bank One', 'SYNTHETIC-ACCT-0009', 'SYN-ROUTE-09', 'ACTIVE'),
('10000000-0000-4000-8000-000000000010', 'Silver Finch Safety Equipment', 'SYN-TAX-SF-010', 'US', '10 Mock Street, Sampletown', 'Example Credit Union', 'SYNTHETIC-ACCT-0010', 'SYN-ROUTE-10', 'ACTIVE'),
('10000000-0000-4000-8000-000000000011', 'Willow Metric Manufacturing', 'SYN-TAX-WM-011', 'JP', '11 Placeholder Avenue, Test Ward', 'Imaginary Bank Two', 'SYNTHETIC-ACCT-0011', 'SYN-ROUTE-11', 'ACTIVE'),
('10000000-0000-4000-8000-000000000012', 'Mosaic Comet Facilities Ltd', 'SYN-TAX-MC-012', 'IE', '12 Fiction Walk, Exampleford', 'Demo National Bank', 'SYNTHETIC-ACCT-0012', 'SYN-ROUTE-12', 'ACTIVE')
on conflict (id) do update set legal_name = excluded.legal_name, tax_id = excluded.tax_id,
    country = excluded.country, address = excluded.address, bank_name = excluded.bank_name,
    bank_account_number = excluded.bank_account_number, routing_code = excluded.routing_code,
    status = excluded.status;

insert into public.sanctions_entries (id, name, aliases, country, list_name) values
('20000000-0000-4000-8000-000000000001', 'Synthetic Example Entity Alpha', array['Example Alpha', 'Entity A Demo'], 'ZZ', 'TRAINING-DEMO-LIST'),
('20000000-0000-4000-8000-000000000002', 'Fictional Sample Group Beta', array['Sample Beta Group'], 'YY', 'TRAINING-DEMO-LIST'),
('20000000-0000-4000-8000-000000000003', 'Imaginary Placeholder Person Gamma', array['Placeholder Gamma'], 'XX', 'TRAINING-DEMO-LIST'),
('20000000-0000-4000-8000-000000000004', 'Demo Only Organization Delta', array['Demo Delta Org'], 'ZZ', 'TRAINING-DEMO-LIST'),
('20000000-0000-4000-8000-000000000005', 'Mock Training Entity Epsilon', array['Training Epsilon'], 'YY', 'TRAINING-DEMO-LIST'),
('20000000-0000-4000-8000-000000000006', 'Fictional Test Name Zeta', array['Test Zeta'], 'XX', 'TRAINING-DEMO-LIST')
on conflict (id) do update set name = excluded.name, aliases = excluded.aliases,
    country = excluded.country, list_name = excluded.list_name;
