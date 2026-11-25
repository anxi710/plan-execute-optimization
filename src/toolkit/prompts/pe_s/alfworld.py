"""alfworld prompts for the pe-s framework."""


PLANNER_PROMPT = """You are the high-level Planner for a household task.
Use the task requirements and public facts. Plan observable outcomes and leave environment commands to the Executor.
Give one brief assessment of what the evidence supports and any important uncertainty.
Keep hypotheses distinct from observations. The environment determines task termination and success."""

PLANNER_INITIAL_PROMPT = """Give one advisory plan covering the entire task.
Produce a numbered plan covering the remaining whole task."""

EXECUTOR_PROMPT = """Complete the household task using the observations and current Available actions supplied by the environment.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""

PLANNER_TEMPLATE = """Generate a high-level global plan for the household task:
<task>
{task}
</task>

Organize the work into abstract subgoals and their dependencies.
Identify what must be learned or established before each subgoal, and how to adjust the route if an assumption fails.
Ground the plan in the task and supplied observations. Do not assume unobserved objects or conditions.
Leave concrete environment commands and local execution choices to the Executor.

Format your plan as follows:
<plan>
Step 1: ...
Step 2: ...
...
</plan>"""

PLANNER_JSON_FORMAT = """Return exactly one JSON object matching the following field contract.
Do not wrap it in Markdown or include an Action line. assessment contains your brief assessment;
evidence_refs may only cite observation numbers present in this request. Keep hypotheses separate from facts.
{schema}"""
