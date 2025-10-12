# fuzzy-fortnight

Agentic interview orchestration playground. The repository now includes scaffolding for
agent packages, configuration management, and a SQLite-backed persistence layer in addition to
the existing FastAPI services and UI experiments.

## Development quickstart

```bash
make install
cp .env.example .env  # customise if needed
make migrate          # create the SQLite schema
make test             # run unit tests
make lint             # optional: run Ruff + mypy
make run              # start the FastAPI service on http://localhost:5001
```

The default settings place the SQLite database at `data/interview.db`. Override any value via
environment variables (see `.env.example`).

## Project layout

- `agents/` — shared types for agent components (Stage 3+ will add implementations).
- `config/` — environment-driven settings and a simple model registry for binding LLM callables.
- `storage/` — SQLite helpers, schema migration, and strongly-typed insert adapters.
- `tests/` — pytest suite including smoke tests, existing competency tooling tests, and database
  adapter coverage.
- `api_server.py` — FastAPI application exposing the job-description analysis endpoints used by the UI.
- `ui/` — Vite + React client.

## Running the existing stack manually

If you prefer to manage dependencies without `make`, the legacy workflow still works:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m storage.migrate
uvicorn api_server:app --reload --port 5001
```

In a separate terminal you can start the React UI via Vite:

```bash
cd ui
npm install
npm run dev
```

The Vite dev server proxies `/api` calls to the FastAPI backend running on port 5001. Remember to set
`LLM_API_KEY` in your environment if any LLM gateway integrations require authentication.
