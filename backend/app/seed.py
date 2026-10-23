"""Synthetic members, hospitals, and policy wording. Not real patients.

SqlStore.init copies MEMBERS, HOSPITALS, and EXCLUSIONS into SQL.
seed_clauses is what Cosmos stores as the policy text the model may cite.
"""

from __future__ import annotations

MEMBERS = [
    {
        "id": "MBR-1001",
        "name": "Ananya Shah",
        "policy_number": "POL-1001",
        "plan_code": "GOLD",
        "plan_name": "Gold",
        "sum_insured": 500000,
        "amount_used": 0,
        "room_rent_cap": 5000,
        "effective_from": "2024-04-01",
        "effective_to": "2027-03-31",
    },
    {
        "id": "MBR-1002",
        "name": "Rohan Iyer",
        "policy_number": "POL-1002",
        "plan_code": "SILVER",
        "plan_name": "Silver",
        "sum_insured": 300000,
        "amount_used": 0,
        "room_rent_cap": 3000,
        "effective_from": "2025-01-01",
        "effective_to": "2026-12-31",
    },
    {
        "id": "MBR-1003",
        "name": "Meera Das",
        "policy_number": "POL-1003",
        "plan_code": "GOLD-NEW",
        "plan_name": "Gold (new)",
        "sum_insured": 500000,
        "amount_used": 0,
        "room_rent_cap": 5000,
        "effective_from": "2026-09-01",
        "effective_to": "2027-08-31",
    },
    {
        "id": "MBR-1004",
        "name": "Vikram Nair",
        "policy_number": "POL-1004",
        "plan_code": "GOLD",
        "plan_name": "Gold",
        "sum_insured": 500000,
        "amount_used": 0,
        "room_rent_cap": 5000,
        "effective_from": "2024-01-01",
        "effective_to": "2026-12-31",
    },
]

HOSPITALS = [
    {"id": "HSP-CITY", "name": "CityCare Hospital", "city": "Pune", "in_network": True},
    {"id": "HSP-LAKE", "name": "Lakeside Clinic", "city": "Nashik", "in_network": False},
]

EXCLUSIONS = [
    {"plan_code": "GOLD", "keyword": "cosmetic", "kind": "exclude", "waiting_days": None, "clause_id": "CL-EXCL"},
    {"plan_code": "SILVER", "keyword": "cosmetic", "kind": "exclude", "waiting_days": None, "clause_id": "CL-EXCL"},
    {"plan_code": "GOLD-NEW", "keyword": "cosmetic", "kind": "exclude", "waiting_days": None, "clause_id": "CL-EXCL"},
    {
        "plan_code": "GOLD-NEW",
        "keyword": "arthroscopy",
        "kind": "waiting",
        "waiting_days": 90,
        "clause_id": "CL-WAIT",
    },
]


def _common_clauses(plan_code: str, room_cap: int, with_wait: bool) -> list[dict]:
    """Build the clause documents for one plan. The room-rent sentence uses that plan's cap."""
    clauses = [
        {
            "clause_id": "CL-TERM",
            "plan_code": plan_code,
            "title": "Policy in force",
            "text": "Cashless admission is available only while the policy is in force on the admission date.",
        },
        {
            "clause_id": "CL-NET",
            "plan_code": plan_code,
            "title": "Network hospital",
            "text": "Cashless admission is limited to network hospitals. Treatment at a non-network hospital is not payable under cashless.",
        },
        {
            "clause_id": "CL-SURG",
            "plan_code": plan_code,
            "title": "Inpatient treatment",
            "text": "Medically necessary inpatient treatment is payable up to the remaining sum insured.",
        },
        {
            "clause_id": "CL-ROOM",
            "plan_code": plan_code,
            "title": "Room rent cap",
            "text": f"Room rent is payable up to Rs {room_cap:,} per day. Rent above the cap is the member's share.",
        },
        {
            "clause_id": "CL-SUM",
            "plan_code": plan_code,
            "title": "Sum insured",
            "text": "The payable amount cannot exceed the sum insured remaining on the admission date.",
        },
        {
            "clause_id": "CL-FORM",
            "plan_code": plan_code,
            "title": "Admission form",
            "text": "A legible admission form is required before a cashless decision is issued.",
        },
        {
            "clause_id": "CL-EXCL",
            "plan_code": plan_code,
            "title": "Cosmetic exclusion",
            "text": "Cosmetic or aesthetic treatment is excluded.",
        },
    ]
    if with_wait:
        clauses.append(
            {
                "clause_id": "CL-WAIT",
                "plan_code": plan_code,
                "title": "Specified-illness wait",
                "text": "Arthroscopy is a specified illness. It is covered only after 90 days from the policy start.",
            }
        )
    for clause in clauses:
        clause["id"] = f"{plan_code}:{clause['clause_id']}"
    return clauses


def seed_clauses() -> list[dict]:
    """Clauses for GOLD, SILVER, and GOLD-NEW. Only GOLD-NEW includes the 90-day wait."""
    return [
        *_common_clauses("GOLD", 5000, False),
        *_common_clauses("SILVER", 3000, False),
        *_common_clauses("GOLD-NEW", 5000, True),
    ]
