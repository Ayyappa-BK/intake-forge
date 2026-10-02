# Intake Forge

A small dataset intake console that keeps invalid records out of the training table. It validates JSONL, commits accepted records and a batch receipt together, and compares the new label mix with the prior dataset.

## Run locally

Use Python 3.11+ and Node.js 24 with npm. Python has no third-party dependencies. From the cloned repository root:

```sh
cd frontend
npm ci
npm run build
cd ..
python3 backend/server.py
```

Open http://localhost:8312. On Windows, use `py` in place of `python3`. The Python server serves both the compiled React app and the REST API. No API keys, downloaded model weights, or paid services are needed. The first npm install requires internet access.

For frontend development, keep the Python server running and use a second terminal:

```sh
cd frontend
npm run dev
```

Vite runs at http://localhost:8412 and proxies `/api` to the Python server. Set `PORT` to change the backend port; update `frontend/vite.config.ts` if you also use the development proxy. The backend binds to localhost by default.

## Try it

1. Commit the original sample. It contains valid records, a duplicate ID, an empty text value, an unknown label, and malformed JSON.
2. Inspect quarantine reasons and original line numbers.
3. Commit the same sample again. The receipt is marked as replayed and the record count stays unchanged.
4. Load the shifted batch and commit it. Its all-negative label mix raises a distribution warning.

Supply one JSON object per line. Each needs a string `id`, nonempty `text`, and a `positive`, `negative`, or `neutral` label. IDs must be unique within a batch. Limits: 5,000 lines, 1 MB of UTF-8 input, and 10,000 characters per text field.

## How it works

`backend/domain.py` validates rows and writes to SQLite. A SHA-256 digest of the original input bytes is the idempotency key. Whitespace changes create a new batch; IDs may recur across separate batches. The record primary key is `(batch, id)`.

A transaction stores accepted records and their receipt together. Quarantine stays in the receipt, so the UI can show the original input and the rejection reason. A process lock serializes intake, and SQL parameters keep user strings out of executable SQL.

Drift uses base-2 Jensen–Shannon divergence between the accepted batch and all previously accepted records. It ranges from zero to one; a value above 0.15 raises a warning but does not reject the batch. The first batch has no reference distribution. Label drift is only one quality signal and does not measure feature or semantic drift.

Data persists in `.data/intake.sqlite3`. Set `DATA_DIR` to choose another directory. Stop the server and remove `.data` to reset the default local database. Recent receipts are limited to 20 in the UI; the database retains every batch.

The frontend is React and TypeScript; Vite builds static assets. The Python standard-library HTTP server validates JSON requests, limits payloads to 2 MB, and emits request-duration logs. Errors appear inline in the interface. React renders user text as text rather than HTML.

## API

`GET /api/health` returns a liveness check. `GET /api/state` returns the current dashboard state.

```text
POST /api/ingest
{"lines":"{\"id\":\"r1\",\"text\":\"great sync\",\"label\":\"positive\"}"}
```

POST endpoints expect `Content-Type: application/json`. Invalid inputs return HTTP 400 with an `error` field. Oversized requests return 413. These endpoints have no authentication and are intended for local use; the standard-library server is not a production ingress server.

## Checks

```sh
python3 -m unittest discover -s backend -p 'test_*.py' -v
cd frontend
npm ci
npm run build
```

Tests exercise domain behavior and HTTP validation. The frontend build includes strict TypeScript checking. GitHub Actions runs both on pushes and pull requests.

## Docker

```sh
docker build -t intake-forge .
docker run --rm -p 127.0.0.1:8312:8312 intake-forge
```

The image builds the frontend and serves it from Python under a non-root user. Docker is optional. For persistent Docker storage:

```sh
docker volume create intake-data
docker run --rm -p 127.0.0.1:8312:8312 -v intake-data:/app/.data intake-forge
```

## Platform engineering focus

The project connects a React workflow to Python validation, transactional ingestion, SQL analytics, and quality monitoring. A practical next step is a streaming input adapter with schema versions and reviewable quarantine exports.

## Layout

```text
backend/                 API server, domain logic, and tests
frontend/src/            React interface and styles
frontend/package-lock.json  Reproducible dependency installation
data/                    Bundled fixtures
.github/workflows/       Build and test checks
```

MIT licensed. See `LICENSE`.
