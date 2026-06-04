# AI Lesson Plan Generator — System Design Document

**Version:** 1.1  
**Audience:** Engineering Team  
**Status:** Completed & Integrated

---

## 1. Overview

A multi-agent system that accepts structured input from a teacher and asynchronously generates a detailed lesson plan (Markdown) plus an independent rubric-based evaluation. The system exposes a REST API, a premium responsive glassmorphic UI, a background task pipeline managed via Celery/Redis, an async SQLite database using SQLAlchemy, and comprehensive OpenTelemetry tracing with Jaeger visualization.

---

## 2. Goals & Non-Goals

### Goals
- Teachers can submit a lesson plan request in under 60 seconds via a web interface.
- Requests are processed asynchronously; the UI polls status and updates a detailed progress bar.
- Direct integration with multiple LLM backends (local Ollama, Google Gemini, Anthropic Claude) via a modular client.
- Rich observability: track token counts, individual agent latencies, total task durations, and visual rubric score percentages.
- Tracing integration: trace client and backend request lifetimes using OpenTelemetry spans visible in Jaeger.
- Persist all requests, metadata, and responses in a SQLite database with automatic table creation on startup.

### Non-Goals (v1)
- User authentication / multi-tenancy (single-user or trusted intranet deployment).
- Real-time streaming of agent output.
- PDF/DOCX export.
- Editing or regenerating plans directly from the UI.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Teacher Browser                       │
│              (HTML + Vanilla CSS + JS Frontend)              │
└──────────────┬──────────────────────────────▲───────────────┘
               │ REST (JSON)                  │ Poll & Trace Link
               ▼                              │
┌─────────────────────────────────────────────┴───────────────┐
│                      FastAPI Backend                        │
│  POST /api/requests       GET /api/requests/{id}            │
│  GET /api/requests        GET /api/metrics                  │
└──────────────┬──────────────────────────────────────────────┘
               │ enqueue (Celery task)
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Task Queue (Redis)                       │
└──────────────┬──────────────────────────────────────────────┘
               │ pick up
               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Celery Worker (Solo Pool)                  │
│  ─────────────────────────────────────────────────────────  │
│                     Orchestrator Agent                      │
│   1. Update request status -> "processing"                  │
│   2. Start OTel trace child spans                           │
│   3. Call Lesson Plan Agent via LLMClient -> lesson_plan_md  │
│   4. Call Evaluation Agent via LLMClient -> evaluation_md   │
│   5. Parse criteria/overall scores from evaluation          │
│   6. Write results, tokens, latencies, & scores to DB       │
│   7. Update status -> "done" / "failed"                     │
└──────────────┬──────────────────┬───────────────────────────┘
               │                  │
               ▼                  ▼
┌────────────────────┐  ┌───────────────────────┐
│  Lesson Plan Agent │  │   Evaluation Agent     │
└──────────────┬─────┘  └─────┬─────────────────┘
               │              │
               ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                  LLMClient (Router Interface)                │
│    - Ollama (Local qwen2.5-coder:7b HTTP client)            │
│    - Gemini (Google gemini-2.5-flash HTTP client)            │
│    - Anthropic (Claude claude-3-5-sonnet SDK client)        │
└─────────────────────────────────────────────────────────────┘
                               │
                      Reads / Writes Records
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     SQLite Database                         │
│                  (lesson_requests table)                    │
└─────────────────────────────────────────────────────────────┘

======================= OBSERVABILITY =========================
- FastAPI & Celery workers auto-instrumented with OpenTelemetry.
- Trace spans exported via OTLP gRPC to Jaeger Query UI (port 16686).
- Trace IDs stored in DB and exposed to UI frontend for deep tracing.
```

---

## 4. Data Model

### Table: `lesson_requests`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated on insert |
| `grade` | VARCHAR(50) | e.g. "Grade 7", "Class 10" |
| `subject` | VARCHAR(100) | e.g. "Mathematics", "Science" |
| `board` | VARCHAR(100) | e.g. "CBSE", "ICSE", "IB", "State Board" |
| `topic` | VARCHAR(255) | e.g. "Photosynthesis" |
| `methodology` | TEXT NULL | Optional. e.g. "Inquiry-based learning" |
| `instructions` | TEXT NULL | Optional free-text additional instructions |
| `status` | VARCHAR(20) | `pending` → `processing` → `done` / `failed` |
| `lesson_plan_md` | TEXT NULL | Markdown output from Lesson Plan Agent |
| `evaluation_md` | TEXT NULL | Markdown output from Evaluation Agent |
| `error_message` | TEXT NULL | Populated on failure |
| `created_at` | DATETIME | UTC, default now() |
| `completed_at` | DATETIME NULL | UTC, set when status = done/failed |
| `generation_time_seconds` | FLOAT NULL | Latency of the generation agent execution step |
| `evaluation_time_seconds` | FLOAT NULL | Latency of the evaluation agent execution step |
| `plan_input_tokens` | INTEGER NULL | Input tokens sent for plan generation |
| `plan_output_tokens` | INTEGER NULL | Output tokens received for plan generation |
| `eval_input_tokens` | INTEGER NULL | Input tokens sent for plan evaluation |
| `eval_output_tokens` | INTEGER NULL | Output tokens received for plan evaluation |
| `score_clarity` | INTEGER NULL | Rubric Criterion 1 parsed score (1-5) |
| `score_alignment` | INTEGER NULL | Rubric Criterion 2 parsed score (1-5) |
| `score_structure` | INTEGER NULL | Rubric Criterion 3 parsed score (1-5) |
| `score_engagement` | INTEGER NULL | Rubric Criterion 4 parsed score (1-5) |
| `score_differentiation` | INTEGER NULL | Rubric Criterion 5 parsed score (1-5) |
| `score_assessment` | INTEGER NULL | Rubric Criterion 6 parsed score (1-5) |
| `score_feasibility` | INTEGER NULL | Rubric Criterion 7 parsed score (1-5) |
| `score_overall` | FLOAT NULL | Overall average rubric score (1.0 - 5.0) |
| `trace_id` | VARCHAR(32) NULL | OpenTelemetry Trace ID string for Jaeger tracking |

---

## 5. API Specification

### `POST /api/requests`

Create a new lesson plan request.

**Request body:**
```json
{
  "grade": "Grade 8",
  "subject": "Science",
  "board": "CBSE",
  "topic": "Photosynthesis",
  "methodology": "Inquiry-based learning",
  "instructions": "Include a hands-on activity"
}
```

**Response `202 Accepted`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

---

### `GET /api/requests/{request_id}`

Poll for status, parsed metadata, latencies, tokens, rubric scores, and results.

**Response `200 OK`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "grade": "Grade 8",
  "subject": "Science",
  "board": "CBSE",
  "topic": "Photosynthesis",
  "methodology": "Inquiry-based learning",
  "instructions": "Include a hands-on activity",
  "status": "done",
  "lesson_plan_md": "# Lesson Plan\n...",
  "evaluation_md": "## Evaluation\n...",
  "error_message": null,
  "created_at": "2026-06-04T10:00:00Z",
  "completed_at": "2026-06-04T10:01:45Z",
  "provider": "gemini",
  "model_name": "gemini-2.5-flash",
  "generation_time_seconds": 15.42,
  "evaluation_time_seconds": 18.11,
  "plan_input_tokens": 420,
  "plan_output_tokens": 1250,
  "eval_input_tokens": 1300,
  "eval_output_tokens": 620,
  "score_clarity": 5,
  "score_alignment": 4,
  "score_structure": 5,
  "score_engagement": 4,
  "score_differentiation": 4,
  "score_assessment": 5,
  "score_feasibility": 4,
  "score_overall": 4.43,
  "trace_id": "8bfa2e2dcfc623d3876e6a1476dbe21b"
}
```

---

### `GET /api/requests`

List all requests (most recent first). Optional query params: `?limit=20&offset=0`

**Response `200 OK`:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "grade": "Grade 8",
    "subject": "Science",
    "board": "CBSE",
    "topic": "Photosynthesis",
    "methodology": "Inquiry-based learning",
    "instructions": "Include a hands-on activity",
    "status": "done",
    "lesson_plan_md": "# Lesson Plan\n...",
    "evaluation_md": "## Evaluation\n...",
    "error_message": null,
    "created_at": "2026-06-04T10:00:00Z",
    "completed_at": "2026-06-04T10:01:45Z",
    "provider": "gemini",
    "model_name": "gemini-2.5-flash",
    "generation_time_seconds": 15.42,
    "evaluation_time_seconds": 18.11,
    "plan_input_tokens": 420,
    "plan_output_tokens": 1250,
    "eval_input_tokens": 1300,
    "eval_output_tokens": 620,
    "score_clarity": 5,
    "score_alignment": 4,
    "score_structure": 5,
    "score_engagement": 4,
    "score_differentiation": 4,
    "score_assessment": 5,
    "score_feasibility": 4,
    "score_overall": 4.43,
    "trace_id": "8bfa2e2dcfc623d3876e6a1476dbe21b"
  }
]
```

---

### `GET /api/metrics`

Get system observability latency percentiles and error metrics.

**Response `200 OK`:**
```json
{
  "total_requests": 15,
  "successful_requests": 14,
  "failed_requests": 1,
  "error_rate_pct": 6.67,
  "overall_p50_seconds": 32.53,
  "overall_p90_seconds": 45.21,
  "overall_p95_seconds": 48.95,
  "generation_p50_seconds": 15.11,
  "generation_p90_seconds": 22.42,
  "generation_p95_seconds": 24.81,
  "evaluation_p50_seconds": 16.82,
  "evaluation_p90_seconds": 21.91,
  "evaluation_p95_seconds": 23.22
}
```

---

## 6. Agent System

### 6.1 Orchestrator

**File:** `agents/orchestrator.py`

Background task picked up by Celery. It manages the asynchronous end-to-end execution of agents within OpenTelemetry tracing spans:

```
1. Fetch request details from database
2. Transition status → "processing" and save
3. Start a parent OTel trace span: "orchestrate_lesson_plan"
4. Start a child span: "lesson_plan_generation"
   - Call Lesson Plan Agent via LLMClient
   - Record latency and input/output tokens
5. Start a child span: "rubric_evaluation"
   - Call Evaluation Agent via LLMClient with plan markdown
   - Record latency and input/output tokens
6. Parse evaluation markdown using regex:
   - Extract numerical scores (1-5) for 7 criteria (Clarity, Alignment, Structure, Engagement, Differentiation, Assessment, Feasibility)
   - Extract/calculate overall average score
7. Save markdown outputs, latencies, tokens, rubric scores, and complete status → "done"
8. If any step fails:
   - Catch exception, record it on the tracing span, mark status → "failed" and record error_message
```

---

### 6.2 Lesson Plan Agent

**File:** `agents/lesson_plan_agent.py`

**Input:** Structured request fields  
**Output:** Markdown string containing all standard sections

**System prompt:**
```
You are an expert curriculum designer and experienced teacher.
Generate a comprehensive, structured lesson plan in Markdown.
The lesson plan must include all sections listed below.
Be practical, age-appropriate, and aligned with the specified board's curriculum standards.

Required sections (use these exact headings):
## Lesson Overview
## Learning Objectives
## Prerequisites
## Materials & Resources
## Lesson Structure
  ### Hook / Introduction (duration)
  ### Direct Instruction (duration)
  ### Guided Practice (duration)
  ### Independent Practice (duration)
  ### Closure & Summary (duration)
## Differentiation Strategies
  ### For Advanced Learners
  ### For Students Needing Support
## Assessment
## Homework / Extension
## Teacher Notes
```

---

### 6.3 Evaluation Agent

**File:** `agents/evaluation_agent.py`

**Input:** Generated Lesson Plan markdown text  
**Output:** Markdown string evaluation containing structured rubric scores

**System prompt:**
```
You are a senior curriculum evaluator and instructional coach.
Your job is to critically evaluate a lesson plan using the rubric below.
Be honest, specific, and constructive. Score each criterion 1–5.
Output ONLY Markdown.

Rubric Criteria:
1. Clarity of Learning Objectives (are they measurable and grade-appropriate?)
2. Curriculum Alignment (does content match the stated board and grade level?)
3. Pedagogical Structure (logical flow: hook → instruction → practice → closure)
4. Student Engagement (variety of activities, relevance, and motivation)
5. Differentiation (does it address diverse learner needs?)
6. Assessment Quality (are assessments aligned with objectives?)
7. Feasibility (is it achievable within a standard class period with available materials?)
8. Overall Recommendation

For each criterion output:
**Score:** X/5
**Strengths:** ...
**Areas for Improvement:** ...

End with an **Overall Score** (average) and a 2–3 sentence **Summary Recommendation**.
```

---

### 6.4 LLM Routing Client

**File:** `agents/llm_client.py`

Provides a unified asynchronous wrapper (`LLMClient`) that interfaces with multiple configured model providers:

- **Ollama**: Sends async HTTP POST requests to a local instance running `qwen2.5-coder:7b` (default).
- **Gemini**: Sends async HTTP POST requests directly to Google's API endpoint (bypassing blocking SDK pools) running `gemini-2.5-flash` or `gemini-1.5-flash`.
- **Anthropic**: Uses the `AsyncAnthropic` SDK to communicate with Claude models (`claude-3-5-sonnet-20240620`).

Returns structured `LLMResponse` objects containing the model text response and counted input/output tokens.

---

## 7. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend UI** | HTML + CSS Variables + JS (Single File) | Premium, responsive, glassmorphic layout, marked.js parser, ZERO build tooling. |
| **API Backend** | Python / FastAPI | Async-native routes, Pydantic type safety, fast response limits. |
| **Task Queue** | Redis + Celery | Enterprise-grade Python task queue supporting async runtime and status tracking. |
| **DB & ORM** | SQLite + SQLAlchemy (aiosqlite) | Fully asynchronous SQLite driver, declarative mappings, and automatic table creation. |
| **AI Client** | Httpx + AsyncAnthropic SDK | Modular async endpoints for Ollama local instances, Google Gemini, and Anthropic API. |
| **Observability** | OpenTelemetry + Jaeger | Standardized trace propagation and UI for analyzing API and worker latencies. |

---

## 8. Project Structure

```
lesson-plan-agent/
│
├── api/
│   ├── __init__.py
│   ├── database.py          # Database session configuration
│   ├── main.py              # FastAPI app routing, table setup, metrics computation
│   ├── models.py            # SQLAlchemy models defining requests and statistics
│   ├── schemas.py           # Pydantic schemas validating models & requests
│   └── telemetry.py         # OpenTelemetry initialization and Jaeger OTLP config
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py      # Celery task orchestrating agent workflows & regex parsers
│   ├── lesson_plan_agent.py # Plan creation formatting prompts
│   ├── evaluation_agent.py  # Rubric grading templates
│   └── llm_client.py        # Generic routing wrapper for Ollama, Gemini, and Anthropic
│
├── worker/
│   ├── __init__.py
│   ├── celery_app.py        # Celery task scheduling and serializer configs
│   └── worker.py            # Main runner for background workers (sets up telemetry)
│
├── ui/
│   └── index.html           # Dark mode glassmorphic interface, charts, analytics
│
├── tests/
│   └── test_flow.py         # Integration test verifying the database, orchestrator and agents
│
├── lesson_plans.db          # Persisted SQLite database
├── .env                     # App keys, DB endpoints, and worker selections
├── requirements.txt         # Package requirements
└── docker-compose.yml       # Stack containers orchestrating Redis, Jaeger, worker, API, and UI
```

---

## 9. UI Design

Single premium HTML file containing rich CSS variables, dynamic glassmorphic panels, violet-indigo glows, hover highlights, and micro-animations.

### Components

**1. Create Request Form**
- Dynamic Selectors for Grade levels and Curriculum Boards.
- Simple textual fields for Subject, Topic, Teaching Methodology, and custom Instructions.

**2. Progress Bar Loading Screen**
- Tracks progress dynamically from Queue (15%) → Lesson Plan Generation (45%) → Rubric Review (80%) → Done (100%).

**3. Results Viewer & Tab Interface**
- Renders rich generated markdown using `marked.js` with structured styles.
- Navigation tabs allow switching between **Lesson Plan** and **Rubric Evaluation**.

**4. Observability & LLM Metrics Dashboard**
- Rendered on top of results. Shows total latency (plus plan/evaluation breakdown), tokens count (inputs vs outputs), engine model description, and an overall rating.
- Renders **Visual Rubric Score Bars** (Clarity, Alignment, Structure, Engagement, Differentiation, Assessment, Feasibility) utilizing color scales (Red < 3.0, Orange < 4.0, Green >= 4.0).

**5. System Analytics Panel**
- Stretched across the bottom. Displays cumulative statistics retrieved from `/api/metrics` including aggregate P50, P90, and P95 latency percentiles and system error rates.

**6. Recent Requests History**
- Dynamic history list. Completed requests contain a `View` button and a trace link integration (`🔍 Trace` linking to Jaeger's Query interface on port 16686).

---

## 10. Environment Variables

```ini
# .env

# Database configuration (using async SQLite)
DATABASE_URL=sqlite+aiosqlite:///./lesson_plans.db

# Redis/Celery configuration
REDIS_URL=redis://localhost:6379/0

# LLM Provider selection: 'ollama' | 'anthropic' | 'gemini'
LLM_PROVIDER=gemini

# Ollama settings (Local Development)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b

# Anthropic Claude settings
ANTHROPIC_API_KEY=your-key-here
ANTHROPIC_MODEL=claude-3-5-sonnet-20240620

# Google Gemini settings
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash

# Telemetry settings
OTEL_SERVICE_NAME=lesson-plan-architect
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

---

## 11. Sequence Diagram

```
Teacher     UI          API         Redis       Celery Worker     LLMClient         DB
  │          │           │            │               │               │              │
  │─submit──►│           │            │               │               │              │
  │          │─POST ────►│            │               │               │              │
  │          │           │─insert row───────────────────────────────────────────────►│
  │          │           │─enqueue───►│               │               │              │
  │          │◄─202 ID───│            │               │               │              │
  │          │           │            │─pick up──────►│               │              │
  │          │           │            │               │─start span    │              │
  │          │           │            │               │─status=proc.────────────────►│
  │          │─poll─────►│            │               │               │              │
  │          │◄─proc.────│            │               │               │              │
  │          │           │            │               │──gen plan────►│              │
  │          │           │            │               │◄──response────│              │
  │          │           │            │               │─status=save─────────────────►│
  │          │─poll─────►│            │               │               │              │
  │          │◄─eval.────│            │               │               │              │
  │          │           │            │               │──gen eval────►│              │
  │          │           │            │               │◄──response────│              │
  │          │           │            │               │─parse scores  │              │
  │          │           │            │               │─status=done─────────────────►│
  │          │─poll─────►│            │               │               │              │
  │          │◄─done ────│            │               │               │              │
  │          │           │            │               │─end span      │              │
  │◄─results─│           │            │               │               │              │
  │          │                                                                       │
  │──scroll  │                                                                       │
  │  down───►│─GET /metrics─────────────────────────────────────────────────────────►│
  │          │◄─p50/p95/errors───────────────────────────────────────────────────────│
  │◄─charts──│                                                                       │
```

---

## 12. Error Handling

| Scenario | Behaviour |
|---|---|
| **API Provider rate limit / 5xx** | Caught in `LLMClient`, wraps exception as `LLMClientError` and bubbles to worker task. |
| **Empty or malformed LLM response** | Status set to `failed`, records raw trace exception, and updates row `error_message`. |
| **Worker crash mid-job** | Celery tracks job status in Redis, and allows task retry parameters. |
| **Broker (Redis) down during submit** | FastAPI returns `503 Service Unavailable` with details to ensure database state integrity. |
| **Invalid request payload** | Handled via Pydantic model validation on API backend (`422 Unprocessable Entity`). |

---

## 13. Development Runbook

### Prerequisites
- Python 3.10+ installed.
- Docker Desktop running (to host Redis & Jaeger).

### 1. Set Up Environment
```bash
# Clone the repository and install dependencies
pip install -r requirements.txt

# Create .env from example template
cp .env.example .env
# Edit .env with your LLM provider selection and API keys
```

### 2. Start Background Infrastructure (Redis & Jaeger)
```bash
# Run Redis and Jaeger containers
docker run -d -p 6379:6379 --name lesson-redis redis:alpine
docker run -d -p 16686:16686 -p 4317:4317 --name lesson-jaeger jaegertracing/all-in-one:latest
```

### 3. Run the Backend API Server
```bash
# Starts FastAPI server on port 8000 with hot reloading
uvicorn api.main:app --reload --port 8000
```

### 4. Start the Background Worker (Separate Terminal)
```bash
# Starts Celery task runner. On Windows, forces solo execution pool
python worker/worker.py
```

### 5. Launch the Web Interface
```bash
# Serve frontend on port 3000
python -m http.server 3000 --directory ui/
```
Open `http://localhost:3000` in a browser. Open Jaeger Query UI at `http://localhost:16686` to explore spans.

### 6. Alternative: Run Entire Stack via Docker-Compose
```bash
docker-compose up --build
```

### 7. Run Integration Tests
```bash
python tests/test_flow.py
```
