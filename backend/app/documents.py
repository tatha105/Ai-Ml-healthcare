"""Read the admission form.

The desk pastes text, so the local path is what you see in the UI.
A file byte payload, with Document Intelligence configured, uses Azure's prebuilt-read model.
"""

from __future__ import annotations

from app.config import Settings


class DocumentReader:
    """Turn an admission form into text the eligibility check can accept or reject."""

    def __init__(self, settings: Settings) -> None:
        """Stay on pasted text unless both Document Intelligence settings are set and the client imports."""
        self.settings = settings
        self._client = None
        self.mode = "local"
        if settings.doc_endpoint and settings.doc_key:
            try:
                from azure.ai.documentintelligence import DocumentIntelligenceClient
                from azure.core.credentials import AzureKeyCredential

                self._client = DocumentIntelligenceClient(
                    endpoint=settings.doc_endpoint,
                    credential=AzureKeyCredential(settings.doc_key),
                )
                self.mode = "azure-document-intelligence"
            except Exception:
                self._client = None
                self.mode = "local"

    def extract(self, document_name: str, document_text: str, file_bytes: bytes | None = None) -> dict:
        """Return the form text and whether it is usable.

        Empty text, or text containing UNREADABLE, is not usable. The graph
        then refers the claim and does not call GPT-5.1.
        """
        provider = "local"
        text = (document_text or "").strip()
        if self._client is not None and file_bytes:
            analyzed = self._analyze(file_bytes)
            if analyzed:
                text = analyzed
                provider = "azure-document-intelligence"
        usable = bool(text) and "UNREADABLE" not in text.upper()
        return {
            "document_name": document_name or "admission-form.txt",
            "text": text,
            "usable": usable,
            "provider": provider,
        }

    def _analyze(self, file_bytes: bytes) -> str:
        """Send file bytes to Azure AI Document Intelligence. A failed call returns empty text."""
        try:
            poller = self._client.begin_analyze_document(
                "prebuilt-read",
                body=file_bytes,
                content_type="application/octet-stream",
            )
            result = poller.result()
            return (getattr(result, "content", None) or "").strip()
        except Exception:
            return ""
