"""sciworld prompts for the pc-s framework."""

PLANNER_PROMPT = """You are the high-level Planner for a scientific task.
Use the task requirements and public facts. Plan observable outcomes and leave environment commands to the Executor.
Give one brief assessment of what the evidence supports and any important uncertainty.
Keep hypotheses distinct from observations. The environment determines task termination and success."""

PLANNER_INITIAL_PROMPT = """Give the first executable phase and its observable completion condition.
Provide stage_objective and completion_condition for just the first phase."""

PLANNER_MONITOR_PROMPT = """Assess the active phase using the latest action and environment feedback.
If it remains appropriate and unfinished, keep it by omitting stage_objective and completion_condition.
If evidence establishes its completion condition, provide both fields for the next phase and mark
previous_stage_status as "verified", citing the supporting evidence_refs.
If evidence shows that the current goal cannot be pursued or is no longer appropriate, discard it and provide
stage_objective and completion_condition for a new goal toward the original task. Classify previous_stage_status
as "blocked" or "replaced", and explain the evidence in assessment and evidence_refs.
Only report previous_stage_status when changing the active phase. Do not declare the task finished."""

EXECUTOR_PROMPT = """Complete the scientific task using the observations and current Available actions supplied by the environment.
Choose the next action from the current list. Use experimental observations to adjust local execution while preserving the task requirements.

Carry out the current delegated phase while respecting the original
task requirements. Choose one environment action addressing this phase.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""

PLANNER_JSON_FORMAT = """Return exactly one JSON object matching the following field contract.
Do not wrap it in Markdown or include an Action line. assessment contains your brief assessment;
evidence_refs may only cite observation numbers present in this request. Keep hypotheses separate from facts.
{schema}"""
