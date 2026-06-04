import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class LessonRequest(Base):
    __tablename__ = "lesson_requests"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    grade: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    board: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    lesson_plan_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Observability: Latencies
    generation_time_seconds: Mapped[float | None] = mapped_column(nullable=True)
    evaluation_time_seconds: Mapped[float | None] = mapped_column(nullable=True)
    
    # Observability: Token Counts
    plan_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    plan_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    eval_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    eval_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    
    # Observability: Rubric Scores
    score_clarity: Mapped[int | None] = mapped_column(nullable=True)
    score_alignment: Mapped[int | None] = mapped_column(nullable=True)
    score_structure: Mapped[int | None] = mapped_column(nullable=True)
    score_engagement: Mapped[int | None] = mapped_column(nullable=True)
    score_differentiation: Mapped[int | None] = mapped_column(nullable=True)
    score_assessment: Mapped[int | None] = mapped_column(nullable=True)
    score_feasibility: Mapped[int | None] = mapped_column(nullable=True)
    score_overall: Mapped[float | None] = mapped_column(nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
