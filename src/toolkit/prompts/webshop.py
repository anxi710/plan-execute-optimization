"""webshop Planner and Executor prompt templates."""


WEBSHOP_PLANNER_TEMPLATE = """Generate a high-level global plan for the shopping task:
<task>
{task}
</task>

Organize the work into abstract subgoals for finding candidates, verifying requirements, and choosing a suitable item.
Identify the evidence needed for each requirement and what to reconsider if no candidate fits.
Do not assume a particular product ID or option before inspecting the page.
Leave concrete page interactions and local execution choices to the Executor.

Format your plan as follows:
<plan>
Step 1: ...
Step 2: ...
...
</plan>
"""

WEBSHOP_EXECUTOR_TEMPLATE = """Complete the shopping task using the observations and current Available actions supplied by the environment.
Choose an interaction from the current page's list. Replace a keywords placeholder with a task-relevant query.
Verify product requirements before purchasing. An available interaction does not guarantee that the item meets the goal.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command.
"""
