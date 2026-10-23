"""SQL tables for members, policies, admissions, and claim amounts.

Policy wording and the written rationale live in Cosmos, not in these tables.
Locally this is a SQLite file. With AZURE_SQL_URL the same tables sit on Azure SQL.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class SQLAlchemy uses to create the tables."""


class MemberRow(Base):
    """A synthetic policy member."""

    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class PolicyRow(Base):
    """The member's contract: plan, dates, sum insured, and room-rent cap."""

    __tablename__ = "policies"
    policy_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    plan_code: Mapped[str] = mapped_column(String(32))
    plan_name: Mapped[str] = mapped_column(String(80))
    sum_insured: Mapped[float] = mapped_column(Float)
    amount_used: Mapped[float] = mapped_column(Float)
    room_rent_cap: Mapped[float] = mapped_column(Float)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")


class ExclusionRow(Base):
    """A plan rule. kind `exclude` is a denial keyword. kind `waiting` is a day count."""

    __tablename__ = "exclusions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(32))
    keyword: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    waiting_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clause_id: Mapped[str] = mapped_column(String(32))


class HospitalRow(Base):
    """A hospital. in_network decides whether cashless cover applies."""

    __tablename__ = "hospitals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    in_network: Mapped[bool] = mapped_column(Boolean)


class AdmissionRow(Base):
    """The hospital visit the desk submitted, including the pasted admission form."""

    __tablename__ = "admissions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    admitted_at: Mapped[datetime] = mapped_column(DateTime)
    diagnosis: Mapped[str] = mapped_column(String(240))
    treatment: Mapped[str] = mapped_column(String(240))
    estimated_amount: Mapped[float] = mapped_column(Float)
    room_rent_per_day: Mapped[float] = mapped_column(Float)
    stay_days: Mapped[int] = mapped_column(Integer)
    document_name: Mapped[str] = mapped_column(String(180))
    document_text: Mapped[str] = mapped_column(Text, default="")


class ClaimRow(Base):
    """One cashless claim. Amounts and status live here. The written rationale lives in Cosmos."""

    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"))
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"))
    status: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payable_amount: Mapped[float] = mapped_column(Float, default=0)
    patient_share: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_provider: Mapped[str] = mapped_column(String(40), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
