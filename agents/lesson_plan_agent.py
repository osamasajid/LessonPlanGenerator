from .llm_client import get_llm_client, LLMResponse

SYSTEM_PROMPT = """You are an expert curriculum designer and experienced teacher.
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
## Teacher Notes"""

USER_PROMPT_TEMPLATE = """Grade: {grade}
Subject: {subject}
Board: {board}
Topic: {topic}
Teaching Methodology: {methodology}
Additional Instructions: {instructions}

Generate the lesson plan now."""

async def generate_lesson_plan(
    grade: str,
    subject: str,
    board: str,
    topic: str,
    methodology: str | None = None,
    instructions: str | None = None
) -> LLMResponse:
    """
    Asynchronously generates a lesson plan using the configured LLM.
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        grade=grade,
        subject=subject,
        board=board,
        topic=topic,
        methodology=methodology or "Not specified",
        instructions=instructions or "None"
    )
    
    client = get_llm_client()
    return await client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=4000
    )
