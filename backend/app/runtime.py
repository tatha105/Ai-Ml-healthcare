"""Build the objects the graph calls: SQL, Cosmos, documents, and the coverage function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.config import Settings
from app.cosmos_store import build_cosmos_store
from app.coverage import build_assessor
from app.documents import DocumentReader
from app.sql_store import SqlStore


@dataclass
class Stores:
    """Everything one claim graph needs. The nodes close over this object."""
    settings: Settings
    sql: SqlStore
    cosmos: object
    documents: DocumentReader
    assess: Callable[[dict], dict]
    coverage_mode: str


def build_stores(settings: Settings) -> Stores:
    """Construct SQL, Cosmos, Document Intelligence, and the LangChain assessor."""
    assess, coverage_mode = build_assessor(settings)
    return Stores(
        settings=settings,
        sql=SqlStore(settings),
        cosmos=build_cosmos_store(settings),
        documents=DocumentReader(settings),
        assess=assess,
        coverage_mode=coverage_mode,
    )
