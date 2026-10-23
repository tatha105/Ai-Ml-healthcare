const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function inr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function shortDate(iso: string) {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function providerLine(health: { sql: string; cosmos: string; documents: string; coverage: string }) {
  const sql = health.sql === "azure-sql" ? "Azure SQL" : "Azure SQL via SQLite";
  const cosmos = health.cosmos === "azure-cosmos" ? "Cosmos DB" : "Cosmos DB via local file";
  const documents =
    health.documents === "azure-document-intelligence"
      ? "Azure AI Document Intelligence"
      : "Document Intelligence via pasted text";
  const coverage = health.coverage.startsWith("azure-openai")
    ? `Azure OpenAI ${health.coverage.split(":")[1] ?? "GPT-5.1"}`
    : "Coverage rules";
  return `${sql} · ${cosmos} · ${documents} · ${coverage}`;
}
