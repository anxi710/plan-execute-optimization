"""alfworld Planner and Executor prompt templates."""


ALFWORLD_PLANNER_TEMPLATE = """Generate a high-level global plan for the household task:
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

ALFWORLD_EXECUTOR_TEMPLATE = """Complete the household task using the observations and current Available actions supplied by the environment.
Choose the next action from the current list. Use new feedback to adjust local execution while preserving the task goal and constraints.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""
