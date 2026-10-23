# End-to-end code demo

One admission, from the HTTP body to the saved decision. Each section is the code that runs, then what each line does.

There is no UI in this walkthrough. Send the request with curl. The API is `http://127.0.0.1:8000`.

Locally the same functions run. Azure SQL is a SQLite file, Cosmos DB is `backend/data/cosmos.json`, the admission form is the pasted text, and GPT-5.1 is the coverage rules. Fill `backend/.env` when you want the live Azure calls. The function names do not change.

## The request

Ananya Shah, CityCare (in network), bill ₹85,000, room rent ₹4,000 a day, Gold cap ₹5,000. The decision is **Approved**, payable ₹85,000.

```bash
curl -s -X POST http://127.0.0.1:8000/api/claims \
  -H 'Content-Type: application/json' \
  -d '{
    "member_id": "MBR-1001",
    "hospital_id": "HSP-CITY",
    "admitted_at": "2026-10-14T09:30:00",
    "diagnosis": "Acute appendicitis",
    "treatment": "Laparoscopic appendectomy",
    "estimated_amount": 85000,
    "room_rent_per_day": 4000,
    "stay_days": 3,
    "document_name": "admission-form.txt",
    "document_text": "Admission form\nHospital: CityCare Hospital\nThe admitting doctor has signed this form."
  }'
```

| Field | What it does |
| --- | --- |
| `member_id` | `MBR-1001`, Ananya Shah, plan GOLD, policy `POL-1001`. |
| `hospital_id` | `HSP-CITY`, CityCare, in the cashless network. |
| `admitted_at` | Must fall inside the policy dates. |
| `estimated_amount` | The bill the graph may approve. |
| `room_rent_per_day` / `stay_days` | Compared with the plan's room-rent cap. |
| `document_text` | The admission form. Empty text makes the claim Referred. |

## 1. FastAPI accepts the body

`backend/app/main.py`. Pydantic checks the body before the function runs.

```25:37:backend/app/main.py
class ClaimCreate(BaseModel):
    member_id: str
    hospital_id: str
    admitted_at: datetime
    diagnosis: str = Field(min_length=2)
    treatment: str = Field(min_length=2)
    estimated_amount: float = Field(gt=0)
    room_rent_per_day: float = Field(ge=0)
    stay_days: int = Field(ge=1, le=60)
    document_name: str = "admission-form.txt"
    document_text: str = ""
```

| Line | What it does |
| --- | --- |
| `member_id` / `hospital_id` | Required strings. Unknown ids are rejected in the next function. |
| `admitted_at: datetime` | Parses `"2026-10-14T09:30:00"` into a datetime. |
| `Field(min_length=2)` | Diagnosis and treatment shorter than 2 characters are HTTP 422. |
| `Field(gt=0)` | The estimate must be above zero. |
| `Field(ge=0)` | Room rent may be zero. |
| `Field(ge=1, le=60)` | Stay length outside 1–60 days is HTTP 422. |
| `document_name` / `document_text` | Optional. Omitted text becomes `""`. |

The route:

```101:123:backend/app/main.py
@app.post("/api/claims")
def create_claim(body: ClaimCreate):
    try:
        stores.sql.require_member(body.member_id)
        stores.sql.require_hospital(body.hospital_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Member or hospital not found") from None
    admission_id, claim_id = stores.sql.create_admission_and_claim(body.model_dump())
    try:
        graph.invoke({"claim_id": claim_id, "admission_id": admission_id, "trace": []})
    except Exception:
        logger.exception("Claim graph failed for %s", claim_id)
        stores.sql.mark_errored(claim_id)
        raise HTTPException(status_code=500, detail="The claim graph failed") from None
    return present_claim(stores, claim_id)
```

| Line | What it does |
| --- | --- |
| `@app.post("/api/claims")` | Binds this function to POST `/api/claims`. |
| `body: ClaimCreate` | The parsed JSON. |
| `require_member` / `require_hospital` | Load `MBR-1001` and `HSP-CITY`. A missing row raises `KeyError`. |
| `HTTPException 404` | That `KeyError` becomes "Member or hospital not found". |
| `create_admission_and_claim` | Inserts the visit and a claim with status `Received`. Returns ids such as `ADM-1003` and `CLM-1003`. |
| `body.model_dump()` | Turns the Pydantic object into a dict the SQL store can read. |
| `graph.invoke(...)` | Runs every LangGraph step. `trace: []` is the empty note list the steps append to. |
| `logger.exception` | Writes the stack trace if a step throws. |
| `mark_errored` | Sets the claim status to `Errored` so it does not stay `Received`. |
| `HTTPException 500` | The caller sees "The claim graph failed". |
| `present_claim` | Reads SQL and Cosmos and returns the response JSON. |

Those objects were built once when the process started:

```52:60:backend/app/main.py
settings = settings or Settings.from_env()
stores = build_stores(settings)
graph = build_claim_graph(stores)

@asynccontextmanager
async def lifespan(app: FastAPI):
    stores.sql.init()
    stores.cosmos.init()
    yield
```

| Line | What it does |
| --- | --- |
| `Settings.from_env()` | Reads `backend/.env`. Blank Azure values keep the local stand-ins. |
| `build_stores` | Builds SQL, Cosmos, the document reader, and the coverage function. |
| `build_claim_graph` | Connects the seven steps into one compiled graph. |
| `sql.init()` | Creates tables. If `members` is empty, inserts the four synthetic members. |
| `cosmos.init()` | Writes the policy clauses if the Cosmos store has none. |
| `yield` | The API starts serving after those two lines. |

## 2. LangGraph order

`backend/app/graph.py`. This block is the whole flow.

```178:198:backend/app/graph.py
graph = StateGraph(ClaimState)
graph.add_node("load_contract", load_contract)
graph.add_node("load_wording", load_wording)
graph.add_node("extract_form", extract_form)
graph.add_node("check_eligibility", check_eligibility)
graph.add_node("assess_coverage", assess_coverage)
graph.add_node("route_outcome", route_outcome)
graph.add_node("persist_claim", persist_claim)
graph.set_entry_point("load_contract")
graph.add_edge("load_contract", "load_wording")
graph.add_edge("load_wording", "extract_form")
graph.add_edge("extract_form", "check_eligibility")
graph.add_conditional_edges(
    "check_eligibility",
    after_eligibility,
    {"assess_coverage": "assess_coverage", "route_outcome": "route_outcome"},
)
graph.add_edge("assess_coverage", "route_outcome")
graph.add_edge("route_outcome", "persist_claim")
graph.add_edge("persist_claim", END)
return graph.compile()
```

| Line | What it does |
| --- | --- |
| `StateGraph(ClaimState)` | Shared state is one dict. Each step returns the keys it changes. |
| `add_node` | Registers one function under a name. |
| `set_entry_point("load_contract")` | `invoke` starts at step 1. |
| `add_edge` | An unconditional arrow. |
| `add_conditional_edges` | After eligibility, `after_eligibility` returns the name of the next node. |
| `END` | Stops the graph. |
| `compile()` | Freezes the graph so `invoke` can run it. |

`ClaimState.trace` is annotated with `operator.add`. A step returns `{"trace": [one note]}` and LangGraph appends it instead of replacing the list.

### Step 1 — Azure SQL

```45:56:backend/app/graph.py
def load_contract(state: ClaimState) -> dict:
    contract = stores.sql.load_contract(state["admission_id"])
    return {
        "contract": contract,
        "trace": [
            _note(
                "load_contract",
                f"Loaded {contract['policy_number']} ({contract['plan_name']}) and {contract['hospital_name']}.",
            )
        ],
    }
```

| Line | What it does |
| --- | --- |
| `state["admission_id"]` | The id just inserted. |
| `load_contract` | Joins admission, member, policy, hospital, and exclusions. This request loads Ananya, `POL-1001`, Gold, room cap 5000, CityCare, `in_network` true. |
| `return {"contract": ...}` | Merged into the state. Later steps read `state["contract"]`. |
| `_note(...)` | One trace line: "Loaded POL-1001 (Gold) and CityCare Hospital." |

`SqlStore` uses SQLite unless `AZURE_SQL_URL` is set. The SQL calls are the same either way. Table classes are in `db.py`.

### Step 2 — Cosmos DB

```58:65:backend/app/graph.py
def load_wording(state: ClaimState) -> dict:
    plan_code = state["contract"]["plan_code"]
    clauses = stores.cosmos.clauses_for_plan(plan_code)
    return {
        "clauses": clauses,
        "trace": [_note("load_wording", f"Loaded {len(clauses)} clauses for plan {plan_code}.")],
    }
```

| Line | What it does |
| --- | --- |
| `plan_code` | `"GOLD"`. |
| `clauses_for_plan` | Clause documents for that plan. Locally a filter on `cosmos.json`. On Azure a query of container `policy_clauses`. |
| `return {"clauses": ...}` | Seven clauses, including `CL-SURG` and `CL-ROOM`. Later steps may cite only these ids. |

### Step 3 — Azure AI Document Intelligence

```67:75:backend/app/graph.py
def extract_form(state: ClaimState) -> dict:
    contract = state["contract"]
    extracted = stores.documents.extract(contract["document_name"], contract["document_text"])
    if extracted["usable"]:
        summary = f"Read {extracted['document_name']} with the {extracted['provider']} reader."
    else:
        summary = "The admission form has no legible text."
    return {"extracted": extracted, "trace": [_note("extract_form", summary)]}
```

```40:47:backend/app/documents.py
provider = "local"
text = (document_text or "").strip()
if self._client is not None and file_bytes:
    analyzed = self._analyze(file_bytes)
    if analyzed:
        text = analyzed
        provider = "azure-document-intelligence"
usable = bool(text) and "UNREADABLE" not in text.upper()
```

| Line | What it does |
| --- | --- |
| `provider = "local"` | This request sends pasted text, so the reader stays local. |
| `text = ...strip()` | The admission note from the JSON body. |
| `if self._client and file_bytes` | A file, with Document Intelligence configured, calls Azure. This curl has no file bytes, so the branch is skipped. |
| `_analyze` | Azure `prebuilt-read`. The returned string replaces the pasted text. |
| `usable` | False when the text is empty or contains `UNREADABLE`. Step 4 then returns Referred. |

This request is usable. The trace says the local reader read `admission-form.txt`.

### Step 4 — eligibility

```77:86:backend/app/graph.py
def check_eligibility(state: ClaimState) -> dict:
    eligibility = _eligibility(state["contract"], state["extracted"])
    if eligibility["decision"] == "Continue":
        summary = "Eligibility passed. Coverage assessment can run."
    elif eligibility["decision"] == "Referred":
        summary = "Eligibility stopped the claim before coverage assessment. The form needs review."
    else:
        summary = f"Eligibility stopped the claim before coverage assessment. {eligibility['reason']}"
    return {"eligibility": eligibility, "trace": [_note("check_eligibility", summary)]}
```

`_eligibility` records five checks, then returns on the first failure:

```282:292:backend/app/graph.py
if not in_force:
    return _stop("Denied", checks[0]["detail"], ["CL-TERM"], checks)
if waiting_hit:
    return _stop("Denied", checks[1]["detail"], [waiting_hit["clause_id"]], checks)
if exclusion_hit:
    return _stop("Denied", checks[2]["detail"], [exclusion_hit["clause_id"]], checks)
if not contract["in_network"]:
    return _stop("Denied", checks[3]["detail"], ["CL-NET"], checks)
if not usable:
    return _stop("Referred", checks[4]["detail"], ["CL-FORM"], checks)
return {"decision": "Continue", "reason": "Eligibility passed.", "clause_ids": [], "checks": checks}
```

| Line | This request |
| --- | --- |
| `if not in_force` | 14 Oct 2026 is inside 1 Apr 2024–31 Mar 2027, so this is skipped. |
| `if waiting_hit` | "appendicitis" does not contain `arthroscopy`, so this is skipped. |
| `if exclusion_hit` | The text does not contain `cosmetic`, so this is skipped. |
| `if not contract["in_network"]` | CityCare is in network, so this is skipped. |
| `if not usable` | The note has text, so this is skipped. |
| `return Continue` | All five checks passed. The model may run. |

The branch after that:

```172:176:backend/app/graph.py
def after_eligibility(state: ClaimState) -> str:
    if state["eligibility"]["decision"] == "Continue":
        return "assess_coverage"
    return "route_outcome"
```

| Line | What it does |
| --- | --- |
| `return "assess_coverage"` | This request. Step 5 runs. |
| `return "route_outcome"` | Denied or Referred. Step 5 does not run. GPT-5.1 is not called. |

### Step 5 — LangChain and GPT-5.1

```88:125:backend/app/graph.py
def assess_coverage(state: ClaimState) -> dict:
    contract = state["contract"]
    payload = {
        "facts": { ... member, amounts, diagnosis, admission form ... },
        "clauses": [
            {"clause_id": clause["clause_id"], "title": clause["title"], "text": clause["text"]}
            for clause in state["clauses"]
        ],
    }
    assessment = stores.assess(payload)
    provider = assessment.get("provider") or "rules"
    who = "Azure OpenAI" if provider == "azure-openai" else "The rule assessor"
    return {
        "assessment": assessment,
        "trace": [_note("assess_coverage", f"{who} recommended {assessment['outcome']}.")],
    }
```

| Line | What it does |
| --- | --- |
| `payload["facts"]` | Numbers and clinical text copied from the contract. |
| `payload["clauses"]` | Id, title, and text only. Those are the clauses a citation may use. |
| `stores.assess` | The function chosen at startup by `build_assessor`. |
| `who` | Trace text. Locally: "The rule assessor recommended Approved." |

With Azure OpenAI set, `coverage.py` builds this LangChain pipeline:

```python
llm = AzureChatOpenAI(
    azure_endpoint=settings.openai_endpoint,
    api_key=settings.openai_api_key,
    azure_deployment=settings.openai_deployment,  # gpt-5.1
    api_version=settings.openai_api_version,
)
structured = llm.with_structured_output(CoverageDecision)
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Facts:\n{facts}\n\nClauses:\n{clauses}"),
])
chain = prompt | structured
```

| Line | What it does |
| --- | --- |
| `AzureChatOpenAI` | LangChain client for one Azure OpenAI deployment. |
| `azure_deployment` | `gpt-5.1`, unless `AZURE_OPENAI_DEPLOYMENT` overrides it. |
| `with_structured_output(CoverageDecision)` | The model must return outcome, amounts, confidence, rationale, and clause ids. |
| `ChatPromptTemplate` | Substitutes `{facts}` and `{clauses}` into the human message. |
| `prompt \| structured` | LangChain runs the prompt, then the model. |
| `chain.invoke` | The actual call, inside the inner `assess` function. |

If `invoke` throws, `assess` catches it, calls `rule_assess`, and appends a sentence that Azure OpenAI was unavailable.

This demo has no key, so `rule_assess` runs. The arithmetic for this body:

```python
estimated = 85000
cap = 5000
room = 4000
days = 3
remaining = 500000 - 0
room_excess = max(0, 4000 - 5000) * 3   # 0
covered = 85000 - 0                      # 85000
payable = 85000
patient = 0
outcome = "Approved"                     # patient > 0 would be "Partial"
cites = ["CL-SURG"]
confidence = 0.9
provider = "rules"
```

`coverage.py` lines that produce that:

```48:68:backend/app/coverage.py
estimated = float(facts["estimated_amount"])
cap = float(facts["room_rent_cap"])
room = float(facts["room_rent_per_day"])
days = int(facts["stay_days"])
remaining = max(0.0, float(facts["sum_insured"]) - float(facts["amount_used"]))
room_excess = round(max(0.0, room - cap) * days, 2)
covered = max(0.0, estimated - room_excess)
cites = ["CL-SURG"]
if room_excess > 0 and "CL-ROOM" in known:
    cites.append("CL-ROOM")
if covered > remaining:
    payable = round(remaining, 2)
    patient = round(estimated - remaining, 2)
    ...
else:
    payable = round(covered, 2)
    patient = round(room_excess, 2)
outcome = "Partial" if patient > 0 else "Approved"
```

| Line | This request |
| --- | --- |
| `room_excess` | Rent 4000 is under cap 5000, so excess is 0. `CL-ROOM` is not cited. |
| `covered > remaining` | 85000 is under 500000, so the sum-insured branch is skipped. |
| `else` | Payable is the full 85000. Patient share is 0. |
| `outcome` | Patient share is 0, so Approved. |

### Step 6 — route

```306:339:backend/app/graph.py
eligibility = state["eligibility"]
if eligibility["decision"] in {"Denied", "Referred"}:
    outcome = eligibility["decision"]
    return {
        "outcome": outcome,
        "payable_amount": 0,
        "patient_share": 0,
        "confidence": None,
        "rationale": eligibility["reason"],
        "cited_clause_ids": eligibility["clause_ids"],
        "coverage_provider": "not_called",
    }
assessment = state["assessment"]
outcome = assessment["outcome"]
cited = assessment["cited_clause_ids"]
...
if outcome in {"Approved", "Partial", "Denied"} and not cited:
    outcome = "Referred"
elif confidence is not None and confidence < 0.55 and outcome != "Referred":
    outcome = "Referred"
payable = 0 if outcome in {"Denied", "Referred"} else assessment["payable_amount"]
patient = 0 if outcome in {"Denied", "Referred"} else assessment["patient_share"]
```

| Line | This request |
| --- | --- |
| First `if` | Skipped. The decision was `Continue`. |
| `outcome = assessment["outcome"]` | `"Approved"`. |
| `not cited` | Skipped. `CL-SURG` is a real clause id. |
| `confidence < 0.55` | Skipped. The rules return 0.9. A low-confidence model answer would become Referred and the amounts would be zeroed. |
| `payable` / `patient` | Stay 85000 and 0. |
| `coverage_provider` | `"rules"`. A GPT-5.1 answer is `"azure-openai"`. |

### Step 7 — save

```135:170:backend/app/graph.py
def persist_claim(state: ClaimState) -> dict:
    decision = state["decision"]
    cited_ids = decision["cited_clause_ids"]
    by_id = {clause["clause_id"]: clause for clause in state.get("clauses") or []}
    cited = [
        {"clause_id": clause_id, "title": by_id[clause_id]["title"], "text": by_id[clause_id]["text"]}
        for clause_id in cited_ids
        if clause_id in by_id
    ]
    stores.sql.save_decision(state["claim_id"], { ... outcome, amounts, confidence ... })
    stores.cosmos.save_packet({ ... rationale, cited_clauses, checks, trace ... })
    return {"trace": [_note("persist_claim", "Saved the claim amounts and the decision packet.")]}
```

| Line | What it does |
| --- | --- |
| `by_id` | Map of clause id to the document loaded in step 2. |
| `cited` | Copies the `CL-SURG` title and text into the packet. |
| `save_decision` | SQL row becomes `Decided`, outcome `Approved`, payable 85000, patient share 0, confidence 0.9. |
| `save_packet` | Rationale, checks, and trace. Locally `packets[claim_id]` in `cosmos.json`. On Azure an upsert into `claim_packets`. |
| `return {"trace": ...}` | Last graph note. The packet already contains that note, and the response reads the packet. |

## 3. The response

```9:17:backend/app/present.py
def present_claim(stores: Stores, claim_id: str) -> dict:
    record = stores.sql.claim_record(claim_id)
    packet = stores.cosmos.get_packet(claim_id) or {}
    record["rationale"] = packet.get("rationale") or ""
    record["cited_clauses"] = packet.get("cited_clauses") or []
    record["checks"] = packet.get("checks") or []
    record["trace"] = packet.get("trace") or []
    return record
```

| Line | What it does |
| --- | --- |
| `claim_record` | Member, hospital, amounts, and status from SQL. |
| `get_packet` | The write-up from Cosmos. `or {}` keeps a claim that has no packet. |
| four assignments | Rationale, cited clauses, the five checks, and the graph trace. |
| `return record` | HTTP 200 body. |

Fields to check in that JSON:

| Field | Value for this request |
| --- | --- |
| `outcome` | `Approved` |
| `payable_amount` | `85000` |
| `patient_share` | `0` |
| `coverage_provider` | `rules` |
| `status` | `Decided` |
| `cited_clauses` | `CL-SURG` |
| `trace` | seven nodes, including `assess_coverage` |

## 4. Confirm, still HTTP

Confirm does not run the graph again. It only changes the SQL status.

```bash
curl -s -X POST http://127.0.0.1:8000/api/claims/CLM-1003/confirm \
  -H 'Content-Type: application/json' \
  -d '{"officer_name": "Duty officer"}'
```

```125:129:backend/app/main.py
def confirm_claim(claim_id: str, body: ConfirmBody):
    _act(stores, claim_id, lambda: stores.sql.confirm(claim_id, body.officer_name))
    return present_claim(stores, claim_id)
```

`SqlStore.confirm` updates a row only while status is `Decided`. It sets `Confirmed`, `confirmed_by`, and `confirmed_at`. A second confirm raises `ValueError`, and `_act` turns that into HTTP 409.

`POST /api/claims/{id}/return` is the same shape. `send_back` sets status `Returned` instead of `Confirmed`.

## Other request bodies

Same `POST /api/claims`. Only the JSON changes. The fast path is `after_eligibility` returning `"route_outcome"`.

| Change the JSON to | Step 5 | `outcome` | Citation |
| --- | --- | --- | --- |
| `member_id` `MBR-1002`, diagnosis `Dengue fever`, treatment `Inpatient medical management`, estimate `96000`, room `8000`, stay `4` | Rules run. Excess is (8000−3000)×4 = 20000 | `Partial`, payable `76000` | `CL-ROOM` |
| `member_id` `MBR-1003`, admitted `2026-10-10T09:30:00`, diagnosis `Knee arthroscopy`, treatment `Arthroscopic repair` | Skipped. Policy is 39 days old, wait is 90 | `Denied` | `CL-WAIT` |
| `member_id` `MBR-1004`, `document_text` `""` | Skipped. Form is not usable | `Referred` | `CL-FORM` |
| `hospital_id` `HSP-LAKE` | Skipped. Lakeside is outside the network | `Denied` | `CL-NET` |

On the three skips, `coverage_provider` is `not_called` and `trace` has no `assess_coverage` node.
