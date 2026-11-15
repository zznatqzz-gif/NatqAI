# NatqAI Backend

## Run locally

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then set NATQAI_SECRET_KEY in your shell/environment
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Initial endpoints
- `GET /health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/users/me` (Bearer token)
- `GET|POST /api/v1/projects` (Bearer token)
- `DELETE /api/v1/projects/{project_id}` (Bearer token)
- `POST /api/v1/chats` and `POST /api/v1/chats/{chat_id}/messages`
- `GET /api/v1/wallet` (Bearer token)

Chat requests use the configured OpenAI-compatible provider. Set `NATQAI_AI_API_KEY` before sending messages; without it, the API returns a configuration error and does not save a fake assistant reply.

## Web Chat UI

The Arabic-first responsive chat interface is served by the same FastAPI app:

```bash
cd backend
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`. The UI supports account registration/login, creating and reopening conversations, loading message history, and sending messages to the configured AI provider. The frontend is plain HTML/CSS/JavaScript and requires no Node build step.


## Security configuration

- Keep `NATQAI_SECRET_KEY` private and use a unique random value of at least 32 characters in production.
- Set `NATQAI_ENV=production` to enable strict startup checks for the secret and CORS configuration.
- Set `NATQAI_CORS_ORIGINS` to a comma-separated allowlist of trusted frontend origins. Wildcard origins are rejected in production.
- The SQLite connection enables foreign keys and a bounded busy timeout. Back up the database before upgrades.

## Tests

```bash
cd backend
python -m unittest discover -s tests -v
```


## Persistent media worker

Media jobs are persisted in SQLite before processing. Run the API and a separate worker process against the same database:

```bash
# from backend/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python worker.py
```

The worker polls queued jobs, claims them atomically, retries failures up to `max_attempts` with a bounded delay, and re-queues interrupted `running` jobs on worker startup. For multi-instance production deployments, use a shared database with appropriate locking or migrate the queue to a dedicated broker.


## Container deployment preparation (v9)

A Dockerfile and Railway configuration are provided at `backend/Dockerfile`
and `backend/railway.json`. Deploy from the repository root so the Dockerfile
can copy both `backend/` and `frontend/`.

For production, configure these variables in the hosting service:
- `NATQAI_ENV=production`
- `NATQAI_SECRET_KEY` (unique random value, at least 32 characters)
- `NATQAI_CORS_ORIGINS` (comma-separated public origins; no wildcard)
- `NATQAI_AI_BASE_URL`, `NATQAI_AI_API_KEY`, `NATQAI_AI_MODEL`

Attach a persistent volume at `/data`; the container defaults the SQLite
database to `/data/natqai.db`. Do not deploy production without persistent
storage and backups. The media worker is a separate process and is not
started by the web container.


## Upload a workspace ZIP to Railway from NatqAI (v15)

The production container installs Railway CLI. After a user connects a Railway
account inside NatqAI, uploads a validated ZIP to an owned workspace project,
and selects a Railway project/service/environment, the UI can submit a deploy
request. The API validates target ownership within Railway, stages the archive
in a temporary directory, and invokes `railway up` with explicit target IDs.
Railway performs the build; generated project code is not executed by the NatqAI
API container. The detached CLI response is only a queued/triggered state, not
proof of successful deployment. Check the Railway deployment state for `SUCCESS`.

The deploy API is `POST /api/v1/projects/{project_id}/deployment-source/deploy`;
read its job using `GET /api/v1/projects/{project_id}/deployment-source/runs/{run_id}`.
This workflow requires the Railway CLI in the deployed container and a valid
per-user Railway token. It has been tested with a mocked CLI, not a live Railway
account. Configure persistent storage for both the SQLite database and private
ZIP archive directory before production use.

### Android APK builder (optional isolated service)

Set `ANDROID_BUILDER_URL` and `ANDROID_BUILDER_TOKEN` on the API only after deploying the separate service in `android_builder/`. The builder must remain private and must not receive Docker socket mounts. See `android_builder/README_AR.md`. Without these settings, the APK endpoint returns HTTP 503 instead of claiming a build is available.
