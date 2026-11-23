"""Prompt templates for framework control and plan guidance."""


PLAN_HINT = """This plan may be helpful for you to complete the task:"""

THOUGHT_PLAN_HINT = """This plan may be helpful to complete the task:"""

INITIAL_SUB_PLAN_GENERATION = "Initial Sub-Plan Generation"
CONTINUOUS_EXECUTION_MONITORING = "Continuous Execution Monitoring"

FRAMEWORK_PLANNER_PROMPT = """You are the high-level Planner for a {benchmark} task.
Use the task requirements and public facts. Plan observable outcomes and leave environment commands to the Executor.
Give one brief assessment of what the evidence supports and any important uncertainty.
Keep hypotheses distinct from observations. The environment determines task termination and success."""

PC_INITIAL_PROMPT = """Choose the first executable phase and its observable completion condition.
Return the initial plan before any environment action. The runner then invokes the Executor directly."""

PC_MONITOR_PROMPT = """Compare the last actual action and environment feedback with the active phase.
Keep the phase while its objective is still appropriate and unfinished. If its condition is supported by public
evidence, record it as verified and move to the next phase. If blocked or superseded, explain why.
A new fact can inform planning without completing the phase. The runner invokes the Executor once after this update.
Do not declare the task finished or request an execution tool; task termination comes from environment feedback."""

PC_FULL_PROMPT = """Initially provide a full_plan of numbered sub-plans and select current_subplan_id.
The initial plan does not require revision_reason.
On later calls, preserve the active stage id when its objective and completion condition remain the same.
To advance to another existing phase without changing the plan, provide current_subplan_id and omit full_plan.
If any part of full_plan changes, include the updated full_plan and a nonempty revision_reason string
in the same JSON object. Explain what changed and why, including wording changes or added details."""

PC_SUB_PROMPT = """Initially provide stage_objective and completion_condition for just the first phase.
Keep the stage by omitting both fields. Replace it by providing both fields."""

PE_STATIC_PLAN_PROMPT = """The Executor owns the task. Use the original task and public evidence.
Before execution, give one advisory plan covering the entire task.
The Executor carries out the task autonomously without further Planner calls."""

PE_INITIAL_PLAN_PROMPT = """The Executor owns the task. Use the original task and public evidence.
Before execution, give initial advisory guidance for the requested planning scope.
The Executor chooses its own actions and whether to request further guidance."""

PE_REPLAN_PROMPT = """The Executor owns the task and has requested planning guidance.
Use the original task, current guidance, and complete public interaction history to assess the request.
Keep the current guidance if it still answers the request; otherwise give updated advisory guidance."""

PE_SUB_PLAN_PROMPT = """Deliver only the next actionable sub-goal, with the first useful observable
checkpoint as its completion condition. For a task with several remaining phases, this checkpoint must occur
before the overall task is done. For example, if a needed object has not been located, locating it is one
sub-goal. Using or delivering it belongs to a later plan request. If just one phase remains, use that phase."""

TERMINAL_REVIEW_PROMPT = """Give a one-sentence assessment of the final observable result.
Refer to the actual action and feedback. State uncertainty if completion is not established.
Begin with Assessment: and do not choose another action."""

EXECUTOR_DELEGATION_PROMPT = """Carry out the current delegated phase while respecting the original task requirements.
Choose one environment action addressing this phase. The Planner receives the action and actual environment feedback automatically."""

EXECUTOR_PLAN_REQUEST_PROMPT = """Choose one environment action, or call request_plan to ask the Planner for guidance.
A planning call must not also contain an Action: line."""

PLANNER_JSON_FORMAT = """Return exactly one JSON object matching the following field contract.
Do not wrap it in Markdown or include an Action line. assessment contains your brief assessment;
evidence_refs may only cite observation numbers present in this request. Keep hypotheses separate from facts.
{schema}"""
