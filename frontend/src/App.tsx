import { useEffect, useState } from "react";
import { confirmClaim, createClaim, getCatalog, getClaim, getHealth, listClaims, returnClaim } from "./api";
import { AdmissionForm } from "./AdmissionForm";
import { ClaimView } from "./ClaimView";
import { inr, providerLine, shortDate } from "./format";
import type { Catalog, ClaimDetail, ClaimDraft, ClaimSummary, Health } from "./types";

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [composing, setComposing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getHealth(), getCatalog(), listClaims()])
      .then(([nextHealth, nextCatalog, nextClaims]) => {
        if (cancelled) return;
        setHealth(nextHealth);
        setCatalog(nextCatalog);
        setClaims(nextClaims);
      })
      .catch(() => {
        if (!cancelled) setError("The claim API is not running.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function openClaim(id: string) {
    setError("");
    setComposing(false);
    setSelectedId(id);
    setDetail(await getClaim(id));
  }

  async function refreshList(id: string) {
    const [nextClaims, nextDetail] = await Promise.all([listClaims(), getClaim(id)]);
    setClaims(nextClaims);
    setDetail(nextDetail);
    setSelectedId(id);
    setComposing(false);
  }

  async function submit(draft: ClaimDraft) {
    setBusy(true);
    setError("");
    try {
      const created = await createClaim(draft);
      await refreshList(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The claim could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(officerName: string) {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await confirmClaim(selectedId, officerName);
      await refreshList(selectedId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The decision could not be confirmed.");
    } finally {
      setBusy(false);
    }
  }

  async function sendBack() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await returnClaim(selectedId);
      await refreshList(selectedId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The claim could not be sent back.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <p className="kicker">Synthetic policies</p>
          <h1>Claim desk</h1>
        </div>
        <p className="providers">{health ? providerLine(health) : "Connecting to the claim API…"}</p>
      </header>
      {error ? <p className="banner">{error}</p> : null}
      <div className="shell">
        <aside className="queue">
          <div className="queue-head">
            <h2>Claims</h2>
            <button
              className="ghost"
              type="button"
              onClick={() => {
                setComposing(true);
                setSelectedId(null);
              }}
            >
              New admission
            </button>
          </div>
          {claims.length === 0 ? (
            <p className="empty">No claims yet. Register an admission to run the policy graph.</p>
          ) : (
            <div className="claim-list">
              {claims.map((claim) => (
                <button
                  key={claim.id}
                  type="button"
                  className={claim.id === selectedId && !composing ? "claim-item active" : "claim-item"}
                  onClick={() => {
                    openClaim(claim.id).catch(() => setError("That claim could not be opened."));
                  }}
                >
                  <span className="row-between">
                    <strong>{claim.member_name}</strong>
                    {claim.outcome ? <span className={`outcome outcome-${claim.outcome}`}>{claim.outcome}</span> : null}
                  </span>
                  <span className="hint">
                    {claim.id} · {shortDate(claim.admitted_at)} · {inr(claim.payable_amount)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </aside>
        <main className="panel">
          {composing ? (
            <>
              <div className="panel-head">
                <div>
                  <p className="kicker">Admission</p>
                  <h2>Register a cashless claim</h2>
                </div>
              </div>
              {catalog ? (
                <AdmissionForm catalog={catalog} busy={busy} onSubmit={submit} />
              ) : (
                <p className="hint">Loading members and hospitals…</p>
              )}
            </>
          ) : detail ? (
            <ClaimView claim={detail} busy={busy} onConfirm={confirm} onReturn={sendBack} />
          ) : (
            <p className="hint">Loading the claim…</p>
          )}
          <p className="footnote">
            Recommendations only. An officer confirms every outcome. These members and clauses are synthetic.
          </p>
        </main>
      </div>
    </div>
  );
}
