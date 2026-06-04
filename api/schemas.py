import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class LessonRequestCreate(BaseModel):
    grade: str = Field(..., min_length=1, max_length=50, examples=["Grade 8"])
    subject: str = Field(..., min_length=1, max_length=100, examples=["Science"])
    board: str = Field(..., min_length=1, max_length=100, examples=["CBSE"])
    topic: str = Field(..., min_length=1, max_length=255, examples=["Photosynthesis"])
    methodology: str | None = Field(None, examples=["Inquiry-based learning"])
    instructions: str | None = Field(None, examples=["Include a hands-on activity"])

class LessonRequestResponse(BaseModel):
    id: uuid.UUID
    status: str

    model_config = ConfigDict(from_attributes=True)

class LessonRequestDetail(BaseModel):
    id: uuid.UUID
    grade: str
    subject: str
    board: str
    topic: str
    methodology: str | None
    instructions: str | None
    status: str
    lesson_plan_md: str | None
    evaluation_md: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    # LLM details
    provider: str | None = None
    model_name: str | None = None

    # Observability Metrics
    generation_time_seconds: float | None = None
    evaluation_time_seconds: float | None = None
    plan_input_tokens: int | None = None
    plan_output_tokens: int | None = None
    eval_input_tokens: int | None = None
    eval_output_tokens: int | None = None
    
    # Rubric scores
    score_clarity: int | None = None
    score_alignment: int | None = None
    score_structure: int | None = None
    score_engagement: int | None = None
    score_differentiation: int | None = None
    score_assessment: int | None = None
    score_feasibility: int | None = None
    score_overall: float | None = None
    trace_id: str | None = None

    model_config = ConfigDict(from_attributes=True)

class SystemMetricsResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate_pct: float
    
    # Latency breakdowns (overall elapsed time)
    overall_p50_seconds: float | None = None
    overall_p90_seconds: float | None = None
    overall_p95_seconds: float | None = None
    
    # Latency breakdowns (generation step)
    generation_p50_seconds: float | None = None
    generation_p90_seconds: float | None = None
    generation_p95_seconds: float | None = None
    
    # Latency breakdowns (evaluation step)
    evaluation_p50_seconds: float | None = None
    evaluation_p90_seconds: float | None = None
    evaluation_p95_seconds: float | None = None

