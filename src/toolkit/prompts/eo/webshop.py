"""webshop prompts for the eo framework."""


EXECUTOR_PROMPT = """Complete the shopping task using the observations and current Available actions supplied by the environment.
Choose an interaction from the current page's list. Replace a keywords placeholder with a task-relevant query.
Verify product requirements before purchasing. An available interaction does not guarantee that the item meets the goal.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""
