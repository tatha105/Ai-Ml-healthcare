"""Azure SQL access for the claim flow. Locally the same calls use SQLite.

The graph's first step calls load_contract. The last step calls save_decision.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import (
    AdmissionRow,
    Base,
    ClaimRow,
    ExclusionRow,
    HospitalRow,
    MemberRow,
    PolicyRow,
)
from app.seed import EXCLUSIONS, HOSPITALS, MEMBERS


def money(value: float) -> float:
    """Round a rupee amount to two decimal places before it is stored."""
    return round(float(value), 2)


class SqlStore:
    """Read and write the SQL tables. This is the system of record for amounts and status."""
    def __init__(self, settings: Settings) -> None:
        """Open SQLite, or Azure SQL when AZURE_SQL_URL is set."""
        settings.ensure_dirs()
        url = settings.sql_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.mode = "azure-sql" if settings.azure_sql_url else "sqlite"

    def init(self) -> None:
        """Create missing tables and, on an empty database, insert the synthetic members.

        A later startup leaves claims that are already saved.
        """
        Base.metadata.create_all(self.engine)
        with self.Session() as session:
            existing = session.scalar(select(func.count()).select_from(MemberRow))
            if existing:
                return
            for member in MEMBERS:
                session.add(MemberRow(id=member["id"], name=member["name"]))
                session.add(
                    PolicyRow(
                        policy_number=member["policy_number"],
                        member_id=member["id"],
                        plan_code=member["plan_code"],
                        plan_name=member["plan_name"],
                        sum_insured=member["sum_insured"],
                        amount_used=member["amount_used"],
                        room_rent_cap=member["room_rent_cap"],
                        effective_from=date.fromisoformat(member["effective_from"]),
                        effective_to=date.fromisoformat(member["effective_to"]),
                        status="active",
                    )
                )
            for hospital in HOSPITALS:
                session.add(HospitalRow(**hospital))
            for exclusion in EXCLUSIONS:
                session.add(ExclusionRow(**exclusion))
            session.commit()

    def catalog(self) -> dict:
        """Return members (with their policy) and hospitals for the admission form."""
        with self.Session() as session:
            members = []
            for member, policy in session.execute(select(MemberRow, PolicyRow).join(PolicyRow, PolicyRow.member_id == MemberRow.id)).all():
                members.append(
                    {
                        "id": member.id,
                        "name": member.name,
                        "policy_number": policy.policy_number,
                        "plan_code": policy.plan_code,
                        "plan_name": policy.plan_name,
                        "sum_insured": policy.sum_insured,
                        "amount_used": policy.amount_used,
                        "room_rent_cap": policy.room_rent_cap,
                        "effective_from": policy.effective_from.isoformat(),
                        "effective_to": policy.effective_to.isoformat(),
                    }
                )
            hospitals = [
                {
                    "id": hospital.id,
                    "name": hospital.name,
                    "city": hospital.city,
                    "in_network": hospital.in_network,
                }
                for hospital in session.scalars(select(HospitalRow).order_by(HospitalRow.name))
            ]
        return {"members": members, "hospitals": hospitals}

    def require_member(self, member_id: str) -> MemberRow:
        """Load one member. Raises KeyError when the id is not in the seed data."""
        with self.Session() as session:
            member = session.get(MemberRow, member_id)
            if member is None:
                raise KeyError(member_id)
            return member

    def require_hospital(self, hospital_id: str) -> HospitalRow:
        """Load one hospital. Raises KeyError when the id is unknown."""
        with self.Session() as session:
            hospital = session.get(HospitalRow, hospital_id)
            if hospital is None:
                raise KeyError(hospital_id)
            return hospital

    def _next_id(self, session: Session, prefix: str, model) -> str:
        """Next id from the row count. The first claim is CLM-1001, the first admission ADM-1001."""
        count = session.scalar(select(func.count()).select_from(model)) or 0
        return f"{prefix}-{1001 + count}"

    def create_admission_and_claim(self, payload: dict) -> tuple[str, str]:
        """Save the visit and a claim in status Received. The graph has not run yet."""
        admitted_at = payload["admitted_at"]
        if isinstance(admitted_at, str):
            admitted_at = datetime.fromisoformat(admitted_at)
        with self.Session() as session:
            admission_id = self._next_id(session, "ADM", AdmissionRow)
            claim_id = self._next_id(session, "CLM", ClaimRow)
            session.add(
                AdmissionRow(
                    id=admission_id,
                    member_id=payload["member_id"],
                    hospital_id=payload["hospital_id"],
                    admitted_at=admitted_at,
                    diagnosis=payload["diagnosis"],
                    treatment=payload["treatment"],
                    estimated_amount=money(payload["estimated_amount"]),
                    room_rent_per_day=money(payload["room_rent_per_day"]),
                    stay_days=int(payload["stay_days"]),
                    document_name=payload.get("document_name") or "admission-form.txt",
                    document_text=payload.get("document_text") or "",
                )
            )
            session.add(
                ClaimRow(
                    id=claim_id,
                    admission_id=admission_id,
                    member_id=payload["member_id"],
                    status="Received",
                    payable_amount=0,
                    patient_share=0,
                    coverage_provider="",
                )
            )
            session.commit()
        return admission_id, claim_id

    def load_contract(self, admission_id: str) -> dict:
        """Join admission, member, policy, hospital, and exclusions for the graph's first step."""
        with self.Session() as session:
            admission = session.get(AdmissionRow, admission_id)
            if admission is None:
                raise KeyError(admission_id)
            member = session.get(MemberRow, admission.member_id)
            policy = session.scalar(select(PolicyRow).where(PolicyRow.member_id == admission.member_id))
            hospital = session.get(HospitalRow, admission.hospital_id)
            exclusions = session.scalars(select(ExclusionRow).where(ExclusionRow.plan_code == policy.plan_code)).all()
            return {
                "admission_id": admission.id,
                "member_id": member.id,
                "member_name": member.name,
                "policy_number": policy.policy_number,
                "plan_code": policy.plan_code,
                "plan_name": policy.plan_name,
                "sum_insured": policy.sum_insured,
                "amount_used": policy.amount_used,
                "room_rent_cap": policy.room_rent_cap,
                "effective_from": policy.effective_from.isoformat(),
                "effective_to": policy.effective_to.isoformat(),
                "status": policy.status,
                "hospital_id": hospital.id,
                "hospital_name": hospital.name,
                "hospital_city": hospital.city,
                "in_network": hospital.in_network,
                "admitted_at": admission.admitted_at.isoformat(timespec="minutes"),
                "diagnosis": admission.diagnosis,
                "treatment": admission.treatment,
                "estimated_amount": admission.estimated_amount,
                "room_rent_per_day": admission.room_rent_per_day,
                "stay_days": admission.stay_days,
                "document_name": admission.document_name,
                "document_text": admission.document_text,
                "exclusions": [
                    {
                        "keyword": row.keyword,
                        "kind": row.kind,
                        "waiting_days": row.waiting_days,
                        "clause_id": row.clause_id,
                    }
                    for row in exclusions
                ],
            }

    def save_decision(self, claim_id: str, decision: dict) -> None:
        """Store the graph's outcome and amounts and set status to Decided.

        The rationale text is not stored here. persist_claim writes that to Cosmos.
        """
        with self.Session() as session:
            claim = session.get(ClaimRow, claim_id)
            claim.status = "Decided"
            claim.outcome = decision["outcome"]
            claim.payable_amount = money(decision["payable_amount"])
            claim.patient_share = money(decision["patient_share"])
            claim.confidence = decision.get("confidence")
            claim.coverage_provider = decision.get("coverage_provider") or ""
            claim.decided_at = datetime.now().replace(microsecond=0)
            session.commit()

    def mark_errored(self, claim_id: str) -> None:
        """Mark the claim Errored when the graph throws, so the queue shows the failure."""
        with self.Session() as session:
            claim = session.get(ClaimRow, claim_id)
            if claim is not None:
                claim.status = "Errored"
                session.commit()

    def confirm(self, claim_id: str, officer_name: str) -> str:
        """Officer accepts a Decided claim. Raises KeyError if missing, ValueError if it is no longer Decided."""
        with self.Session() as session:
            claim = session.get(ClaimRow, claim_id)
            if claim is None:
                raise KeyError(claim_id)
            if claim.status != "Decided":
                raise ValueError(claim.status)
            claim.status = "Confirmed"
            claim.confirmed_by = officer_name.strip() or "Duty officer"
            claim.confirmed_at = datetime.now().replace(microsecond=0)
            session.commit()
            return claim.status

    def send_back(self, claim_id: str) -> str:
        """Officer returns a Decided claim. Same missing-claim and status checks as confirm."""
        with self.Session() as session:
            claim = session.get(ClaimRow, claim_id)
            if claim is None:
                raise KeyError(claim_id)
            if claim.status != "Decided":
                raise ValueError(claim.status)
            claim.status = "Returned"
            session.commit()
            return claim.status

    def list_claims(self) -> list[dict]:
        """Return the queue newest-id first: who, outcome, hospital, and payable amount."""
        with self.Session() as session:
            rows = session.execute(
                select(ClaimRow, AdmissionRow, MemberRow, HospitalRow)
                .join(AdmissionRow, AdmissionRow.id == ClaimRow.admission_id)
                .join(MemberRow, MemberRow.id == ClaimRow.member_id)
                .join(HospitalRow, HospitalRow.id == AdmissionRow.hospital_id)
                .order_by(ClaimRow.id.desc())
            ).all()
            return [
                {
                    "id": claim.id,
                    "status": claim.status,
                    "outcome": claim.outcome,
                    "member_name": member.name,
                    "hospital_name": hospital.name,
                    "diagnosis": admission.diagnosis,
                    "payable_amount": claim.payable_amount,
                    "admitted_at": admission.admitted_at.isoformat(timespec="minutes"),
                }
                for claim, admission, member, hospital in rows
            ]

    def claim_record(self, claim_id: str) -> dict:
        """Return the SQL side of one claim. present_claim adds the Cosmos rationale on top."""
        with self.Session() as session:
            claim = session.get(ClaimRow, claim_id)
            if claim is None:
                raise KeyError(claim_id)
            admission = session.get(AdmissionRow, claim.admission_id)
            member = session.get(MemberRow, claim.member_id)
            policy = session.scalar(select(PolicyRow).where(PolicyRow.member_id == claim.member_id))
            hospital = session.get(HospitalRow, admission.hospital_id)
            return {
                "id": claim.id,
                "admission_id": admission.id,
                "status": claim.status,
                "outcome": claim.outcome,
                "member_id": member.id,
                "member_name": member.name,
                "policy_number": policy.policy_number,
                "plan_name": policy.plan_name,
                "hospital_name": hospital.name,
                "in_network": hospital.in_network,
                "diagnosis": admission.diagnosis,
                "treatment": admission.treatment,
                "admitted_at": admission.admitted_at.isoformat(timespec="minutes"),
                "estimated_amount": admission.estimated_amount,
                "room_rent_per_day": admission.room_rent_per_day,
                "stay_days": admission.stay_days,
                "document_name": admission.document_name,
                "payable_amount": claim.payable_amount,
                "patient_share": claim.patient_share,
                "confidence": claim.confidence,
                "coverage_provider": claim.coverage_provider,
                "confirmed_by": claim.confirmed_by,
                "confirmed_at": claim.confirmed_at.isoformat(timespec="minutes") if claim.confirmed_at else None,
            }
