import asyncio
import os
import uuid
import traceback
import time
import re
from datetime import datetime, timezone
from celery import Celery
from dotenv import load_dotenv

# Import OpenTelemetry modules
from api.telemetry import get_tracer
from opentelemetry.trace import StatusCode

# Import database session, models, and agents
from api.database import AsyncSessionLocal
from api.models import LessonRequest
from .lesson_plan_agent import generate_lesson_plan
from .evaluation_agent import evaluate_lesson_plan

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Define the Celery application locally for reference
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
tracer = get_tracer("orchestrator")

def parse_evaluation_scores(eval_md: str) -> dict:
    """
    Parses the 7 individual rubric criteria scores and the average overall score
    from the evaluation markdown string using regex.
    """
    scores = {
        "score_clarity": None,
        "score_alignment": None,
        "score_structure": None,
        "score_engagement": None,
        "score_differentiation": None,
        "score_assessment": None,
        "score_feasibility": None,
        "score_overall": None
    }
    
    # Match patterns like: **Score:** 4/5, Score: 4.5/5, Score: 4/5
    matches = re.findall(r"(?:score|Score)[:\*\s]+([0-9\.]+)\s*/\s*5", eval_md)
    
    if len(matches) >= 7:
        try:
            scores["score_clarity"] = int(float(matches[0]))
            scores["score_alignment"] = int(float(matches[1]))
            scores["score_structure"] = int(float(matches[2]))
            scores["score_engagement"] = int(float(matches[3]))
            scores["score_differentiation"] = int(float(matches[4]))
            scores["score_assessment"] = int(float(matches[5]))
            scores["score_feasibility"] = int(float(matches[6]))
        except (ValueError, IndexError) as e:
            print(f"Error casting individual scores: {str(e)}")
            
    # Extract overall score: "**Overall Score:** 4.2/5" or similar
    overall_match = re.search(r"Overall Score[:\*\s]+([0-9\.]+)", eval_md, re.IGNORECASE)
    if overall_match:
        try:
            scores["score_overall"] = float(overall_match.group(1))
        except ValueError:
            pass
    elif len(matches) > 7:
        try:
            scores["score_overall"] = float(matches[-1])
        except ValueError:
            pass
            
    # Fallback overall score calculation if not explicitly parsed
    if scores["score_overall"] is None:
        valid_scores = [scores[k] for k in scores if k != "score_overall" and scores[k] is not None]
        if valid_scores:
            scores["score_overall"] = round(sum(valid_scores) / len(valid_scores), 2)
            
    return scores

@celery_app.task(name="agents.orchestrator.orchestrate_lesson_plan")
def orchestrate_lesson_plan(request_id_str: str):
    """
    Celery task that runs the orchestrator flow.
    Invokes the async orchestration function in the event loop.
    """
    request_id = uuid.UUID(request_id_str)
    return asyncio.run(async_orchestrate(request_id))

async def async_orchestrate(request_id: uuid.UUID):
    print(f"Starting orchestration for request {request_id}")
    
    # Start a tracing span for the orchestrator task lifecycle
    with tracer.start_as_current_span("orchestrate_lesson_plan") as parent_span:
        parent_span.set_attribute("request.id", str(request_id))
        
        async with AsyncSessionLocal() as session:
            # 1. Fetch request from database
            request = await session.get(LessonRequest, request_id)
            if not request:
                print(f"Request {request_id} not found in DB")
                parent_span.set_status(StatusCode.ERROR, description="Request not found in database")
                return
            
            # 2. Update request status -> "processing"
            request.status = "processing"
            await session.commit()
            print(f"Request {request_id} status updated to 'processing'")
            
            try:
                # 3. Call Lesson Plan Agent with timer and sub-span
                print(f"Generating lesson plan for request {request_id}...")
                start_plan = time.perf_counter()
                
                with tracer.start_as_current_span("lesson_plan_generation") as span:
                    span.set_attribute("lesson.grade", request.grade)
                    span.set_attribute("lesson.subject", request.subject)
                    span.set_attribute("lesson.board", request.board)
                    span.set_attribute("lesson.topic", request.topic)
                    span.set_attribute("lesson.methodology", request.methodology or "Not specified")
                    span.set_attribute("lesson.instructions", request.instructions or "None")
                    
                    plan_response = await generate_lesson_plan(
                        grade=request.grade,
                        subject=request.subject,
                        board=request.board,
                        topic=request.topic,
                        methodology=request.methodology,
                        instructions=request.instructions
                    )
                    
                    # Record LLM metrics on OTel span
                    span.set_attribute("llm.input_tokens", plan_response.input_tokens)
                    span.set_attribute("llm.output_tokens", plan_response.output_tokens)
                    span.set_attribute("llm.response.text", plan_response.text)
                
                plan_latency = time.perf_counter() - start_plan
                
                # Save intermediate results in case evaluation fails
                request.lesson_plan_md = plan_response.text
                request.plan_input_tokens = plan_response.input_tokens
                request.plan_output_tokens = plan_response.output_tokens
                request.generation_time_seconds = plan_latency
                await session.commit()
                print(f"Lesson plan generated in {plan_latency:.2f}s for request {request_id}")
                
                # 4. Call Evaluation Agent with timer and sub-span
                print(f"Generating evaluation for request {request_id}...")
                start_eval = time.perf_counter()
                
                with tracer.start_as_current_span("rubric_evaluation") as span:
                    span.set_attribute("lesson.plan_length_chars", len(plan_response.text))
                    
                    eval_response = await evaluate_lesson_plan(plan_response.text)
                    
                    # Record LLM metrics on OTel span
                    span.set_attribute("llm.input_tokens", eval_response.input_tokens)
                    span.set_attribute("llm.output_tokens", eval_response.output_tokens)
                    span.set_attribute("llm.response.text", eval_response.text)
                
                eval_latency = time.perf_counter() - start_eval
                
                # Parse scores from the evaluation markdown
                scores = parse_evaluation_scores(eval_response.text)
                print(f"Parsed scores for request {request_id}: {scores}")
                
                # Save criteria scores on parent span attributes
                parent_span.set_attribute("rubric.score_clarity", scores.get("score_clarity") or 0)
                parent_span.set_attribute("rubric.score_alignment", scores.get("score_alignment") or 0)
                parent_span.set_attribute("rubric.score_structure", scores.get("score_structure") or 0)
                parent_span.set_attribute("rubric.score_engagement", scores.get("score_engagement") or 0)
                parent_span.set_attribute("rubric.score_overall", scores.get("score_overall") or 0.0)
                
                # 5. Write all outputs, tokens, times, and scores to DB -> status = "done"
                request.evaluation_md = eval_response.text
                request.eval_input_tokens = eval_response.input_tokens
                request.eval_output_tokens = eval_response.output_tokens
                request.evaluation_time_seconds = eval_latency
                
                # Set parsed scores
                request.score_clarity = scores.get("score_clarity")
                request.score_alignment = scores.get("score_alignment")
                request.score_structure = scores.get("score_structure")
                request.score_engagement = scores.get("score_engagement")
                request.score_differentiation = scores.get("score_differentiation")
                request.score_assessment = scores.get("score_assessment")
                request.score_feasibility = scores.get("score_feasibility")
                request.score_overall = scores.get("score_overall")
                
                request.status = "done"
                request.completed_at = datetime.now(timezone.utc)
                await session.commit()
                print(f"Orchestration completed successfully in {plan_latency + eval_latency:.2f}s for request {request_id}")
                
            except Exception as e:
                # Log exception and set span state to failed
                parent_span.record_exception(e)
                parent_span.set_status(StatusCode.ERROR, description=str(e))
                
                # Handle failure: update DB status and store error details
                error_details = traceback.format_exc()
                print(f"Orchestration failed for request {request_id}: {str(e)}\n{error_details}")
                
                request.status = "failed"
                request.error_message = f"{str(e)}"
                request.completed_at = datetime.now(timezone.utc)
                await session.commit()
