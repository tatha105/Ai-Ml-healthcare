"""LangGraph claim flow. This is the order of work for one admission.

    load_contract → load_wording → extract_form → check_eligibility
           check passed → assess_coverage → route_outcome → persist_claim
           check failed → route_outcome → persist_claim

load_contract reads Azure SQL. load_wording reads Cosmos DB.
extract_form uses Azure AI Document Intelligence when a file is sent.
assess_coverage calls LangChain, which calls Azure OpenAI GPT-5.1 when configured.
A failed eligibility check skips assess_coverage.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.runtime import Stores


class ClaimState(TypedDict, total=False):
    """Fields passed from one graph step to the next. trace grows by one note per step."""
    claim_id: str
    admission_id: str
    contract: dict
    clauses: list[dict]
    extracted: dict
    eligibility: dict
    assessment: dict
    decision: dict
    trace: Annotated[list[dict], operator.add]


def _note(node: str, summary: str) -> dict:
    """One line in the trace the desk shows under Graph."""
    return {"node": node, "summary": summary}


def build_claim_graph(stores: Stores):
    """Wire the seven steps and return a compiled graph. main.create_claim calls invoke."""

    def load_contract(state: ClaimState) -> dict:
        """Step 1. Read the member, policy, hospital, and admission from SQL."""
        contract = stores.sql.load_contract(state["admission_id"])
        return {
            "contract": contract,
            "trace": [
                _note(
                    "load_contract",
                    f"Loaded {contract['policy_number']} ({contract['plan_name']}) and {contract['hospital_name']}.",
                )
            ],
        }

    def load_wording(state: ClaimState) -> dict:
        """Step 2. Read that plan's clause text from Cosmos DB."""
        plan_code = state["contract"]["plan_code"]
        clauses = stores.cosmos.clauses_for_plan(plan_code)
        return {
            "clauses": clauses,
            "trace": [_note("load_wording", f"Loaded {len(clauses)} clauses for plan {plan_code}.")],
        }

    def extract_form(state: ClaimState) -> dict:
        """Step 3. Read the admission form. Pasted text locally, Document Intelligence for a file."""
        contract = state["contract"]
        extracted = stores.documents.extract(contract["document_name"], contract["document_text"])
        if extracted["usable"]:
            summary = f"Read {extracted['document_name']} with the {extracted['provider']} reader."
        else:
            summary = "The admission form has no legible text."
        return {"extracted": extracted, "trace": [_note("extract_form", summary)]}

    def check_eligibility(state: ClaimState) -> dict:
        """Step 4. Apply the hard policy rules. Continue means the model may run."""
        eligibility = _eligibility(state["contract"], state["extracted"])
        if eligibility["decision"] == "Continue":
            summary = "Eligibility passed. Coverage assessment can run."
        elif eligibility["decision"] == "Referred":
            summary = "Eligibility stopped the claim before coverage assessment. The form needs review."
        else:
            summary = f"Eligibility stopped the claim before coverage assessment. {eligibility['reason']}"
        return {"eligibility": eligibility, "trace": [_note("check_eligibility", summary)]}

    def assess_coverage(state: ClaimState) -> dict:
        """Step 5. Ask LangChain for Approved or Partial. Skipped when step 4 did not continue."""
        contract = state["contract"]
        payload = {
            "facts": {
                "member_name": contract["member_name"],
                "policy_number": contract["policy_number"],
                "plan_name": contract["plan_name"],
                "hospital_name": contract["hospital_name"],
                "in_network": contract["in_network"],
                "admitted_at": contract["admitted_at"],
                "diagnosis": contract["diagnosis"],
                "treatment": contract["treatment"],
                "estimated_amount": contract["estimated_amount"],
                "room_rent_per_day": contract["room_rent_per_day"],
                "room_rent_cap": contract["room_rent_cap"],
                "stay_days": contract["stay_days"],
                "sum_insured": contract["sum_insured"],
                "amount_used": contract["amount_used"],
                "admission_form": state["extracted"]["text"],
            },
            "clauses": [
                {"clause_id": clause["clause_id"], "title": clause["title"], "text": clause["text"]}
                for clause in state["clauses"]
            ],
        }
        assessment = stores.assess(payload)
        provider = assessment.get("provider") or "rules"
        who = "Azure OpenAI" if provider == "azure-openai" else "The rule assessor"
        return {
            "assessment": assessment,
            "trace": [
                _note(
                    "assess_coverage",
                    f"{who} recommended {assessment['outcome']}.",
                )
            ],
        }

    def route_outcome(state: ClaimState) -> dict:
        """Step 6. Pick Approved, Partial, Denied, or Referred."""
        decision = _route(state)
        return {
            "decision": decision,
            "trace": [_note("route_outcome", f"Routed the claim to {decision['outcome']}.")],
        }

    def persist_claim(state: ClaimState) -> dict:
        """Step 7. Write amounts to SQL and the rationale packet to Cosmos."""
        decision = state["decision"]
        cited_ids = decision["cited_clause_ids"]
        by_id = {clause["clause_id"]: clause for clause in state.get("clauses") or []}
        cited = [
            {"clause_id": clause_id, "title": by_id[clause_id]["title"], "text": by_id[clause_id]["text"]}
            for clause_id in cited_ids
            if clause_id in by_id
        ]
        stores.sql.save_decision(
            state["claim_id"],
            {
                "outcome": decision["outcome"],
                "payable_amount": decision["payable_amount"],
                "patient_share": decision["patient_share"],
                "confidence": decision.get("confidence"),
                "coverage_provider": decision["coverage_provider"],
            },
        )
        stores.cosmos.save_packet(
            {
                "id": state["claim_id"],
                "claim_id": state["claim_id"],
                "plan_code": state["contract"]["plan_code"],
                "rationale": decision["rationale"],
                "cited_clause_ids": cited_ids,
                "cited_clauses": cited,
                "checks": state["eligibility"]["checks"],
                "trace": list(state.get("trace") or [])
                + [_note("persist_claim", "Saved the claim amounts and the decision packet.")],
                "coverage_provider": decision["coverage_provider"],
                "confidence": decision.get("confidence"),
            }
        )
        return {"trace": [_note("persist_claim", "Saved the claim amounts and the decision packet.")]}

    def after_eligibility(state: ClaimState) -> str:
        """Send a passed claim to the model. Send a failed claim straight to routing."""
        if state["eligibility"]["decision"] == "Continue":
            return "assess_coverage"
        return "route_outcome"

    graph = StateGraph(ClaimState)
    graph.add_node("load_contract", load_contract)
    graph.add_node("load_wording", load_wording)
    graph.add_node("extract_form", extract_form)
    graph.add_node("check_eligibility", check_eligibility)
    graph.add_node("assess_coverage", assess_coverage)
    graph.add_node("route_outcome", route_outcome)
    graph.add_node("persist_claim", persist_claim)
    graph.set_entry_point("load_contract")
    graph.add_edge("load_contract", "load_wording")
    graph.add_edge("load_wording", "extract_form")
    graph.add_edge("extract_form", "check_eligibility")
    graph.add_conditional_edges(
        "check_eligibility",
        after_eligibility,
        {"assess_coverage": "assess_coverage", "route_outcome": "route_outcome"},
    )
    graph.add_edge("assess_coverage", "route_outcome")
    graph.add_edge("route_outcome", "persist_claim")
    graph.add_edge("persist_claim", END)
    return graph.compile()


def _eligibility(contract: dict, extracted: dict) -> dict:
    """Run the five hard checks in order. The first failure decides the outcome.

    Order: policy in force, specified-illness wait, exclusion keyword,
    network hospital, legible admission form. A form problem is Referred.
    The other failures are Denied. All clear returns Continue.
    """
    admitted = datetime.fromisoformat(contract["admitted_at"]).date()
    start = date.fromisoformat(contract["effective_from"])
    end = date.fromisoformat(contract["effective_to"])
    in_force = contract["status"] == "active" and start <= admitted <= end
    checks = [
        {
            "name": "Policy in force",
            "result": "pass" if in_force else "fail",
            "detail": (
                f"{contract['policy_number']} is active from {start.isoformat()} to {end.isoformat()}."
                if in_force
                else f"{contract['policy_number']} is not in force on {admitted.isoformat()}."
            ),
        }
    ]
    narrative = f"{contract['diagnosis']} {contract['treatment']}".lower()
    waiting_hit = None
    exclusion_hit = None
    for rule in contract["exclusions"]:
        if rule["keyword"].lower() not in narrative:
            continue
        if rule["kind"] == "exclude":
            exclusion_hit = rule
        elif rule["kind"] == "waiting":
            days_in_force = (admitted - start).days
            if days_in_force < int(rule["waiting_days"]):
                waiting_hit = {**rule, "days_in_force": days_in_force}
    checks.append(
        {
            "name": "Specified illness",
            "result": "fail" if waiting_hit else "pass",
            "detail": (
                f"{waiting_hit['keyword'].title()} is inside a {waiting_hit['waiting_days']}-day wait. "
                f"The policy has been in force for {waiting_hit['days_in_force']} days."
                if waiting_hit
                else "No specified-illness wait applies to this admission."
            ),
        }
    )
    checks.append(
        {
            "name": "Exclusions",
            "result": "fail" if exclusion_hit else "pass",
            "detail": (
                f"The admission matches the excluded term '{exclusion_hit['keyword']}'."
                if exclusion_hit
                else "No listed exclusion matches this admission."
            ),
        }
    )
    checks.append(
        {
            "name": "Network hospital",
            "result": "pass" if contract["in_network"] else "fail",
            "detail": (
                f"{contract['hospital_name']} is a network hospital."
                if contract["in_network"]
                else f"{contract['hospital_name']} is outside the network."
            ),
        }
    )
    usable = bool(extracted.get("usable"))
    checks.append(
        {
            "name": "Admission form",
            "result": "pass" if usable else "refer",
            "detail": (
                f"{extracted.get('document_name')} has legible text."
                if usable
                else "The admission form has no legible text."
            ),
        }
    )

    if not in_force:
        return _stop("Denied", checks[0]["detail"], ["CL-TERM"], checks)
    if waiting_hit:
        return _stop("Denied", checks[1]["detail"], [waiting_hit["clause_id"]], checks)
    if exclusion_hit:
        return _stop("Denied", checks[2]["detail"], [exclusion_hit["clause_id"]], checks)
    if not contract["in_network"]:
        return _stop("Denied", checks[3]["detail"], ["CL-NET"], checks)
    if not usable:
        return _stop("Referred", checks[4]["detail"], ["CL-FORM"], checks)
    return {"decision": "Continue", "reason": "Eligibility passed.", "clause_ids": [], "checks": checks}


def _stop(decision: str, reason: str, clause_ids: list[str], checks: list[dict]) -> dict:
    """Package a Denied or Referred stop, including every check that was recorded."""
    return {"decision": decision, "reason": reason, "clause_ids": clause_ids, "checks": checks}


def _route(state: ClaimState) -> dict:
    """Turn eligibility, or the model answer, into the outcome that gets saved.

    An eligibility stop keeps payable amounts at 0 and does not call the model.
    A model answer with no matching clause, or confidence under 0.55, becomes Referred.
    """
    eligibility = state["eligibility"]
    if eligibility["decision"] in {"Denied", "Referred"}:
        outcome = eligibility["decision"]
        return {
            "outcome": outcome,
            "payable_amount": 0,
            "patient_share": 0,
            "confidence": None,
            "rationale": eligibility["reason"],
            "cited_clause_ids": eligibility["clause_ids"],
            "coverage_provider": "not_called",
        }
    assessment = state["assessment"]
    outcome = assessment["outcome"]
    cited = assessment["cited_clause_ids"]
    rationale = assessment["rationale"]
    confidence = assessment["confidence"]
    if outcome in {"Approved", "Partial", "Denied"} and not cited:
        outcome = "Referred"
        rationale = f"{rationale} No cited clause matched the policy wording, so the claim is referred."
    elif confidence is not None and confidence < 0.55 and outcome != "Referred":
        outcome = "Referred"
        rationale = f"{rationale} Confidence is below the review threshold, so an officer needs to decide."
    payable = 0 if outcome in {"Denied", "Referred"} else assessment["payable_amount"]
    patient = 0 if outcome in {"Denied", "Referred"} else assessment["patient_share"]
    return {
        "outcome": outcome,
        "payable_amount": payable,
        "patient_share": patient,
        "confidence": confidence,
        "rationale": rationale,
        "cited_clause_ids": cited,
        "coverage_provider": assessment.get("provider") or "rules",
    }
