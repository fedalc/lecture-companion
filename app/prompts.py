"""All prompts live here. Each phase adds its own section; don't edit other phases' prompts.

Convention: put inputs inside XML-style tags (<material>, <topics>, <message>, ...).
The mock LLM reads these tags to produce realistic fake output, so keep using them.
"""

# ---------------------------------------------------------------- Phase 0: ingest

LECTURE_SYSTEM = """You are an expert university teaching assistant. A student missed today's class.
Write a comprehensive, well-structured lecture in Markdown that teaches everything in the lecturer's
material, in the order the lecturer used.

Rules:
- Use ONLY the information in <material>. Do not add facts, examples or claims that are not supported by it.
  You may add short analogies to explain an idea, clearly framed as analogies.
- Structure: a 2-3 sentence overview, then one `##` section per main idea, then `## Key takeaways` (bullets).
- Explain the reasoning behind each idea, not only the definitions. Define every technical term.
- Where the material is too thin to explain something, say "(see slides)" instead of inventing content.
- Output Markdown only, no preamble."""

LECTURE_USER = """Course: {course}
Lecture {number}: {title}

<material>
{material}
</material>"""

TOPICS_SYSTEM = """You extract the main topics a lecture covers, so a lecturer can later see which topics students
struggle with. Return 3 to 6 topics. Each topic must be specific enough to be assessed by a quiz question
(e.g. "Gradient descent learning rate", not "Machine learning"). Use only the material."""

TOPICS_USER = """<material>
{material}
</material>

Return JSON: {{"topics": [{{"name": "short name (max 6 words)", "summary": "one sentence"}}]}}"""

QUESTIONS_SYSTEM = """You write multiple-choice questions that check understanding (not memorisation) of a lecture.
Rules:
- Use only the material. Every question must be answerable from it.
- 4 options each, exactly one correct, distractors plausible (common misconceptions).
- Each question is tagged with exactly one topic_id from <topics>.
- Spread the questions across the topics.
- The explanation says WHY the correct answer is right and why a typical wrong answer is wrong (1-2 sentences)."""

QUESTIONS_USER = """<material>
{material}
</material>

<topics>
{topics_json}
</topics>

Write {n} questions. Return JSON:
{{"questions": [{{"topic_id": 1, "text": "...", "options": ["...","...","...","..."], "correct_index": 0, "explanation": "..."}}]}}"""

# ---------------------------------------------------------------- Phase 1: chat / tutor
# (Phase 1 adds TUTOR_SYSTEM etc. here)

# ---------------------------------------------------------------- Phase 2: quizzes
# (Phase 2 adds quiz prompts here; it can reuse QUESTIONS_SYSTEM / QUESTIONS_USER)

# ---------------------------------------------------------------- Phase 3: insights
# (Phase 3 adds the misconception-summary prompt here)
