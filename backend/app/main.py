"""FastAPI routes for the claim desk.

Working flow: POST /api/claims saves the admission, runs the LangGraph in
graph.py, and returns the decision. The officer then confirms or sends it back.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import Settings
from app.graph import build_claim_graph
from app.present import present_claim
from app.runtime import Stores, build_stores

logger = logging.getLogger("claimdesk")


class ClaimCreate(BaseModel):
    """Body of POST /api/claims. This is the admission the desk submits."""

    member_id: str
    hospital_id: str
    admitted_at: datetime
    diagnosis: str = Field(min_length=2)
    treatment: str = Field(min_length=2)
    estimated_amount: float = Field(gt=0)
    room_rent_per_day: float = Field(ge=0)
    stay_days: int = Field(ge=1, le=60)
    document_name: str = "admission-form.txt"
    document_text: str = ""


class ConfirmBody(BaseModel):
    """Body of the confirm route. The desk sends the officer's name."""

    officer_name: str = "Duty officer"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app, the stores, and the graph.

    Tests pass their own Settings so each test gets a fresh SQLite file.
    uvicorn uses the app at the bottom of this file, built from the environment.
    """
    settings = settings or Settings.from_env()
    stores = build_stores(settings)
    graph = build_claim_graph(stores)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """On startup, create the SQL tables and the Cosmos clause documents."""
        stores.sql.init()
        stores.cosmos.init()
        yield

    app = FastAPI(title="Hospital policy claim", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.stores = stores
    app.state.graph = graph

    @app.get("/api/health")
    def health():
        """GET /api/health. Tells the desk which stand-in or Azure service is active."""
        return {
            "sql": stores.sql.mode,
            "cosmos": stores.cosmos.mode,
            "documents": stores.documents.mode,
            "coverage": stores.coverage_mode,
        }

    @app.get("/api/catalog")
    def catalog():
        """GET /api/catalog. Members and hospitals for the admission form."""
        return stores.sql.catalog()

    @app.get("/api/claims")
    def list_claims():
        """GET /api/claims. The queue on the left of the desk."""
        return stores.sql.list_claims()

    @app.get("/api/claims/{claim_id}")
    def get_claim(claim_id: str):
        """GET /api/claims/{id}. SQL amounts plus the Cosmos rationale and graph trace."""
        try:
            return present_claim(stores, claim_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Claim not found") from None

    @app.post("/api/claims")
    def create_claim(body: ClaimCreate):
        """POST /api/claims. This is the working flow.

        1. Reject an unknown member or hospital.
        2. Save the admission and a Received claim in SQL.
        3. Run the LangGraph. It reads SQL and Cosmos, checks eligibility,
           and may call LangChain / Azure OpenAI.
        4. Return the decision for the officer.
        """
        try:
            stores.sql.require_member(body.member_id)
            stores.sql.require_hospital(body.hospital_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Member or hospital not found") from None
        admission_id, claim_id = stores.sql.create_admission_and_claim(body.model_dump())
        try:
            graph.invoke({"claim_id": claim_id, "admission_id": admission_id, "trace": []})
        except Exception:
            logger.exception("Claim graph failed for %s", claim_id)
            stores.sql.mark_errored(claim_id)
            raise HTTPException(status_code=500, detail="The claim graph failed") from None
        return present_claim(stores, claim_id)

    @app.post("/api/claims/{claim_id}/confirm")
    def confirm_claim(claim_id: str, body: ConfirmBody):
        """POST /api/claims/{id}/confirm. Officer accepts a Decided claim."""
        _act(stores, claim_id, lambda: stores.sql.confirm(claim_id, body.officer_name))
        return present_claim(stores, claim_id)

    @app.post("/api/claims/{claim_id}/return")
    def return_claim(claim_id: str):
        """POST /api/claims/{id}/return. Officer sends a Decided claim back."""
        _act(stores, claim_id, lambda: stores.sql.send_back(claim_id))
        return present_claim(stores, claim_id)

    return app


def _act(stores: Stores, claim_id: str, action) -> None:
    """Run confirm or send-back. Missing claim is 404. A claim that is not Decided is 409."""
    try:
        action()
    except KeyError:
        raise HTTPException(status_code=404, detail="Claim not found") from None
    except ValueError:
        raise HTTPException(status_code=409, detail="This claim is no longer waiting for an officer") from None


app = create_app()
