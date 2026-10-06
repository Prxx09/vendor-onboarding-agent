# Vendor onboarding test data assessment

## Scope

This pack contains 14 synthetic cases and 50 top-level source files: ten scenarios from the supplied pack (46 files) and four new source files matching VO-1001 through VO-1004. The VO-1002 top-level source is a ZIP containing a filled intake PDF, a blurred cheque image, and a note describing intentionally missing evidence.

## Document inspection

The original 46 files were opened by type. The PDFs contain selectable text; DOCX and XLSX values are in tables; the PNG/JPG samples were readable with OCR. Missing certificates and cross-document mismatches are deliberate negative tests. The four showcase source filenames previously existed only as metadata. Matching synthetic files are now included.

| Case | Evidence under test | Expected state |
| --- | --- | --- |
| VO-1001 | Complete registration, tax, bank, declarations | Auto-approved, 94% |
| VO-1002 | Missing MSME certificate, blurred cheque, declaration review | Human review, 71% |
| VO-1003 | Complete KYC and accepted security acknowledgement | Auto-approved, 89% |
| VO-1004 | Unreadable registration, invalid tax, bank holder mismatch, missing declarations | Rejected, 52% |
| clean_supplier | Complete vendor and purchase evidence | Pending procurement |
| missing_tax_certificate | Tax certificate deliberately absent | Rework |
| duplicate_tax_id | Tax ID already in reference data | Blocked |
| similar_supplier_name | Similar supplier in master data | Pending procurement |
| bank_name_mismatch | Bank letter holder differs from submitted supplier | Blocked |
| expired_registration | Registration certificate expired | Rework |
| sanctions_match | Name in synthetic sanctions list | Blocked |
| high_value_purchase | Finance threshold exceeded | Pending finance head |
| international_supplier | UK supplier with SWIFT and USD evidence | Pending procurement |
| multiple_issues | Missing tax, unknown bank, holder mismatch | Blocked |

## Functional boundary

The current FastAPI upload endpoint calls `simulate_document_extraction(filename, category)`, which derives fields from the filename and does not read document bytes. Validation checks use entered field shapes and a name-based demo sanctions trigger. The expected results in the ten-scenario pack belong to a richer reference workflow; they are not assertions that this app currently satisfies. This pack can exercise upload, storage, form review, document access, case display, and audit presentation. It cannot demonstrate real PDF/OCR/DOCX/XLSX extraction, document completeness checks, duplicate screening, sanctions reference matching, expiry comparison, bank holder matching, or approval routing from purchase values until those features are implemented.

The four original showcase records have fixed display scores. Their attached PDFs/ZIP are synthetic evidence aligned to those displayed values, not proof that the current scoring code derives them from the bytes.

## Handling

All files are fictional test data. The documents include visible synthetic-use labels. No real vendor identity or banking details should be inferred from these fixtures.
