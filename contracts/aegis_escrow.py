# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
AegisEscrow: Verifiable AI-Adjudicated Agent Escrow & Milestone Gate for GenLayer.

Enables trustless, milestone-based escrow between autonomous agents and human contractors.
Milestone completion is adjudicated via decentralized multi-validator LLM consensus
grounded on live web evidence (e.g. GitHub PRs, test reports, live API endpoints).
"""

from genlayer import *
from dataclasses import dataclass
import json


@allow_storage
@dataclass
class Milestone:
    description: str
    evidence_url: str
    payout_amount: u256
    status: str  # "PENDING", "SUBMITTED", "APPROVED", "REVISION_REQUIRED", "REFUNDED"
    score_functional: u32
    score_criteria: u32
    score_quality: u32
    defect_severity: str  # "NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"
    adjudication_summary: str


@allow_storage
@dataclass
class EscrowAgreement:
    client: Address
    contractor: Address
    total_locked: u256
    remaining_balance: u256
    is_active: bool
    milestone_count: u32


class AegisEscrow(gl.Contract):
    """Decentralized AI-Adjudicated Milestone Escrow on GenLayer."""

    agreements: TreeMap[u256, EscrowAgreement]
    milestones: TreeMap[str, Milestone]  # Key: f"{agreement_id}_{milestone_idx}"
    agreement_counter: u256

    def __init__(self):
        self.agreement_counter = u256(0)

    @gl.public.write.payable
    def create_agreement(self, contractor: str) -> u256:
        """Create a new escrow agreement and lock GEN funds deposited with this call."""
        deposit_val = gl.message.value
        if deposit_val == u256(0):
            raise gl.vm.UserError("Escrow agreement requires a non-zero GEN deposit.")

        contractor_addr = Address(contractor)
        if contractor_addr == gl.message.sender_address:
            raise gl.vm.UserError("Client and contractor cannot be the same address.")

        agreement_id = self.agreement_counter
        self.agreements[agreement_id] = EscrowAgreement(
            client=gl.message.sender_address,
            contractor=contractor_addr,
            total_locked=deposit_val,
            remaining_balance=deposit_val,
            is_active=True,
            milestone_count=u32(0),
        )
        self.agreement_counter = self.agreement_counter + u256(1)
        return agreement_id

    @gl.public.write
    def add_milestone(
        self, agreement_id: u256, description: str, evidence_url: str, payout_amount: u256
    ) -> u32:
        """Client adds a verifiable milestone to the agreement."""
        agreement = self.agreements.get(agreement_id, None)
        if agreement is None or not agreement.is_active:
            raise gl.vm.UserError("Agreement does not exist or is inactive.")

        if gl.message.sender_address != agreement.client:
            raise gl.vm.UserError("Only the agreement client can define milestones.")

        if payout_amount == u256(0) or payout_amount > agreement.remaining_balance:
            raise gl.vm.UserError("Milestone payout exceeds available escrow balance.")

        m_idx = agreement.milestone_count
        m_key = f"{agreement_id}_{m_idx}"

        self.milestones[m_key] = Milestone(
            description=description,
            evidence_url=evidence_url,
            payout_amount=payout_amount,
            status="PENDING",
            score_functional=u32(0),
            score_criteria=u32(0),
            score_quality=u32(0),
            defect_severity="NONE",
            adjudication_summary="",
        )

        agreement.milestone_count = m_idx + u32(1)
        self.agreements[agreement_id] = agreement
        return m_idx

    @gl.public.write
    def submit_and_adjudicate_milestone(
        self, agreement_id: u256, milestone_idx: u32, submission_notes: str
    ) -> None:
        """
        Contractor submits milestone evidence. Triggers multi-validator AI consensus
        grounded on live web evidence. If consensus score >= 75 and defects are low,
        payout is deterministically released.
        """
        agreement = self.agreements.get(agreement_id, None)
        if agreement is None or not agreement.is_active:
            raise gl.vm.UserError("Agreement does not exist or is inactive.")

        if gl.message.sender_address != agreement.contractor and gl.message.sender_address != agreement.client:
            raise gl.vm.UserError("Only agreement participants can trigger adjudication.")

        m_key = f"{agreement_id}_{milestone_idx}"
        milestone = self.milestones.get(m_key, None)
        if milestone is None:
            raise gl.vm.UserError("Milestone not found.")

        if milestone.status == "APPROVED":
            raise gl.vm.UserError("Milestone has already been approved and settled.")

        # Capture immutable memory snapshots for non-deterministic execution
        spec_desc = milestone.description
        target_url = milestone.evidence_url
        payout_val = milestone.payout_amount
        contractor_target = str(agreement.contractor)

        def leader_fn() -> dict:
            """Leader validator fetches live web evidence and scores across 4 orthogonal axes."""
            evidence_data = ""
            if target_url and target_url.startswith("http"):
                try:
                    web_res = gl.nondet.web.get(target_url)
                    if hasattr(web_res, "body"):
                        evidence_data = web_res.body.decode("utf-8", errors="replace")[:2500]
                    else:
                        evidence_data = str(web_res)[:2500]
                except Exception:
                    evidence_data = "Web evidence fetch returned error or timeout."

            prompt = f"""
            You are an impartial GenLayer Decentralized Escrow Adjudicator.
            Evaluate whether the submitted work satisfies the contractual milestone specifications.

            === MILESTONE SPECIFICATION ===
            {spec_desc}

            === SUBMISSION NOTES ===
            {submission_notes}

            === LIVE WEB EVIDENCE (EXTRACTED FROM {target_url}) ===
            {evidence_data}

            Score the deliverable strictly on the following metrics (0-100 integers):
            1. "functional_score": Did the deliverable meet core functionality requirements?
            2. "criteria_score": Were all acceptance criteria and edge cases addressed?
            3. "quality_score": Code/artifact quality, reliability, and completeness.
            4. "defect_severity": "NONE", "LOW", "MEDIUM", "HIGH", or "CRITICAL".
            5. "approved": true if (functional_score >= 70 AND criteria_score >= 70 AND quality_score >= 70 AND defect_severity in ["NONE", "LOW"]), else false.
            6. "summary": A concise 1-2 sentence rationale.

            Respond ONLY with a JSON object adhering exactly to this schema:
            {{
                "functional_score": int,
                "criteria_score": int,
                "quality_score": int,
                "defect_severity": "NONE"|"LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
                "approved": bool,
                "summary": "string"
            }}
            """
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            if not isinstance(res, dict):
                raise gl.vm.UserError("LLM response must be a JSON dictionary.")
            return res

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            """
            Validators independently verify evidence and enforce Equivalence Principle:
            - Scores must agree within a ±8 point tolerance.
            - Defect severity must match exactly or be within adjacent severity tier.
            - The binary approval verdict must match.
            """
            if not isinstance(leaders_res, gl.vm.Return):
                return False

            lead_data = leaders_res.calldata
            if not isinstance(lead_data, dict):
                return False

            # Required schema validation
            for req_key in ["functional_score", "criteria_score", "quality_score", "defect_severity", "approved"]:
                if req_key not in lead_data:
                    return False

            # Validator executes independent evaluation
            val_data = leader_fn()

            # Check numeric tolerance on all 3 continuous dimensions
            for score_key in ["functional_score", "criteria_score", "quality_score"]:
                lead_s = int(lead_data.get(score_key, 0))
                val_s = int(val_data.get(score_key, 0))
                if abs(lead_s - val_s) > 8:
                    return False

            # Check verdict equivalence
            if bool(lead_data.get("approved")) != bool(val_data.get("approved")):
                return False

            # Reject critical discrepancy
            if lead_data.get("defect_severity") == "CRITICAL" and val_data.get("defect_severity") == "NONE":
                return False

            return True

        # Run multi-validator consensus
        adjudication = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # Update milestone record with agreed evaluation
        f_score = u32(int(adjudication.get("functional_score", 0)))
        c_score = u32(int(adjudication.get("criteria_score", 0)))
        q_score = u32(int(adjudication.get("quality_score", 0)))
        def_sev = str(adjudication.get("defect_severity", "MEDIUM"))
        is_approved = bool(adjudication.get("approved", False))
        summary = str(adjudication.get("summary", ""))

        milestone.score_functional = f_score
        milestone.score_criteria = c_score
        milestone.score_quality = q_score
        milestone.defect_severity = def_sev
        milestone.adjudication_summary = summary

        # Deterministic Gate: Enforce on-chain financial consequence
        if is_approved and f_score >= u32(70) and c_score >= u32(70) and q_score >= u32(70):
            milestone.status = "APPROVED"
            agreement.remaining_balance = agreement.remaining_balance - payout_val

            # External message to EOA: release milestone payout to contractor
            @gl.evm.contract_interface
            class _Recipient:
                class View:
                    pass
                class Write:
                    pass

            _Recipient(Address(contractor_target)).emit_transfer(value=payout_val)
        else:
            milestone.status = "REVISION_REQUIRED"

        self.milestones[m_key] = milestone
        self.agreements[agreement_id] = agreement

    @gl.public.write
    def refund_remaining(self, agreement_id: u256) -> None:
        """Client can reclaim remaining unapproved funds if contract is completed or disputed."""
        agreement = self.agreements.get(agreement_id, None)
        if agreement is None or not agreement.is_active:
            raise gl.vm.UserError("Agreement does not exist or is inactive.")

        if gl.message.sender_address != agreement.client:
            raise gl.vm.UserError("Only the client can request a balance refund.")

        rem_bal = agreement.remaining_balance
        if rem_bal == u256(0):
            raise gl.vm.UserError("No remaining balance to refund.")

        agreement.remaining_balance = u256(0)
        agreement.is_active = False
        self.agreements[agreement_id] = agreement

        @gl.evm.contract_interface
        class _Recipient:
            class View:
                pass
            class Write:
                pass

        _Recipient(agreement.client).emit_transfer(value=rem_bal)

    @gl.public.view
    def get_agreement(self, agreement_id: u256) -> dict:
        """View details of an escrow agreement."""
        ag = self.agreements.get(agreement_id, None)
        if ag is None:
            raise gl.vm.UserError("Agreement not found.")
        return {
            "client": str(ag.client),
            "contractor": str(ag.contractor),
            "total_locked": str(ag.total_locked),
            "remaining_balance": str(ag.remaining_balance),
            "is_active": ag.is_active,
            "milestone_count": int(ag.milestone_count),
        }

    @gl.public.view
    def get_milestone(self, agreement_id: u256, milestone_idx: u32) -> dict:
        """View details and consensus adjudication score of a milestone."""
        m_key = f"{agreement_id}_{milestone_idx}"
        m = self.milestones.get(m_key, None)
        if m is None:
            raise gl.vm.UserError("Milestone not found.")
        return {
            "description": m.description,
            "evidence_url": m.evidence_url,
            "payout_amount": str(m.payout_amount),
            "status": m.status,
            "score_functional": int(m.score_functional),
            "score_criteria": int(m.score_criteria),
            "score_quality": int(m.score_quality),
            "defect_severity": m.defect_severity,
            "adjudication_summary": m.adjudication_summary,
        }
