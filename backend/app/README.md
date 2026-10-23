# How `backend/app` works

This folder is the claim API. The React desk sends an admission here. FastAPI saves it, LangGraph walks the policy checks, and the result comes back for an officer to confirm.

Each function has a docstring that says where it sits in that flow. Start at `create_claim` in `main.py`, then the seven steps at the top of `graph.py`.

Read the files in the order below. Each later file is a piece the earlier files call.

```
main.py          HTTP routes
  runtime.py     builds the stores the graph will use
    config.py    reads .env and chooses SQLite or Azure
    sql_store.py members, policies, admissions, claim amounts
      db.py      table definitions
      seed.py    the four synthetic members
    cosmos_store.py  policy wording and the decision write-up
    documents.py     reads the admission form
    coverage.py      rules, or Azure OpenAI GPT-5.1 through LangChain
  graph.py       the step order
  present.py     joins the SQL row and the Cosmos packet for the desk
```

`__init__.py` is empty. It only marks this folder as a Python package so `from app.main import ...` works.

## What happens on one claim

1. `POST /api/claims` in `main.py` checks the member and hospital, then inserts an admission and a claim with status `Received`.
2. `graph.invoke` starts at `load_contract`.
3. The graph loads the policy from SQL, the clause text from Cosmos, and the admission form.
4. `check_eligibility` applies the hard rules. A failure becomes Denied or Referred and skips the model.
5. If the checks pass, `assess_coverage` asks the coverage function for Approved or Partial.
6. `route_outcome` picks the final outcome. `persist_claim` writes amounts to SQL and the rationale to Cosmos.
7. `present_claim` returns one JSON object to the desk.

Claim status values: `Received`, `Decided`, `Confirmed`, `Returned`, `Errored`.

Outcomes: `Approved`, `Partial`, `Denied`, `Referred`.

## `config.py`

Holds settings. Local defaults need no `.env` file.

| Name | What it does |
| --- | --- |
| `BACKEND_ROOT` | The `backend/` directory. `data/` and `.env` live next to `app/`. |
| `_blank` | Reads one environment variable. An empty string becomes `None`, which keeps the local stand-in. |
| `Settings` | One object of paths and Azure credentials. |
| `Settings.from_env` | Loads `backend/.env`, then fills `Settings`. `DATA_DIR` overrides the folder for `claims.db` and `cosmos.json`. |
| `Settings.ensure_dirs` | Creates `data/` if it is missing. |
| `Settings.sql_url` | Returns `AZURE_SQL_URL` when it is set. Otherwise returns a SQLite URL for `data/claims.db`. |

## `db.py`

SQLAlchemy table classes. `SqlStore.init` creates these tables. No functions live here.

| Class | Table | What it stores |
| --- | --- | --- |
| `Base` |  | Shared base so SQLAlchemy knows these classes are tables. |
| `MemberRow` | `members` | Member id and name. |
| `PolicyRow` | `policies` | Policy number, plan, sum insured, amount already used, room-rent cap, start and end dates, status. |
| `ExclusionRow` | `exclusions` | A keyword on a plan. `kind` is `exclude` or `waiting`. Waiting rules also have `waiting_days` and a clause id. |
| `HospitalRow` | `hospitals` | Hospital name, city, and whether it is in the cashless network. |
| `AdmissionRow` | `admissions` | The hospital visit: diagnosis, treatment, bill estimate, room rent, stay length, and the admission-form text. |
| `ClaimRow` | `claims` | Status, outcome, payable amount, member share, confidence, who assessed it, and who confirmed it. |

## `seed.py`

Synthetic people and policy text. These are fixtures, not real patients.

| Name | What it does |
| --- | --- |
| `MEMBERS` | Ananya Shah (`GOLD`), Rohan Iyer (`SILVER`, room cap Rs 3,000), Meera Das (`GOLD-NEW`, policy started 1 Sep 2026), Vikram Nair (`GOLD`). |
| `HOSPITALS` | CityCare Hospital in Pune is in network. Lakeside Clinic in Nashik is not. |
| `EXCLUSIONS` | Every plan excludes the word `cosmetic`. `GOLD-NEW` also puts `arthroscopy` behind a 90-day wait. |
| `_common_clauses` | Builds the clause documents for one plan. The room-rent sentence uses that plan's cap. `with_wait=True` adds clause `CL-WAIT`. Each clause id is stored as `{plan}:{clause_id}`, for example `GOLD:CL-ROOM`. |
| `seed_clauses` | Returns the clauses for `GOLD` (cap 5000), `SILVER` (cap 3000), and `GOLD-NEW` (cap 5000, plus the wait clause). |

Clause ids the graph can cite:

| Id | Meaning |
| --- | --- |
| `CL-TERM` | The policy must be in force on the admission date. |
| `CL-NET` | Cashless cover is limited to network hospitals. |
| `CL-SURG` | Inpatient treatment is payable up to the remaining sum insured. |
| `CL-ROOM` | Room rent above the daily cap is the member's share. |
| `CL-SUM` | The payable amount cannot exceed the remaining sum insured. |
| `CL-FORM` | A legible admission form is required. |
| `CL-EXCL` | Cosmetic treatment is excluded. |
| `CL-WAIT` | Arthroscopy on `GOLD-NEW` waits 90 days. |

## `sql_store.py`

Reads and writes the tables in `db.py`. This is the system of record for amounts and status.

| Name | What it does |
| --- | --- |
| `money` | Rounds a rupee amount to two decimal places. |
| `SqlStore.__init__` | Opens SQLAlchemy against `settings.sql_url`. SQLite is allowed to be used from FastAPI's threads. `mode` is `sqlite` or `azure-sql`. |
| `SqlStore.init` | Creates any missing tables. If `members` is empty, inserts `MEMBERS`, `HOSPITALS`, and `EXCLUSIONS`. A second startup leaves existing claims in place. |
| `SqlStore.catalog` | Returns members with their policy fields, and hospitals sorted by name. The desk uses this to fill the form. |
| `SqlStore.require_member` | Loads one member. Raises `KeyError` when the id is unknown. |
| `SqlStore.require_hospital` | Loads one hospital. Raises `KeyError` when the id is unknown. |
| `SqlStore._next_id` | Builds the next id from the row count. The first admission is `ADM-1001` and the first claim is `CLM-1001`. |
| `SqlStore.create_admission_and_claim` | Inserts the admission and a claim in status `Received`. Returns both ids. The graph has not run yet. |
| `SqlStore.load_contract` | Joins admission, member, policy, hospital, and that plan's exclusions into one dictionary for the graph. |
| `SqlStore.save_decision` | Sets the claim to `Decided` and stores the outcome and amounts. The rationale goes to Cosmos, not here. |
| `SqlStore.mark_errored` | Sets status to `Errored` when the graph throws. |
| `SqlStore.confirm` | Sets status to `Confirmed` and records the officer name and time. Raises `KeyError` if the claim is missing. Raises `ValueError` unless the status is still `Decided`. |
| `SqlStore.send_back` | Sets status to `Returned`. Same missing-claim and status checks as `confirm`. |
| `SqlStore.list_claims` | Returns the queue: id, status, outcome, member, hospital, diagnosis, payable amount, admission time. Newest id first. |
| `SqlStore.claim_record` | Returns the full SQL side of one claim, including line items. Raises `KeyError` when the id is missing. The rationale is added later by `present_claim`. |

## `cosmos_store.py`

Stores policy wording and the decision packet. Amounts stay in SQL.

Both store classes expose the same four operations: `init`, `clauses_for_plan`, `save_packet`, `get_packet`.

| Name | What it does |
| --- | --- |
| `FileCosmosStore.__init__` | Points at `data/cosmos.json`. `mode` is `file`. |
| `FileCosmosStore.init` | If the file has no clauses, writes `seed_clauses()`. Existing packets are kept. |
| `FileCosmosStore.clauses_for_plan` | Returns every clause whose `plan_code` matches. |
| `FileCosmosStore.save_packet` | Stores the packet under `packets[claim_id]`. |
| `FileCosmosStore.get_packet` | Returns that packet, or `None`. |
| `FileCosmosStore._load` | Reads the JSON file. A missing file becomes `{"clauses": [], "packets": {}}`. |
| `FileCosmosStore._save` | Writes the JSON file with indentation. |
| `AzureCosmosStore.__init__` | Connects with `COSMOS_ENDPOINT` and `COSMOS_KEY`. Creates database `claimdesk` (or `COSMOS_DATABASE`), container `policy_clauses` partitioned by `/plan_code`, and container `claim_packets` partitioned by `/claim_id`. |
| `AzureCosmosStore.init` | If `policy_clauses` is empty, upserts the seed clauses. |
| `AzureCosmosStore.clauses_for_plan` | SQL-style query for that plan code. |
| `AzureCosmosStore.save_packet` | Upserts the packet. The Cosmos item id is the claim id. |
| `AzureCosmosStore.get_packet` | Reads that item. A missing item returns `None`. |
| `build_cosmos_store` | Returns `AzureCosmosStore` when endpoint and key are set and the client connects. Any other case returns `FileCosmosStore`. |

A packet written by the graph contains `claim_id`, `plan_code`, `rationale`, `cited_clause_ids`, `cited_clauses`, `checks`, `trace`, `coverage_provider`, and `confidence`.

## `documents.py`

Turns an admission form into text the eligibility check can accept or reject.

| Name | What it does |
| --- | --- |
| `DocumentReader.__init__` | Starts in `mode` `local`. If both Document Intelligence settings are set and the Azure client imports, builds that client and sets `mode` to `azure-document-intelligence`. A failed import stays on `local`. |
| `DocumentReader.extract` | Uses the pasted `document_text`. If Azure is configured and `file_bytes` were passed, replaces that text with the Azure read. The form is `usable` when the text is non-empty and does not contain `UNREADABLE`. Returns `document_name`, `text`, `usable`, and `provider`. |
| `DocumentReader._analyze` | Calls Azure's `prebuilt-read` model on the file bytes. A failed call returns an empty string, and `extract` keeps the pasted text. |

The current desk sends pasted text and does not send file bytes, so the local path is the one you see while clicking through the UI.

## `coverage.py`

Decides Approved or Partial after eligibility has passed. LangChain is the wrapper around Azure OpenAI. The graph calls whatever function `build_assessor` returned.

| Name | What it does |
| --- | --- |
| `CoverageDecision` | The JSON shape the model must return: outcome, payable amount, patient share, confidence, rationale, cited clause ids. |
| `SYSTEM_PROMPT` | Instructions for GPT-5.1: use only the supplied clauses, and pick one of the four outcomes. |
| `rule_assess` | The local assessor. Room rent above the cap becomes the member's share (`Partial`) and cites `CL-ROOM` plus `CL-SURG`. If the covered amount is above the remaining sum insured, the payable amount is capped and `CL-SUM` is cited. Otherwise the estimate is `Approved` and cites `CL-SURG`. Confidence is `0.9`. `provider` is `rules`. |
| `_normalize` | Cleans a model answer. Confidence above 1 is treated as a percent when it is at most 100. Clause ids that are not in the supplied wording are dropped. An unknown outcome becomes `Referred`. `provider` is `azure-openai`. |
| `build_assessor` | Returns `(function, mode)`. With no Azure OpenAI endpoint or key, the function is `rule_assess` and the mode is `rules`. With credentials, it builds `AzureChatOpenAI` for deployment `gpt-5.1`, pipes `SYSTEM_PROMPT` into structured output, and returns an inner `assess` function. Mode is `azure-openai:gpt-5.1`. |
| `assess` (inside `build_assessor`) | Sends the facts and clauses to the chain. On success, returns `_normalize`. If the call throws, it returns `rule_assess` and appends a sentence saying Azure OpenAI was unavailable. |

## `graph.py`

The LangGraph workflow. `ClaimState` is the dictionary passed from step to step. `trace` is a list of `{node, summary}` notes. Each step returns a new note, and LangGraph appends it.

| Name | What it does |
| --- | --- |
| `_note` | Builds one trace entry. |
| `build_claim_graph` | Defines the steps below, wires them, and returns a compiled graph. `main.py` calls `graph.invoke`. |
| `load_contract` | Calls `SqlStore.load_contract` and stores the contract on the state. |
| `load_wording` | Loads that plan's clauses from Cosmos. |
| `extract_form` | Calls `DocumentReader.extract` on the admission form text. |
| `check_eligibility` | Runs `_eligibility` and records whether the model may run. |
| `assess_coverage` | Builds the facts payload and calls `stores.assess`. This step is skipped when eligibility did not return `Continue`. |
| `route_outcome` | Calls `_route` and stores the final decision. |
| `persist_claim` | Writes the decision through `SqlStore.save_decision` and the packet through `save_packet`. |
| `after_eligibility` | Returns `assess_coverage` when the decision is `Continue`. Otherwise returns `route_outcome`, which skips the model. |

The compiled edges are:

```
load_contract → load_wording → extract_form → check_eligibility
check_eligibility → assess_coverage   (only when checks pass)
check_eligibility → route_outcome     (Denied or Referred)
assess_coverage → route_outcome → persist_claim → end
```

Helpers used by those steps:

| Name | What it does |
| --- | --- |
| `_eligibility` | Records five checks: policy in force, specified illness, exclusions, network hospital, admission form. The first hard failure wins, in that order. In force, waiting period, an exclusion keyword, or a non-network hospital returns `Denied` with a clause id. An unusable form returns `Referred` with `CL-FORM`. All checks passing returns `Continue`. |
| `_stop` | Packages a Denied or Referred result: decision, reason, clause ids, and the full check list. |
| `_route` | If eligibility already decided Denied or Referred, the payable amounts are 0 and `coverage_provider` is `not_called`. Otherwise it uses the assessment. No matching citation, or confidence under `0.55`, changes the outcome to `Referred` and clears the amounts. |

## `present.py`

| Name | What it does |
| --- | --- |
| `present_claim` | Loads the SQL record, then copies `rationale`, `cited_clauses`, `checks`, and `trace` from the Cosmos packet onto it. A claim with no packet still returns, with those four fields empty. This is the JSON shape `GET /api/claims/{id}` and the create/confirm/return routes send to the desk. |

## `runtime.py`

| Name | What it does |
| --- | --- |
| `Stores` | The bag the graph closes over: settings, SQL, Cosmos, documents, the assess function, and `coverage_mode`. |
| `build_stores` | Calls `build_assessor`, `SqlStore`, `build_cosmos_store`, and `DocumentReader`, and returns one `Stores`. |

## `main.py`

The FastAPI app. Importing this module calls `create_app()`, which is what `uvicorn app.main:app` serves.

| Name | What it does |
| --- | --- |
| `ClaimCreate` | Body for `POST /api/claims`. Diagnosis and treatment need at least 2 characters. The estimate must be above 0. Stay length is 1 to 60 days. |
| `ConfirmBody` | Body for confirm. `officer_name` defaults to `Duty officer`. |
| `create_app` | Builds stores and the graph, then registers the routes below. Tests call this with a temporary `Settings` so they get their own SQLite file. |
| `lifespan` | On startup, calls `sql.init()` and `cosmos.init()`. |
| `health` | `GET /api/health`. Returns the active mode of SQL, Cosmos, documents, and coverage. The desk prints this line under the title. |
| `catalog` | `GET /api/catalog`. Members and hospitals for the form. |
| `list_claims` | `GET /api/claims`. The queue. |
| `get_claim` | `GET /api/claims/{claim_id}`. One claim, or 404. |
| `create_claim` | `POST /api/claims`. Validates the member and hospital, inserts the rows, runs the graph, and returns the presented claim. A graph failure marks the claim `Errored` and returns 500. |
| `confirm_claim` | `POST /api/claims/{claim_id}/confirm`. Officer confirms a `Decided` claim. |
| `return_claim` | `POST /api/claims/{claim_id}/return`. Officer sends a `Decided` claim back. |
| `_act` | Runs confirm or send-back. `KeyError` becomes 404. `ValueError` becomes 409 because the claim is no longer waiting. |
| `app` | The process-wide app, created from environment settings. |

CORS allows the Vite desk at `http://localhost:5173` and `http://127.0.0.1:5173`.
