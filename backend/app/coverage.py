"""Coverage decision after eligibility has passed.

Locally rule_assess applies the room-rent cap and the sum insured.
With Azure OpenAI credentials, LangChain sends the same facts to GPT-5.1.
"""

from __future__ import annotations

import json
from typing import Callable

from pydantic import BaseModel, Field

from app.config import Settings


class CoverageDecision(BaseModel):
    """JSON shape GPT-5.1 must return. rule_assess returns the same keys."""

    outcome: str = Field(description="Approved, Partial, Denied, or Referred")
    payable_amount: float
    patient_share: float
    confidence: float = Field(description="0 to 1")
    rationale: str
    cited_clause_ids: list[str]


SYSTEM_PROMPT = """You adjudicate a synthetic hospital cashless claim for an officer to confirm.
Use only the clauses provided. Do not invent benefits, hospitals, or amounts.
Choose one outcome: Approved, Partial, Denied, or Referred.
Approved means the estimate is payable in full and patient_share is 0.
Partial means a cap leaves a patient share. payable_amount plus patient_share equals the estimated amount.
Denied means the policy does not cover this admission. Both amounts are 0.
Referred means the clauses are insufficient. Use confidence below 0.5.
Cite clause ids exactly as given. Amounts are INR numbers."""


def rule_assess(payload: dict) -> dict:
    """Decide Approved or Partial from the room-rent cap and the remaining sum insured.

    Room rent above the cap is the member's share and cites CL-ROOM.
    A bill above the remaining sum insured cites CL-SUM. Otherwise the
    estimate is Approved and cites CL-SURG. provider is "rules".
    """
    facts = payload["facts"]
    clauses = payload["clauses"]
    known = {clause["clause_id"] for clause in clauses}
    estimated = float(facts["estimated_amount"])
    cap = float(facts["room_rent_cap"])
    room = float(facts["room_rent_per_day"])
    days = int(facts["stay_days"])
    remaining = max(0.0, float(facts["sum_insured"]) - float(facts["amount_used"]))
    room_excess = round(max(0.0, room - cap) * days, 2)
    covered = max(0.0, estimated - room_excess)
    cites = ["CL-SURG"]
    if room_excess > 0 and "CL-ROOM" in known:
        cites.append("CL-ROOM")
    if covered > remaining:
        payable = round(remaining, 2)
        patient = round(estimated - remaining, 2)
        if "CL-SUM" in known:
            cites.append("CL-SUM")
        limit_note = f" The remaining sum insured is Rs {remaining:,.0f}."
    else:
        payable = round(covered, 2)
        patient = round(room_excess, 2)
        limit_note = ""
    outcome = "Partial" if patient > 0 else "Approved"
    if room_excess > 0:
        rationale = (
            f"Inpatient treatment is covered. Room rent of Rs {room:,.0f} per day "
            f"is above the Rs {cap:,.0f} cap, so Rs {room_excess:,.0f} is the member's share "
            f"over {days} days. Payable amount is Rs {payable:,.0f}.{limit_note}"
        )
    else:
        rationale = (
            f"Inpatient treatment at a network hospital is covered. "
            f"Room rent is within the Rs {cap:,.0f} daily cap. Payable amount is Rs {payable:,.0f}.{limit_note}"
        )
    return {
        "outcome": outcome,
        "payable_amount": payable,
        "patient_share": patient,
        "confidence": 0.9,
        "rationale": rationale.strip(),
        "cited_clause_ids": [clause_id for clause_id in cites if clause_id in known],
        "provider": "rules",
    }


def _normalize(result: CoverageDecision | dict, known_ids: set[str]) -> dict:
    """Clean a GPT-5.1 answer: keep only known clause ids, and force a known outcome."""
    data = result.model_dump() if isinstance(result, CoverageDecision) else dict(result)
    confidence = float(data.get("confidence") or 0)
    if confidence > 1:
        confidence = confidence / 100 if confidence <= 100 else 1
    confidence = min(1.0, max(0.0, confidence))
    cited = [clause_id for clause_id in data.get("cited_clause_ids") or [] if clause_id in known_ids]
    outcome = data.get("outcome") or "Referred"
    if outcome not in {"Approved", "Partial", "Denied", "Referred"}:
        outcome = "Referred"
    return {
        "outcome": outcome,
        "payable_amount": round(float(data.get("payable_amount") or 0), 2),
        "patient_share": round(float(data.get("patient_share") or 0), 2),
        "confidence": confidence,
        "rationale": (data.get("rationale") or "").strip(),
        "cited_clause_ids": cited,
        "provider": "azure-openai",
    }


def build_assessor(settings: Settings) -> tuple[Callable[[dict], dict], str]:
    """Return (assess function, mode name).

    No Azure OpenAI key: the function is rule_assess and the mode is "rules".
    With a key: LangChain pipes SYSTEM_PROMPT into AzureChatOpenAI for the
    gpt-5.1 deployment. If that call fails, assess falls back to rule_assess.
    """
    if not (settings.openai_endpoint and settings.openai_api_key):
        return rule_assess, "rules"
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import AzureChatOpenAI
    except Exception:
        return rule_assess, "rules"

    llm = AzureChatOpenAI(
        azure_endpoint=settings.openai_endpoint,
        api_key=settings.openai_api_key,
        azure_deployment=settings.openai_deployment,
        api_version=settings.openai_api_version,
    )
    structured = llm.with_structured_output(CoverageDecision)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "Facts:\n{facts}\n\nClauses:\n{clauses}"),
        ]
    )
    chain = prompt | structured
    mode = f"azure-openai:{settings.openai_deployment}"

    def assess(payload: dict) -> dict:
        """Call GPT-5.1. On any error, return the rule decision and say Azure was unavailable."""
        known_ids = {clause["clause_id"] for clause in payload["clauses"]}
        try:
            result = chain.invoke(
                {
                    "facts": json.dumps(payload["facts"], default=str),
                    "clauses": json.dumps(payload["clauses"], default=str),
                }
            )
            return _normalize(result, known_ids)
        except Exception as exc:
            fallback = rule_assess(payload)
            fallback["rationale"] = (
                f"{fallback['rationale']} Azure OpenAI was unavailable ({exc.__class__.__name__}), "
                "so the rule assessor produced this recommendation."
            )
            return fallback

    return assess, mode
