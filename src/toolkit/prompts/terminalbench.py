"""terminalbench Planner and Executor prompt templates."""


TERMINALBENCH_PLANNER_TEMPLATE = """Generate a high-level global plan for the reviewed Terminal-Bench task:
<task>
{task}
</task>

Use only the supplied task inputs and local workspace.
Organize the work into abstract subgoals for inspecting inputs, producing the required output, and checking the result.
Identify prerequisites, evidence to obtain, and alternatives if an assumption fails.
Do not change the verifier or assume access to hidden tests. Leave concrete commands and local execution choices to the Executor.

Format your plan as follows:
<plan>
Step 1: ...
Step 2: ...
...
</plan>
"""

TERMINALBENCH_EXECUTOR_TEMPLATE = """You are the Executor for this Terminal-Bench task.
Return one Action line per turn. Action: <one shell command> runs a command in /app.
Use Action: finish when the complete task is ready for independent verification.
You can inspect local inputs, create task artifacts, and check your work.
Files persist across turns. Each command starts in /app."""
