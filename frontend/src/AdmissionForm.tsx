import { useMemo, useState } from "react";
import type { Catalog, ClaimDraft } from "./types";
import { inr } from "./format";
import { scenarios } from "./scenarios";

export function AdmissionForm({
  catalog,
  busy,
  onSubmit,
}: {
  catalog: Catalog;
  busy: boolean;
  onSubmit: (draft: ClaimDraft) => void;
}) {
  const [scenarioId, setScenarioId] = useState(scenarios[0].id);
  const [draft, setDraft] = useState<ClaimDraft>(scenarios[0]);
  const member = useMemo(
    () => catalog.members.find((item) => item.id === draft.member_id),
    [catalog.members, draft.member_id],
  );

  function applyScenario(id: string) {
    const scenario = scenarios.find((item) => item.id === id) ?? scenarios[0];
    setScenarioId(scenario.id);
    setDraft(scenario);
  }

  function patch(partial: Partial<ClaimDraft>) {
    setDraft((current) => ({ ...current, ...partial }));
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(draft);
      }}
    >
      <div className="scenarios" role="group" aria-label="Sample admissions">
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            className={scenario.id === scenarioId ? "scenario active" : "scenario"}
            onClick={() => applyScenario(scenario.id)}
          >
            <strong>{scenario.label}</strong>
            <span className="hint">{scenario.hint}</span>
          </button>
        ))}
      </div>
      <div className="form-grid">
        <label>
          Member
          <select value={draft.member_id} onChange={(event) => patch({ member_id: event.target.value })}>
            {catalog.members.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.policy_number}
              </option>
            ))}
          </select>
        </label>
        <label>
          Hospital
          <select value={draft.hospital_id} onChange={(event) => patch({ hospital_id: event.target.value })}>
            {catalog.hospitals.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.in_network ? "network" : "out of network"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Admitted at
          <input
            type="datetime-local"
            value={draft.admitted_at}
            onChange={(event) => patch({ admitted_at: event.target.value })}
            required
          />
        </label>
        <label>
          Stay (days)
          <input
            type="number"
            min={1}
            max={60}
            value={draft.stay_days}
            onChange={(event) => patch({ stay_days: Number(event.target.value) })}
            required
          />
        </label>
        <label>
          Diagnosis
          <input
            value={draft.diagnosis}
            onChange={(event) => patch({ diagnosis: event.target.value })}
            required
          />
        </label>
        <label>
          Treatment
          <input
            value={draft.treatment}
            onChange={(event) => patch({ treatment: event.target.value })}
            required
          />
        </label>
        <label>
          Estimated bill
          <input
            type="number"
            min={1}
            value={draft.estimated_amount}
            onChange={(event) => patch({ estimated_amount: Number(event.target.value) })}
            required
          />
        </label>
        <label>
          Room rent per day
          <input
            type="number"
            min={0}
            value={draft.room_rent_per_day}
            onChange={(event) => patch({ room_rent_per_day: Number(event.target.value) })}
            required
          />
        </label>
        <label className="wide">
          Admission form
          <textarea
            value={draft.document_text}
            onChange={(event) => patch({ document_text: event.target.value })}
            placeholder="Paste the admission note. Leave it empty to send the claim to review."
          />
        </label>
      </div>
      {member ? (
        <p className="policy-note hint">
          {member.plan_name} · {member.policy_number} · room rent cap {inr(member.room_rent_cap)} / day · sum
          insured {inr(member.sum_insured)} · in force {member.effective_from} to {member.effective_to}
        </p>
      ) : null}
      <div className="actions">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Running claim…" : "Run claim"}
        </button>
      </div>
    </form>
  );
}
