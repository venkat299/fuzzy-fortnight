# fuzzy-fortnight

Python modules:

- `config.py` loads `app_config.json` and resolves LLM routes.
- `llm_gateway.py` provides a validated interface to call configured LLM endpoints.
- `jd_analysis.py` turns job descriptions into competency matrices for the UI.
- `api_server.py` exposes the job-description analysis as a FastAPI service for the UI.

Configuration lives in `app_config.json`. Set the `LLM_API_KEY` environment variable to authorize requests to the configured model endpoint.

## Running the stack

### Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api_server:app --reload --port 5001
```

In a separate terminal start the React UI with Vite:

```bash
cd ui
npm install
npm run dev
```

The Vite dev server proxies `/api` calls to the FastAPI backend running on port 5001.

### Docker Compose

Build and start both the FastAPI backend and the React UI behind an Nginx proxy:

```bash
docker compose up --build
```

The services expose the following ports on your host machine:

- `http://localhost:5001` — FastAPI backend
- `http://localhost:5173` — React UI served via Nginx (proxies `/api` to the backend)

Set `LLM_API_KEY` in your environment before running `docker compose` if the LLM gateway requires authentication.
