# ChronoGraph

ChronoGraph is a local demo for exploring engineering decisions as a temporal evidence graph. It combines a React-based investigation workspace with a FastAPI backend that serves graph-style responses from synthetic evidence data.

## User guide

### 1. Prerequisites

Make sure you have:
- Node.js and npm installed
- Python 3.12 installed
- The project dependencies installed

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
npm install
```

### 2. Start the application

Run the full local demo:

```bash
npm run dev:full
```

This starts:
- the frontend at http://localhost:3000
- the backend API at http://localhost:8002

If you want to run the services separately:

```bash
npm run dev
```

```bash
C:/Users/admin/AppData/Local/Programs/Python/Python312/python.exe backend/main.py
```

### 3. Use the workspace

Once the app loads:
- Type a question in the input box, such as "What did Sarah say about the migration?"
- Click one of the example prompts to preload a common investigation question
- Click a citation or graph edge to inspect the supporting evidence
- Use the timeline panel to jump between evidence entries
- Click Reset to clear the current conversation and restore the default narrative

### 4. API checks

You can also test the backend directly:

```bash
curl http://localhost:8002/health
```

```bash
curl -X POST http://localhost:8002/query -H "Content-Type: application/json" -d '{"question":"What did Sarah say about the migration?","history":[]}'
```

### 5. Build and verify

Run the test suite:

```bash
C:/Users/admin/AppData/Local/Programs/Python/Python312/python.exe -m unittest tests.test_backend
```

Build the frontend:

```bash
npm run build
```

## Project structure

- app/: Next.js frontend UI
- backend/: FastAPI API server
- data/: raw and processed evidence data
- pipeline/: scripts for processing and loading evidence
- tests/: backend regression tests
