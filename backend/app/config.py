"""Settings. Empty Azure values keep the local stand-ins: SQLite, a JSON file, pasted text, and rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _blank(name: str) -> str | None:
    """Read one environment variable. A missing or blank value means 'use the local stand-in'."""
    value = os.getenv(name, "").strip()
    return value or None


@dataclass
class Settings:
    """Paths and Azure credentials for one process."""
    data_dir: Path = field(default_factory=lambda: BACKEND_ROOT / "data")
    azure_sql_url: str | None = None
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database: str = "claimdesk"
    doc_endpoint: str | None = None
    doc_key: str | None = None
    openai_endpoint: str | None = None
    openai_api_key: str | None = None
    openai_deployment: str = "gpt-5.1"
    openai_api_version: str = "2024-10-21"

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from backend/.env. Used by the uvicorn app, not by tests."""
        load_dotenv(BACKEND_ROOT / ".env")
        data_dir = Path(os.getenv("DATA_DIR", "")).expanduser() if os.getenv("DATA_DIR") else BACKEND_ROOT / "data"
        return cls(
            data_dir=data_dir,
            azure_sql_url=_blank("AZURE_SQL_URL"),
            cosmos_endpoint=_blank("COSMOS_ENDPOINT"),
            cosmos_key=_blank("COSMOS_KEY"),
            cosmos_database=os.getenv("COSMOS_DATABASE", "claimdesk").strip() or "claimdesk",
            doc_endpoint=_blank("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
            doc_key=_blank("AZURE_DOCUMENT_INTELLIGENCE_KEY"),
            openai_endpoint=_blank("AZURE_OPENAI_ENDPOINT"),
            openai_api_key=_blank("AZURE_OPENAI_API_KEY"),
            openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.1").strip() or "gpt-5.1",
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip() or "2024-10-21",
        )

    def ensure_dirs(self) -> None:
        """Create the data folder that holds claims.db and cosmos.json."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def sql_url(self) -> str:
        """Azure SQL URL when set, otherwise the local SQLite file."""
        if self.azure_sql_url:
            return self.azure_sql_url
        return f"sqlite:///{self.data_dir / 'claims.db'}"
