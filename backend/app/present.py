"""Join the SQL claim with the Cosmos packet into the JSON the desk renders.
"""

from __future__ import annotations

from app.runtime import Stores


def present_claim(stores: Stores, claim_id: str) -> dict:
    """Return one claim: amounts from SQL, rationale, clauses, checks, and trace from Cosmos."""
    record = stores.sql.claim_record(claim_id)
    packet = stores.cosmos.get_packet(claim_id) or {}
    record["rationale"] = packet.get("rationale") or ""
    record["cited_clauses"] = packet.get("cited_clauses") or []
    record["checks"] = packet.get("checks") or []
    record["trace"] = packet.get("trace") or []
    return record
