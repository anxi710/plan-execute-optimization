"""alfworld prompts for the eo framework."""


EXECUTOR_PROMPT = """Complete the household task using the observations and current Available actions supplied by the environment.

Write exactly one nonempty Action: <command> line per turn.
You may include a brief Thought: line before it. Thought is reasoning text, not an environment command."""
