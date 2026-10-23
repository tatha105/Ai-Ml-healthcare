# Hospital policy claim desk

A proof of concept for cashless claims at hospital admission. Staff register an admission, a LangGraph workflow checks the policy, and an officer confirms the recommendation.

Synthetic members only. This is not a clinical tool and it does not pay a hospital.

## Flow

1. The React claim desk registers the admission.
2. FastAPI opens a claim and starts one LangGraph thread.
3. The graph loads the contract from the SQL store, the clause text from the Cosmos store, and the admission form.
4. Eligibility runs in code: policy in force, waiting period, exclusions, network hospital, legible form.
5. A hard stop becomes Denied or Referred, and GPT-5.1 is not called.
6. Otherwise LangChain asks Azure OpenAI for a structured decision. Without Azure credentials, the same schema is filled by coverage rules.
7. Amounts are saved in SQL. The rationale, citations, and graph trace are saved as a Cosmos packet.
8. The officer confirms or sends the claim back.

## Run

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The sample admissions cover an approval, a room-rent partial, a waiting-period denial, an unreadable form, and an out-of-network denial.

The end-to-end code walkthrough, from the HTTP request through each line that runs, is in [DEMO.md](DEMO.md). File-by-file notes for the API are in [backend/app/README.md](backend/app/README.md).

Copy `backend/.env.example` to `backend/.env` and fill the Azure values when you want the live services. Empty values keep the local stand-ins:

| Setting | Local stand-in | Azure service |
| --- | --- | --- |
| `AZURE_SQL_URL` | SQLite | Azure SQL, as a SQLAlchemy URL |
| `COSMOS_ENDPOINT`, `COSMOS_KEY` | JSON file | Cosmos DB |
| Document Intelligence endpoint and key | Pasted admission text | Azure AI Document Intelligence |
| Azure OpenAI endpoint and key | Coverage rules | Deployment `gpt-5.1` through LangChain |

Azure SQL needs `pyodbc` and the ODBC driver on the machine. The URL is passed straight to SQLAlchemy.

```bash
cd backend && .venv/bin/pytest
```
