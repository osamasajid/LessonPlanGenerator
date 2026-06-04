# AI Lesson Plan Architect

A multi-agent, asynchronous system that takes structured lesson inputs from teachers and generates a detailed lesson plan and an independent, rubric-based evaluation.

The system uses an **async FastAPI backend**, a **Celery task queue with a Redis broker** (running in Docker), a **multi-model LLM client** (defaulting to local **Ollama** for development), and a **premium single-page HTML/JS UI**.

---

## Architecture Overview

1. **Teacher UI (`ui/index.html`)**: Single-file glassmorphic dark interface. Accepts form inputs, submits requests asynchronously to the API, polls the status endpoint, and renders the markdown result using `marked.js`.
2. **FastAPI Web Server (`api/main.py`)**: Exposes REST endpoints to submit requests (`POST /api/requests`), check request status/results (`GET /api/requests/{id}`), and list recent history.
3. **Database (`api/database.py`, `api/models.py`)**: Stores requests and results in an asynchronous SQLite database (`lesson_plans.db`) using SQLAlchemy with `aiosqlite`.
4. **Celery Worker (`worker/worker.py`, `worker/celery_app.py`)**: Processes background generation tasks offloaded to the Redis broker. Configured for Windows compatibility.
5. **Multi-Model Pipeline (`agents/`)**:
   - `llm_client.py`: Uniform async wrapper supporting **Ollama** (local), **Claude** (Anthropic), and **Gemini** (Google).
   - `lesson_plan_agent.py`: Generates the structured lesson plan markdown.
   - `evaluation_agent.py`: Reviews the plan against a 8-criteria rubric scoring 1–5.
   - `orchestrator.py`: Coordinates status changes and sequential agent execution.

---

## Prerequisites

- **Python**: Version 3.12+
- **Docker**: For running the Redis message broker container.
- **Ollama**: Running locally with the `qwen2.5-coder:7b` model pulled (`ollama pull qwen2.5-coder:7b`).

---

## Setup & Runbook

There are two ways to boot the application stack: **Option A (Docker Compose)** which is easiest and packages all components, and **Option B (Manual)** which is best for debugging.

### Option A: Running with Docker Compose (Recommended)

1. Make sure **Ollama** is running locally and has the model pulled:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
2. Build and start all services (Redis, API Web Server, and Celery Worker):
   ```bash
   docker compose up --build
   ```
3. Open the UI by loading `ui/index.html` in your browser, or serve it:
   ```bash
   python -m http.server 3000 --directory ui/
   ```
   Then navigate to `http://localhost:3000`.

---

### Option B: Manual Startup (Development)

1. **Start Redis in Docker**:
   ```bash
   docker run -d --name lesson-redis -p 6379:6379 redis:alpine
   ```

2. **Set Up Python Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\pip install -r requirements.txt
   ```

3. **Configure Environment Variables (`.env`)**:
   Create a `.env` file with:
   ```ini
   LLM_PROVIDER=ollama
   OLLAMA_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5-coder:7b
   ```

4. **Run the API Server**:
   ```bash
   .\venv\Scripts\uvicorn api.main:app --reload --port 8000
   ```

5. **Run the Celery Worker** (in a separate terminal):
   ```bash
   .\venv\Scripts\python -m worker.worker
   ```

6. **Serve the UI**:
   ```bash
   python -m http.server 3000 --directory ui/
   ```
   Then navigate to `http://localhost:3000`.


---

## Verifying the Setup

To run a direct, end-to-end integration test of the database, local Ollama connectivity, and the agent orchestrator pipeline, run the verification script:
```bash
.\venv\Scripts\python tests/test_flow.py
```
This test script will insert a test request, invoke the orchestrator locally, generate a plan/evaluation via local Ollama, and print a truncated version of the generated text to verify success.
