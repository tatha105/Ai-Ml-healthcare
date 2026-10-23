export type Health = {
  sql: string;
  cosmos: string;
  documents: string;
  coverage: string;
};

export type Member = {
  id: string;
  name: string;
  policy_number: string;
  plan_code: string;
  plan_name: string;
  sum_insured: number;
  amount_used: number;
  room_rent_cap: number;
  effective_from: string;
  effective_to: string;
};

export type Hospital = {
  id: string;
  name: string;
  city: string;
  in_network: boolean;
};

export type Catalog = {
  members: Member[];
  hospitals: Hospital[];
};

export type ClaimSummary = {
  id: string;
  status: string;
  outcome: string | null;
  member_name: string;
  hospital_name: string;
  diagnosis: string;
  payable_amount: number;
  admitted_at: string;
};

export type Check = {
  name: string;
  result: "pass" | "fail" | "refer";
  detail: string;
};

export type Clause = {
  clause_id: string;
  title: string;
  text: string;
};

export type TraceStep = {
  node: string;
  summary: string;
};

export type ClaimDetail = {
  id: string;
  admission_id: string;
  status: string;
  outcome: string | null;
  member_name: string;
  policy_number: string;
  plan_name: string;
  hospital_name: string;
  in_network: boolean;
  diagnosis: string;
  treatment: string;
  admitted_at: string;
  estimated_amount: number;
  room_rent_per_day: number;
  stay_days: number;
  document_name: string;
  payable_amount: number;
  patient_share: number;
  confidence: number | null;
  coverage_provider: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  rationale: string;
  cited_clauses: Clause[];
  checks: Check[];
  trace: TraceStep[];
};

export type ClaimDraft = {
  member_id: string;
  hospital_id: string;
  admitted_at: string;
  diagnosis: string;
  treatment: string;
  estimated_amount: number;
  room_rent_per_day: number;
  stay_days: number;
  document_name: string;
  document_text: string;
};
