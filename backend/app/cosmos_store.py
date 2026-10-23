"""Policy wording and the decision packet.

Amounts stay in SQL. This store holds clause text, the rationale, citations,
and the graph trace. Locally that is data/cosmos.json. With Cosmos credentials
the same four methods talk to Azure Cosmos DB.
"""

from __future__ import annotations

import json

from app.config import Settings
from app.seed import seed_clauses


class FileCosmosStore:
    """Local stand-in with the same methods as Azure Cosmos DB."""

    def __init__(self, settings: Settings) -> None:
        """Point at data/cosmos.json."""
        settings.ensure_dirs()
        self.path = settings.data_dir / "cosmos.json"
        self.mode = "file"

    def init(self) -> None:
        """Write the seed clauses once. Packets already in the file are kept."""
        data = self._load()
        if not data["clauses"]:
            data["clauses"] = seed_clauses()
            self._save(data)

    def clauses_for_plan(self, plan_code: str) -> list[dict]:
        """Return the clause documents for one plan, such as GOLD or GOLD-NEW."""
        data = self._load()
        return [dict(clause) for clause in data["clauses"] if clause["plan_code"] == plan_code]

    def save_packet(self, packet: dict) -> None:
        """Store the decision write-up under the claim id."""
        data = self._load()
        data["packets"][packet["claim_id"]] = packet
        self._save(data)

    def get_packet(self, claim_id: str) -> dict | None:
        """Return the decision packet, or None when this claim has no write-up yet."""
        packet = self._load()["packets"].get(claim_id)
        return dict(packet) if packet else None

    def _load(self) -> dict:
        """Read cosmos.json. A missing file starts as empty clauses and packets."""
        if not self.path.exists():
            return {"clauses": [], "packets": {}}
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        """Write cosmos.json."""
        self.path.write_text(json.dumps(data, indent=2))


class AzureCosmosStore:
    """Same four operations against Azure Cosmos DB containers."""

    def __init__(self, settings: Settings) -> None:
        """Create the database and the policy_clauses and claim_packets containers if needed."""
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.create_database_if_not_exists(settings.cosmos_database)
        self.clauses = database.create_container_if_not_exists(
            id="policy_clauses",
            partition_key=PartitionKey(path="/plan_code"),
        )
        self.packets = database.create_container_if_not_exists(
            id="claim_packets",
            partition_key=PartitionKey(path="/claim_id"),
        )
        self.mode = "azure-cosmos"

    def init(self) -> None:
        """Insert the seed clauses when the policy_clauses container is empty."""
        existing = list(self.clauses.read_all_items())
        if existing:
            return
        for clause in seed_clauses():
            self.clauses.upsert_item(clause)

    def clauses_for_plan(self, plan_code: str) -> list[dict]:
        """Query policy_clauses for one plan code."""
        items = self.clauses.query_items(
            query="SELECT * FROM c WHERE c.plan_code = @plan",
            parameters=[{"name": "@plan", "value": plan_code}],
            enable_cross_partition_query=True,
        )
        return list(items)

    def save_packet(self, packet: dict) -> None:
        """Upsert the decision packet. The Cosmos item id is the claim id."""
        body = dict(packet)
        body["id"] = packet["claim_id"]
        self.packets.upsert_item(body)

    def get_packet(self, claim_id: str) -> dict | None:
        """Read one claim packet. A missing item returns None."""
        try:
            return self.packets.read_item(item=claim_id, partition_key=claim_id)
        except Exception:
            return None


def build_cosmos_store(settings: Settings):
    """Return Azure Cosmos when the endpoint and key connect. Otherwise the JSON file."""
    if settings.cosmos_endpoint and settings.cosmos_key:
        try:
            return AzureCosmosStore(settings)
        except Exception:
            return FileCosmosStore(settings)
    return FileCosmosStore(settings)
