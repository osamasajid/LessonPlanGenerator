import os
import sys
import uuid
import math
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add project root to sys.path to ensure correct imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import telemetry and OpenTelemetry modules
from api.telemetry import setup_telemetry, instrument_app
from opentelemetry import trace

# Initialize telemetry first (creates tracer provider)
setup_telemetry()

from api.database import get_db, engine, Base
from api.models import LessonRequest
from api.schemas import LessonRequestCreate, LessonRequestResponse, LessonRequestDetail, SystemMetricsResponse
from agents.orchestrator import orchestrate_lesson_plan

app = FastAPI(
    title="AI Lesson Plan Generator API",
    description="Asynchronous backend API for managing AI-generated lesson plans and evaluations.",
    version="1.0"
)

# Instrument the FastAPI app immediately
instrument_app(app)

# Enable CORS for local UI and debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    """
    Ensures that SQLite database tables are created automatically on API startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.post(
    "/api/requests",
    response_model=LessonRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a new lesson plan request"
)
async def create_request(payload: LessonRequestCreate, db: AsyncSession = Depends(get_db)):
    # Extract trace ID from OpenTelemetry active span context
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    trace_id_str = None
    if span_context and span_context.is_valid:
        trace_id_str = format(span_context.trace_id, "032x")
        print(f"Captured active request OTel trace ID: {trace_id_str}")

    # Create request record in database
    new_request = LessonRequest(
        grade=payload.grade,
        subject=payload.subject,
        board=payload.board,
        topic=payload.topic,
        methodology=payload.methodology,
        instructions=payload.instructions,
        status="pending",
        trace_id=trace_id_str
    )
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)
    
    # Enqueue Celery task
    try:
        orchestrate_lesson_plan.delay(str(new_request.id))
    except Exception as e:
        # Fallback error handling if Redis is down
        await db.delete(new_request)
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail=f"Task queue broker is unavailable. Ensure Redis is running. Details: {str(e)}"
        )
    
    return new_request

def inject_llm_metadata(db_request):
    if not db_request:
        return
    provider = os.getenv("LLM_PROVIDER", "ollama")
    db_request.provider = provider
    if provider == "ollama":
        db_request.model_name = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    elif provider == "anthropic":
        db_request.model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
    else:
        db_request.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

@app.get(
    "/api/requests/{request_id}",
    response_model=LessonRequestDetail,
    summary="Get details of a specific lesson request"
)
async def get_request(request_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    db_request = await db.get(LessonRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Lesson request not found")
    inject_llm_metadata(db_request)
    return db_request

@app.get(
    "/api/requests",
    response_model=list[LessonRequestDetail],
    summary="List all lesson requests"
)
async def list_requests(limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    query = select(LessonRequest).order_by(LessonRequest.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    requests = result.scalars().all()
    for req in requests:
        inject_llm_metadata(req)
    return requests

@app.get(
    "/api/metrics",
    response_model=SystemMetricsResponse,
    summary="Get system observability latency percentiles and error metrics"
)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    # Query all requests in database
    query = select(LessonRequest)
    result = await db.execute(query)
    requests = result.scalars().all()
    
    total = len(requests)
    successful = sum(1 for r in requests if r.status == "done")
    failed = sum(1 for r in requests if r.status == "failed")
    
    error_rate = (failed / total * 100.0) if total > 0 else 0.0
    
    # Extract latencies for successful jobs
    overall_times = []
    gen_times = []
    eval_times = []
    
    for r in requests:
        if r.status == "done" and r.completed_at and r.created_at:
            overall_times.append((r.completed_at - r.created_at).total_seconds())
            if r.generation_time_seconds is not None:
                gen_times.append(r.generation_time_seconds)
            if r.evaluation_time_seconds is not None:
                eval_times.append(r.evaluation_time_seconds)
                
    # Helper to calculate percentile using linear interpolation
    def get_p(lst, p):
        if not lst:
            return 0.0
        sorted_lst = sorted(lst)
        k = (len(sorted_lst) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_lst[int(k)], 2)
        d0 = sorted_lst[int(f)] * (c - k)
        d1 = sorted_lst[int(c)] * (k - f)
        return round(d0 + d1, 2)
        
    return SystemMetricsResponse(
        total_requests=total,
        successful_requests=successful,
        failed_requests=failed,
        error_rate_pct=round(error_rate, 2),
        
        overall_p50_seconds=get_p(overall_times, 50),
        overall_p90_seconds=get_p(overall_times, 90),
        overall_p95_seconds=get_p(overall_times, 95),
        
        generation_p50_seconds=get_p(gen_times, 50),
        generation_p90_seconds=get_p(gen_times, 90),
        generation_p95_seconds=get_p(gen_times, 95),
        
        evaluation_p50_seconds=get_p(eval_times, 50),
        evaluation_p90_seconds=get_p(eval_times, 90),
        evaluation_p95_seconds=get_p(eval_times, 95)
    )
