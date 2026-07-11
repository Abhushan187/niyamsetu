# Niyamsetu (नियमसेतु)

Context-aware conversational AI platform for querying Maharashtra Government Resolution (GR) documents in English and Marathi.

## Problem

Maharashtra government issues 800+ GRs annually, stored as scanned, unsearchable PDFs on portals like Aaple Sarkar. Officials waste hours finding specific clauses. Niyamsetu enables natural language querying, auto-summarization, and GR relationship detection (supersession/amendment) — fully on-premise for DPDP Act compliance.

## Tech Stack

- **Backend:** FastAPI, MongoDB (Motor), FAISS, LangChain, Ollama (phi4-mini / llama3:8b)
- **Frontend:** React 19, Vite, Tailwind (base styles only), Axios, React Router
- **Auth:** JWT (python-jose), bcrypt password hashing

## Prerequisites

- Python 3.13
- Node.js 18+
- MongoDB running locally on `localhost:27017`
- Ollama installed (https://ollama.com), with models pulled:
  ollama pull phi4-mini
  ollama pull nomic-embed-text

## Setup

### 1. Clone and configure

git clone https://github.com/Abhushan187/niyamsetu.git
cd niyamsetu

Create `backend/.env`:

MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=niyamsetu
JWT_SECRET=change-this-to-something-random
JWT_EXPIRE_HOURS=24
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=phi4-mini
DATA_DIR=./data

### 2. Backend

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
# source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt --only-binary=:all:
uvicorn main:app --reload --host 0.0.0.0 --port 8000

Backend runs at http://localhost:8000. API docs at http://localhost:8000/docs.

### 3. Frontend

cd frontend
npm install
npm run dev

Frontend runs at http://localhost:5173.

### 4. Start Ollama (separate terminal)

ollama serve

## Default Credentials

Seeded automatically on first backend startup if the `users` collection is empty.

| Username | Password  | Role  |
|----------|-----------|-------|
| admin    | admin123  | admin |
| user1    | user123   | user  |

**Change these before any real deployment.**

## Project Structure

```
niyamsetu/
├── backend/
│   ├── auth/       — JWT auth, login, user management
│   ├── api/        — HTTP route handlers (upload, embed, query, graph, summary, logs, sessions)
│   ├── core/       — business logic (RAG pipeline, vectorstore, graph detection, summarizer)
│   ├── db/         — MongoDB read/write operations
│   └── data/       — grdocs/ (uploaded PDFs), vectorstore/ (FAISS), summaries/ (generated)
└── frontend/
    └── src/
        ├── pages/       — route-level pages
        ├── components/  — shared UI (Navbar, Sidebar, Layout)
        ├── context/      — AuthContext, ChatContext
        └── api/          — Axios client
```

## Workflow for Contributors

1. Create a feature branch off `main`.
2. Backend: business logic goes in `core/`, HTTP handling in `api/`, DB ops in `db/` — never mix these.
3. Frontend: inline styles only (no Tailwind classes), state via Context, all API calls through `src/api/client.js`.
4. Open a PR — CI runs the offline test suite automatically (`test_units.py` + `test_config.py`, no external services required).
5. Before approving any PR, run the full test suite locally: `python tests/run_all_tests.py` (no `--offline` flag). This includes `test_integration.py`, which requires MongoDB and Ollama running — currently only Harsh's machine has both. Harsh should run this before approving merges to `main`.
6. PRs are reviewed before merging to `main`.

## Known Constraints

- **Do not use MongoDB Atlas** — Python 3.13 has a TLS incompatibility with Atlas. Local MongoDB only.
- **No cloud services** — architecture is on-premise/air-gapped by design for DPDP Act compliance.
- `phi4-mini` is the default LLM (runs on 4-6GB RAM); `llama3:8b` is used only on machines with 16GB+ RAM and a dedicated GPU for higher-quality testing.

## License

Copyright application in progress. All rights reserved pending filing.