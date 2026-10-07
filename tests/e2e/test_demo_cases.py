import json
from argparse import Namespace
from pathlib import Path

import pytest

from app.cli import _run_case

CASES = Path(__file__).resolve().parents[2] / "demo" / "cases"


@pytest.mark.parametrize("case", sorted(path.name for path in CASES.iterdir() if path.is_dir()))
def test_all_cases_have_local_and_fake_live_business_parity(case, capsys):
    outcomes = []
    for mode in ("local", "fake-live"):
        _run_case(case, Namespace(
            repo="memory", provider="mock", verification_mode=mode,
            approve_all=False, json=True,
        ))
        outcomes.append(json.loads(capsys.readouterr().out))

    local, fake_live = outcomes
    assert local["assessment"]["recommended_next_action"] == fake_live["assessment"]["recommended_next_action"]
    assert local["assessment"]["risk_assessment"]["risk"]["score"] == fake_live["assessment"]["risk_assessment"]["risk"]["score"]
    assert local["assessment"]["risk_assessment"]["risk"]["label"] == fake_live["assessment"]["risk_assessment"]["risk"]["label"]
    assert local["assessment"]["risk_assessment"]["risk"]["hard_blocks"] == fake_live["assessment"]["risk_assessment"]["risk"]["hard_blocks"]
    local_codes = sorted(item["code"] for item in local["assessment"]["validation_findings"])
    fake_codes = sorted(item["code"] for item in fake_live["assessment"]["validation_findings"])
    assert local_codes == fake_codes
    assert local["status"] == fake_live["status"]
    assert {item["mode"] for item in local["assessment"]["verification_summary"]} <= {"LOCAL_SIMULATED"}
    configured = [item for item in fake_live["assessment"]["verification_summary"] if item["provider_name"] != "input_gate"]
    assert {item["mode"] for item in configured} <= {"LIVE"}

    expected = json.loads((CASES / case / "expected_result.json").read_text(encoding="utf-8"))
    assert local["assessment"]["recommended_next_action"] == expected["recommended_next_action"]
    assert local["status"] == expected["workflow_status"]
    assert local["assessment"]["risk_assessment"]["risk"]["score"] == expected["risk_score"]
    assert local["assessment"]["risk_assessment"]["risk"]["label"] == expected["risk_label"]
    assert sorted(local_codes) == sorted(expected["finding_codes"])
    assert [stage for stage in local["review_package"]["required_stages"]] == expected["required_approval_stages"]
    assert bool(local["assessment"]["risk_assessment"]["risk"]["hard_blocks"]) == expected["hard_blocked"]


def _run(case, capsys, *, mode="local", approve=False):
    _run_case(case, Namespace(
        repo="memory", provider="mock", verification_mode=mode,
        approve_all=approve, json=True,
    ))
    return json.loads(capsys.readouterr().out)


def test_clean_lifecycle_masks_account_and_requires_real_policy_stages(capsys):
    result = _run("clean_supplier", capsys, approve=True)
    serialized = json.dumps(result)
    assert result["status"] == "DRAFTS_GENERATED"
    assert "123456789012" not in serialized
    assert result["drafts"]["vendor"]["bank"]["account_number_masked"] == "****9012"
    assert [entry["status"] for entry in result["approvals"]] == ["PENDING_BUDGET", "APPROVED"]
    assert "LOCAL_SIMULATED" in serialized


def test_hard_block_and_provider_failure_do_not_approve(capsys):
    blocked = _run("duplicate_tax_id", capsys)
    assert blocked["status"] == "BLOCKED"
    assert blocked["approvals"] == []
    assert blocked["drafts"] == {"vendor": None, "purchase_order": None}

    unavailable = _run("bank_verification_unavailable", capsys)
    assert unavailable["assessment"]["recommended_next_action"] == "MANUAL_REVIEW"
    assert unavailable["status"] == "NEEDS_MANUAL_REVIEW"
    assert unavailable["approvals"] == []


def test_high_value_demo_requires_finance_head_before_drafts(capsys):
    result = _run("high_value_purchase", capsys, approve=True)
    assert result["status"] == "DRAFTS_GENERATED"
    assert [item["stage"] for item in result["report"]["approvals"]] == [
        "PROCUREMENT", "BUDGET_OWNER", "FINANCE_HEAD",
    ]
    assert [item["status"] for item in result["approvals"]] == [
        "PENDING_BUDGET", "PENDING_FINANCE_HEAD", "APPROVED",
    ]
