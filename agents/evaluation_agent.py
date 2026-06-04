from .llm_client import get_llm_client, LLMResponse

SYSTEM_PROMPT = """You are a senior curriculum evaluator and instructional coach.
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

End with an **Overall Score** (average) and a 2–3 sentence **Summary Recommendation**."""

USER_PROMPT_TEMPLATE = """Please evaluate the following lesson plan:

{lesson_plan_md}"""

async def evaluate_lesson_plan(lesson_plan_md: str) -> LLMResponse:
    """
    Asynchronously evaluates a lesson plan using the configured LLM.
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(lesson_plan_md=lesson_plan_md)
    client = get_llm_client()
    return await client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=5000
    )
