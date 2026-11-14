# Hackathon brief (condensed)

"AI on Campus" challenge, Reply Student Tech Clash 2026 (https://studentclash.reply.com/).
The full brief is in the team's claude.ai project. This copy keeps what matters for building.

## Challenge
Pick a real problem in **learning, teaching or assessment** at your university and build an AI-based
solution. Start with the problem, not the tool. Administration and logistics are out of scope.

## Levels
- **Level 1 (required):** problem, idea, use scenario, target user, success measures, and a 60-second pitch.
- **Level 2 (required):** a **working AI agent** that shows the core of the idea.
- **Level 3 (optional bonus):** a multi-agent system, a knowledge graph and/or a launch campaign.

## Level 2: the agent must
1. **Work with real material:** actual university content (slides, notes, past exercises), not just model knowledge.
2. **Do something, not just say something:** at least one action beyond replying (e.g. generate and score a quiz,
   track what a student keeps getting wrong, flag a question for the lecturer).
3. **Know its limits:** help the student think rather than think for them (guide instead of handing over answers).

Reference architecture: UI → orchestrator (agent loop with a step budget, hand over to a human when unsure)
↔ LLM, plus tools, structured memory, **guardrails in code (not only in the prompt)** and **logs of every step**.

## Level 2 deliverables (coding path)
- README: how to run it, models, libraries and frameworks, custom logic
- A working repo
- Architecture description: input, knowledge used, tools, decisions, output
- Example interactions, **including one where the agent holds its boundary**
- Optional (recommended): an interface and/or a demo video

## Scoring
| Criterion | Weight |
|---|---|
| Creativity & Innovation | 40% |
| Impact | 20% |
| Technical | 20% |
| Effective Presentation | 20% |

The judges ask: Is this genuinely new, or just faster? Does it help someone think, or does it think for them?
Who benefits, and who might be left out?

## Design principles
- Be problem-first and specific: one course, one moment, one user.
- Justify why AI is needed.
- Ground everything in real material, take at least one real action, and hand over to a human when unsure.
- Put guardrails in code and log every step.
- Address the risks: who owns the data, downtime the night before an exam, and students without reliable access.
