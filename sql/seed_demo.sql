-- Synthetic data only. No row in this file represents a real verification service response.

insert into company_registry (
    registration_number, legal_name, country, registered_address,
    company_type, registration_status, registration_valid_to
) values
('U74999MH2024PTC100101', 'Evergreen Facility Solutions Private Limited', 'India', '42 Innovation Park, Mumbai, Maharashtra 400093', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U51909MH2023PTC100102', 'Lighthouse Workplace Supplies Private Limited', 'India', '88 Market Avenue, Mumbai, Maharashtra 400076', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('AAB-2019-100103', 'Blue River Industrial Supplies LLP', 'India', '17 Foundry Road, Bhiwandi, Maharashtra 421302', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U30007MH2025PTC100104', 'Atlas Office Systems India Private Limited', 'India', '19 Tech Crescent, Mumbai, Maharashtra 400013', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U21000MH2024PTC100105', 'Crestline Packaging Private Limited', 'India', '2 Packaging Estate, Navi Mumbai, Maharashtra 400705', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U72900MH2021PTC100106', 'Pinecrest Technical Services Private Limited', 'India', '65 Service Lane, Thane, Maharashtra 400604', 'Synthetic Private Entity', 'EXPIRED', '2025-03-31'),
('FIC-2024-100107', 'Northstar Export Trading LLC', 'Fictionland', '12 Harbor Exchange, Port Azure, Fictionland 500001', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U62010MH2024PTC100108', 'Summit Data Centre Solutions Private Limited', 'India', '300 Digital Campus, Navi Mumbai, Maharashtra 400708', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('UK-99887766', 'Aurora Analytics UK Limited', 'United Kingdom', '18 Wellington Square, London, United Kingdom W1A 1AA', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31'),
('U28999MH2020PTC100110', 'Vertex Industrial Traders Private Limited', 'India', '7 Industrial Ring Road, Pune, Maharashtra 411019', 'Synthetic Private Entity', 'ACTIVE', '2028-12-31')
on conflict (registration_number) do update set
legal_name = excluded.legal_name,
registration_status = excluded.registration_status,
registration_valid_to = excluded.registration_valid_to;

insert into tax_registry (
    tax_id, legal_name, registration_number, country, tax_status, effective_date
) values
('GST27EFS9012Z5A', 'Evergreen Facility Solutions Private Limited', 'U74999MH2024PTC100101', 'India', 'ACTIVE', '2024-04-01'),
('GST27BRI0002Z5A', 'Blue River Industrial Supplies LLP', 'AAB-2019-100103', 'India', 'ACTIVE', '2024-04-01'),
('GST27AOS9013Z5A', 'Atlas Office Systems India Private Limited', 'U30007MH2025PTC100104', 'India', 'ACTIVE', '2024-04-01'),
('GST27CPP9014Z5A', 'Crestline Packaging Private Limited', 'U21000MH2024PTC100105', 'India', 'ACTIVE', '2024-04-01'),
('GST27PTS9015Z5A', 'Pinecrest Technical Services Private Limited', 'U72900MH2021PTC100106', 'India', 'ACTIVE', '2024-04-01'),
('FX-NS-90216', 'Northstar Export Trading LLC', 'FIC-2024-100107', 'Fictionland', 'ACTIVE', '2024-04-01'),
('GST27SDC9017Z5A', 'Summit Data Centre Solutions Private Limited', 'U62010MH2024PTC100108', 'India', 'ACTIVE', '2024-04-01'),
('GB-VA-9018', 'Aurora Analytics UK Limited', 'UK-99887766', 'United Kingdom', 'ACTIVE', '2024-04-01'),
('GST27VIT9019Z5A', 'Vertex Industrial Traders Private Limited', 'U28999MH2020PTC100110', 'India', 'ACTIVE', '2024-04-01')
on conflict (tax_id) do update set
legal_name = excluded.legal_name,
registration_number = excluded.registration_number,
tax_status = excluded.tax_status;

insert into bank_account_registry (
    account_number, bank_name, ifsc_swift, account_holder_legal_name, account_status
) values
('004400112233', 'Maple Trust Bank', 'MTBK0000321', 'Evergreen Facility Solutions Private Limited', 'ACTIVE'),
('004400223344', 'Northwind Bank', 'NWBK0000123', 'Lighthouse Workplace Supplies Private Limited', 'ACTIVE'),
('001234567890', 'Pioneer Bank', 'PNBK0000456', 'Blue River Industrial Supplies LLP', 'ACTIVE'),
('004400334455', 'Cedar Bank', 'CDBK0000789', 'Atlas Office Systems India Private Limited', 'ACTIVE'),
('004400445566', 'Northwind Bank', 'NWBK0000123', 'Crestline Trading House', 'ACTIVE'),
('004400556677', 'Maple Trust Bank', 'MTBK0000321', 'Pinecrest Technical Services Private Limited', 'ACTIVE'),
('MIB-22001144', 'Meridian International Bank', 'MIBKGB2L001', 'Northstar Export Trading LLC', 'ACTIVE'),
('004400667788', 'Cedar Bank', 'CDBK0000789', 'Summit Data Centre Solutions Private Limited', 'ACTIVE'),
('GB29MIBK40001234567890', 'Meridian International Bank', 'MIBKGB2L001', 'Aurora Analytics UK Limited', 'ACTIVE')
on conflict (account_number, ifsc_swift) do update set
account_holder_legal_name = excluded.account_holder_legal_name,
account_status = excluded.account_status;

delete from kyc_registry where registration_number in (
'U74999MH2024PTC100101',
'U51909MH2023PTC100102',
'AAB-2019-100103',
'U30007MH2025PTC100104',
'U21000MH2024PTC100105',
'U72900MH2021PTC100106',
'FIC-2024-100107',
'U62010MH2024PTC100108',
'UK-99887766',
'U28999MH2020PTC100110'
);

insert into kyc_registry (
    legal_name, registration_number, tax_id, kyc_status,
    beneficial_owner_check, document_check_status, risk_country_flag
) values
('Evergreen Facility Solutions Private Limited', 'U74999MH2024PTC100101', 'GST27EFS9012Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Lighthouse Workplace Supplies Private Limited', 'U51909MH2023PTC100102', null, 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Blue River Industrial Supplies LLP', 'AAB-2019-100103', 'GST27BRI0002Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Atlas Office Systems India Private Limited', 'U30007MH2025PTC100104', 'GST27AOS9013Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Crestline Packaging Private Limited', 'U21000MH2024PTC100105', 'GST27CPP9014Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Pinecrest Technical Services Private Limited', 'U72900MH2021PTC100106', 'GST27PTS9015Z5A', 'PENDING_REVIEW', 'CLEAR', 'EXPIRED', false),
('Northstar Export Trading LLC', 'FIC-2024-100107', 'FX-NS-90216', 'PENDING_REVIEW', 'FLAGGED', 'COMPLETE', true),
('Summit Data Centre Solutions Private Limited', 'U62010MH2024PTC100108', 'GST27SDC9017Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Aurora Analytics UK Limited', 'UK-99887766', 'GB-VA-9018', 'VERIFIED', 'CLEAR', 'COMPLETE', false),
('Vertex Industrial Traders Private Limited', 'U28999MH2020PTC100110', 'GST27VIT9019Z5A', 'VERIFIED', 'CLEAR', 'COMPLETE', false);

delete from sanctions_registry where entity_name in (
'Northstar Export Trading LLC',
'Orion Maritime Holdings',
'Redstone Defence Components'
);

insert into sanctions_registry (entity_name, country, match_type, active, reason) values
('Northstar Export Trading LLC', 'Fictionland', 'EXACT', true, 'Synthetic sanctions match for demo only'),
('Orion Maritime Holdings', 'Fictionland', 'EXACT', true, 'Synthetic sanctions match for demo only'),
('Redstone Defence Components', 'Fictionland', 'WATCHLIST', true, 'Synthetic watchlist entry for demo only');

insert into vendor_master_snapshot (
    vendor_id, legal_name, tax_id, bank_name, account_number, ifsc_swift, country
) values
('VEN-1001', 'Atlas Office Systems Private Limited', 'GST27ATL0001Z5A', 'Northwind Bank', '009876543210', 'NWBK0000123', 'India'),
('VEN-1002', 'Blue River Industrial Supply LLP', 'GST27BRI0002Z5A', 'Pioneer Bank', '001234567890', 'PNBK0000456', 'India'),
('VEN-1003', 'Harbor Safety Equipment India Private Limited', 'GST29HSE0003Z5A', 'Cedar Bank', '007654321098', 'CDBK0000789', 'India'),
('VEN-1004', 'Silverline Logistics Services Private Limited', 'GST27SLS0004Z5A', 'Northwind Bank', '003456789012', 'NWBK0000123', 'India')
on conflict (vendor_id) do update set
legal_name = excluded.legal_name,
tax_id = excluded.tax_id,
bank_name = excluded.bank_name,
account_number = excluded.account_number,
ifsc_swift = excluded.ifsc_swift,
country = excluded.country;
