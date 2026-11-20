"""sciworld Planner and Executor prompt templates."""


SCIWORLD_PLANNER_TEMPLATE = """Generate a high-level global plan for the scientific task:
<task>
{task}
</task>

Organize the experiment into abstract subgoals, required conditions, and evidence to obtain.
Explain the dependencies between preparation, investigation, and checking the result.
Ground the plan in the task and supplied observations. Keep unverified assumptions separate from known facts.
Leave concrete environment commands and local execution choices to the Executor.

Format your plan as follows:
<plan>
Step 1: ...
Step 2: ...
...
</plan>
"""

SCIWORLD_EXECUTOR_TEMPLATE = """Complete the scientific task using the observations and current Available actions supplied by the environment.
Choose the next action from the current list. Use experimental observations to adjust local execution while preserving the task goal and constraints.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command.
"""
