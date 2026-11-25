"""sciworld prompts for the eo framework."""


EXECUTOR_PROMPT = """Complete the scientific task using the observations and current Available actions supplied by the environment.
Choose the next action from the current list. Use experimental observations to adjust local execution while preserving the task requirements.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""
