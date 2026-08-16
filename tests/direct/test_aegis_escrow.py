import json
import pytest


def test_escrow_lifecycle_and_adjudication(direct_vm, direct_deploy, direct_alice, direct_bob):
    """
    Test full lifecycle of AegisEscrow:
    1. Alice (Client) creates escrow agreement locking 100 GEN for Bob (Contractor).
    2. Alice defines a verifiable milestone with payout of 50 GEN.
    3. Bob submits milestone evidence.
    4. GenLayer validators fetch web evidence, execute multi-axis LLM adjudication,
       reach consensus on passing scores, and deterministically release 50 GEN payout.
    """
    contract = direct_deploy("contracts/aegis_escrow.py")

    # Step 1: Alice creates agreement and deposits 100 GEN (100 * 10^18 wei)
    deposit_val = 100 * 10**18
    direct_vm.sender = direct_alice
    direct_vm.value = deposit_val

    ag_id = contract.create_agreement(str(direct_bob))
    assert ag_id == 0

    ag = contract.get_agreement(ag_id)
    assert ag["client"].lower() == str(direct_alice).lower()
    assert ag["contractor"].lower() == str(direct_bob).lower()
    assert ag["total_locked"] == str(deposit_val)
    assert ag["remaining_balance"] == str(deposit_val)
    assert ag["is_active"] is True
    assert ag["milestone_count"] == 0

    # Step 2: Alice adds a milestone
    mayout_val = 50 * 10**18
    m_idx = contract.add_milestone(
        ag_id,
        "Implement and test decentralized permit validation in SDK core.",
        "https://api.github.com/repos/sample/sdk/pulls/123",
        mayout_val,
    )
    assert m_idx == 0

    m_info = contract.get_milestone(ag_id, m_idx)
    assert m_info["status"] == "PENDING"
    assert m_info["payout_amount"] == str(mayout_val)

    # Step 3: Setup Mock Web & LLM responses for GenLayer consensus
    direct_vm.mock_web(
        r".*github\.com.*",
        {
            "status": 200,
            "body": json.dumps({
                "title": "feat: permit validation",
                "state": "closed",
                "merged": True,
                "changed_files": 5,
                "additions": 140,
                "deletions": 10,
            }),
        },
    )

    direct_vm.mock_llm(
        r".*GenLayer Decentralized Escrow Adjudicator.*",
        json.dumps({
            "functional_score": 92,
            "criteria_score": 88,
            "quality_score": 95,
            "defect_severity": "NONE",
            "approved": True,
            "summary": "PR #123 successfully implemented and merged all permit expiration logic with full test suite.",
        }),
    )

    # Step 4: Bob triggers adjudication
    direct_vm.sender = direct_bob
    direct_vm.value = 0

    contract.submit_and_adjudicate_milestone(
        ag_id, m_idx, "PR is merged, 24 unit tests passing in CI."
    )

    # Step 5: Verify milestone is APPROVED and remaining balance is deducted
    m_after = contract.get_milestone(ag_id, m_idx)
    assert m_after["status"] == "APPROVED"
    assert m_after["score_functional"] == 92
    assert m_after["score_criteria"] == 88
    assert m_after["score_quality"] == 95
    assert m_after["defect_severity"] == "NONE"

    ag_after = contract.get_agreement(ag_id)
    assert ag_after["remaining_balance"] == str(deposit_val - mayout_val)


def test_milestone_rejection_on_low_quality(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Test that deliverables failing quality thresholds are flagged as REVISION_REQUIRED without releasing funds."""
    contract = direct_deploy("contracts/aegis_escrow.py")

    deposit_val = 100 * 10**18
    direct_vm.sender = direct_alice
    direct_vm.value = deposit_val

    ag_id = contract.create_agreement(str(direct_bob))
    m_idx = contract.add_milestone(
        ag_id,
        "Deliver complete documentation with interactive examples.",
        "https://example.com/incomplete-doc",
        50 * 10**18,
    )

    # Mock failing evaluation
    direct_vm.mock_web(r".*", {"status": 404, "body": "Page Not Found"})
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "functional_score": 35,
            "criteria_score": 40,
            "quality_score": 30,
            "defect_severity": "HIGH",
            "approved": False,
            "summary": "Evidence URL returned 404 and deliverable criteria was not demonstrated.",
        }),
    )

    direct_vm.sender = direct_bob
    direct_vm.value = 0
    contract.submit_and_adjudicate_milestone(ag_id, m_idx, "Please check documentation.")

    m_after = contract.get_milestone(ag_id, m_idx)
    assert m_after["status"] == "REVISION_REQUIRED"

    # Escrow balance remains untouched
    ag_after = contract.get_agreement(ag_id)
    assert ag_after["remaining_balance"] == str(deposit_val)


def test_refund_unclaimed_balance(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    """Test that only the client can reclaim unspent funds and unauthorized callers are reverted."""
    contract = direct_deploy("contracts/aegis_escrow.py")

    deposit_val = 50 * 10**18
    direct_vm.sender = direct_alice
    direct_vm.value = deposit_val
    ag_id = contract.create_agreement(str(direct_bob))

    # Charlie tries to refund Alice's agreement -> should fail
    direct_vm.sender = direct_charlie
    direct_vm.value = 0
    with direct_vm.expect_revert("Only the client can request a balance refund."):
        contract.refund_remaining(ag_id)

    # Alice successfully reclaims funds
    direct_vm.sender = direct_alice
    contract.refund_remaining(ag_id)

    ag = contract.get_agreement(ag_id)
    assert ag["remaining_balance"] == "0"
    assert ag["is_active"] is False
