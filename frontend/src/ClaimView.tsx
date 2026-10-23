import { useState } from "react";
import type { ClaimDetail } from "./types";
import { inr, shortDate } from "./format";

export function ClaimView({
  claim,
  busy,
  onConfirm,
  onReturn,
}: {
  claim: ClaimDetail;
  busy: boolean;
  onConfirm: (officerName: string) => void;
  onReturn: () => void;
}) {
  const [officerName, setOfficerName] = useState(claim.confirmed_by || "Duty officer");
  const waiting = claim.status === "Decided";
  const provider =
    claim.coverage_provider === "azure-openai"
      ? "Azure OpenAI GPT-5.1"
      : claim.coverage_provider === "rules"
        ? "Coverage rules"
        : "Eligibility only";

  return (
    <article>
      <div className="panel-head">
        <div>
          <p className="kicker">{claim.id}</p>
          <h2>
            {claim.member_name} · {claim.diagnosis}
          </h2>
          <p className="hint">
            {claim.policy_number} · {claim.plan_name} · {claim.hospital_name} · {shortDate(claim.admitted_at)}
          </p>
        </div>
        {claim.outcome ? <span className={`outcome outcome-${claim.outcome}`}>{claim.outcome}</span> : null}
      </div>
      <div className="figures">
        <div className="figure">
          <span>Payable</span>
          <strong>{inr(claim.payable_amount)}</strong>
        </div>
        <div className="figure">
          <span>Member share</span>
          <strong>{inr(claim.patient_share)}</strong>
        </div>
        <div className="figure">
          <span>Estimate</span>
          <strong>{inr(claim.estimated_amount)}</strong>
        </div>
      </div>
      <p>
        {claim.rationale}{" "}
        <span className="hint">
          {provider}
          {claim.confidence == null ? "" : ` · ${Math.round(claim.confidence * 100)}% confidence`}. Status {claim.status}.
        </span>
      </p>
      <section className="section">
        <h3>Eligibility</h3>
        {claim.checks.map((check) => (
          <div className="check" key={check.name}>
            <span className={`result result-${check.result}`}>{check.result}</span>
            <div>
              <strong>{check.name}</strong>
              <p className="hint">{check.detail}</p>
            </div>
          </div>
        ))}
      </section>
      <section className="section">
        <h3>Cited clauses</h3>
        {claim.cited_clauses.length === 0 ? <p className="hint">No clause was cited.</p> : null}
        {claim.cited_clauses.map((clause) => (
          <div className="clause" key={clause.clause_id}>
            <strong>
              {clause.clause_id} · {clause.title}
            </strong>
            <p>{clause.text}</p>
          </div>
        ))}
      </section>
      <section className="section">
        <h3>Graph</h3>
        {claim.trace.map((step) => (
          <div className="step" key={`${step.node}-${step.summary}`}>
            <code>{step.node}</code>
            <p>{step.summary}</p>
          </div>
        ))}
      </section>
      {waiting ? (
        <div className="actions">
          <label className="officer">
            Officer
            <input value={officerName} onChange={(event) => setOfficerName(event.target.value)} />
          </label>
          <button className="primary" type="button" disabled={busy} onClick={() => onConfirm(officerName)}>
            {claim.outcome === "Referred" ? "Confirm referral" : "Confirm decision"}
          </button>
          <button className="secondary" type="button" disabled={busy} onClick={onReturn}>
            Send back
          </button>
        </div>
      ) : null}
      {claim.status === "Confirmed" ? (
        <p className="footnote">
          Confirmed by {claim.confirmed_by}
          {claim.confirmed_at ? ` on ${shortDate(claim.confirmed_at)}` : ""}.
        </p>
      ) : null}
      {claim.status === "Returned" ? (
        <p className="footnote">Sent back. Register a new admission to run the graph again.</p>
      ) : null}
    </article>
  );
}
