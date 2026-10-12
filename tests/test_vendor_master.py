from app.repositories.vendor_repository import (
    _master_vendor_code,
    _master_verification_status,
    _normalize_categories,
)


def test_categories_are_normalized_and_deduplicated():
    assert _normalize_categories(
        "IT Hardware, Laptops, it hardware; Networking"
    ) == ["IT Hardware", "Laptops", "Networking"]


def test_master_vendor_code_is_stable_from_case_id():
    assert _master_vendor_code(
        "6dcd8d50-798a-4cd8-8d82-ac6227914033"
    ) == "VEN-6DCD8D50"


def test_human_override_is_visible_in_master_verification_status():
    assert _master_verification_status("APPROVED", "APPROVE") == "VERIFIED_WITH_OVERRIDE"
    assert _master_verification_status("APPROVED", None) == "VERIFIED"
    assert _master_verification_status("REVIEW_REQUIRED", None) == "PENDING"
