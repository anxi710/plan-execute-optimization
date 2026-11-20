"""Prompt templates for framework control and plan guidance."""


PLAN_HINT = """This plan may be helpful for you to complete the task:"""

THOUGHT_PLAN_HINT = """This plan may be helpful to complete the task:"""

HARD_CONSTRAINTS_TEMPLATE = """

Hard constraints for the entire task:
{constraints}"""

PLANNER_TASK_REQUIREMENTS_TEMPLATE = """{prompt}

Task requirements:
{context}"""

PE_D_CONTROL_TEMPLATE = """Set decision to "guide". The Executor owns the entire task. Give advisory full-plan guidance and leave stage_objective and soft_guidance out of the JSON object."""

PC_CONTROL_TEMPLATE = """Set decision to "delegate" when work remains. In that same JSON object, the string stage_objective is required and soft_guidance is optional. The Executor receives only the current stage and chooses its own actions. Use this JSON shape for delegation, with a concrete objective and values grounded in the current task:
{"decision":"delegate","stage_objective":"<next observable subgoal>","soft_guidance":"","hypotheses":[],"remaining_work":[],"evidence_refs":[]}
If you recommend ending the entire task, set decision to "finish" and omit stage_objective and soft_guidance."""

PC_TERMINAL_CONTROL_TEMPLATE = """The environment reached a native terminal state. Set decision to "finish", cite the relevant public observations, and omit the stage fields and plan."""

PLANNER_DECISION_TEMPLATE = """Keep a complete plan for all remaining task work in <plan>...</plan>. Separate unverified hypotheses from observations. Cite observations by their supplied event_id. After the plan, output <decision> and </decision> around a single JSON object. The common JSON fields are decision, hypotheses (array of strings), remaining_work (array of strings), and evidence_refs (array of event IDs). Add the decision-specific fields listed below. A finish decision can omit <plan>.
{control}"""

PLANNER_CONTEXT_TEMPLATE = """{prompt}

{protocol}

{context}"""

DELEGATED_STAGE_TEMPLATE = """Current delegated stage. This supersedes prior stages. Choose actions autonomously within the stage objective, and keep the original task and hard constraints. Treat soft guidance as advice.
{request}"""

PLAN_GUIDANCE_TEMPLATE = """Continue to own the entire original task. The latest guidance supersedes earlier guidance.
{plan_hint}
{guidance}"""
