/**
 * Calls the FastAPI routes in backend/app/main.py.
 * createClaim is the working flow: it runs the LangGraph and returns the decision.
 */
import type { Catalog, ClaimDetail, ClaimDraft, ClaimSummary, Health } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function getHealth() {
  return request<Health>("/api/health");
}

export function getCatalog() {
  return request<Catalog>("/api/catalog");
}

export function listClaims() {
  return request<ClaimSummary[]>("/api/claims");
}

export function getClaim(id: string) {
  return request<ClaimDetail>(`/api/claims/${id}`);
}

/** POST /api/claims. Saves the admission and runs the graph. */
export function createClaim(draft: ClaimDraft) {
  return request<ClaimDetail>("/api/claims", {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

/** POST /api/claims/{id}/confirm. Officer accepts a Decided claim. */
export function confirmClaim(id: string, officerName: string) {
  return request<ClaimDetail>(`/api/claims/${id}/confirm`, {
    method: "POST",
    body: JSON.stringify({ officer_name: officerName }),
  });
}

/** POST /api/claims/{id}/return. Officer sends a Decided claim back. */
export function returnClaim(id: string) {
  return request<ClaimDetail>(`/api/claims/${id}/return`, { method: "POST" });
}
