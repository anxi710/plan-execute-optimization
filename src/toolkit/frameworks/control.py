"""Run the six supported planning configurations over a persistent session."""

from .runtime import FRAMEWORK_MODES, FRAMEWORK_PROTOCOL, FrameworkRun


async def run_framework(*, mode, env, planner, executor, goal, workspace_id, executor_limit, save,
                        benchmark="alfworld", external_verifier=False, protocol_version=FRAMEWORK_PROTOCOL,
                        context_window=None):
    """Apply current framework control and its Toolkit-managed input window."""
    if mode not in FRAMEWORK_MODES:
        raise ValueError(f"Unknown framework mode: {mode}")
    if protocol_version != FRAMEWORK_PROTOCOL:
        raise ValueError(f"Unsupported execution protocol: {protocol_version}")
    if type(executor_limit) is not int or executor_limit < 1:
        raise ValueError("executor_limit must be an integer of at least 1")
    if getattr(env, "max_steps", executor_limit) < executor_limit:
        raise ValueError("Environment limits must permit the requested Executor budget")
    return await FrameworkRun(
        mode=mode, env=env, planner=planner, executor=executor, goal=goal, workspace_id=workspace_id,
        executor_limit=executor_limit, save=save, benchmark=benchmark, external_verifier=external_verifier,
        context_window=context_window,
    ).run()
