"""Run one trajectory with the supplied task, environment, and agent."""

import asyncio

from .state import State


class RolloutRunner:
    """Run one trajectory at a time on a worker's task loader and agent."""

    def __init__(self, load_task, agent, environment_factory, *, plan_placement):
        self._load_task = load_task
        self._agent = agent
        self._environment_factory = environment_factory
        self._plan_placement = plan_placement

    async def run(self, row, plan, save):
        state = State()
        try:
            task = self._load_task(row)
            task.plan = plan
            environment = self._environment_factory(task, plan_placement=self._plan_placement)
            _, state = environment.reset()
            save(state, provisional=True)
            while not state.finished:
                try:
                    response = await environment.plan_injection.async_call_agent(self._agent, state.history)
                except (Exception, KeyboardInterrupt) as error:
                    state.interrupt("request_error", getattr(error, "error_type", type(error).__name__))
                    break
                _, state = environment.step(response)
                save(state, provisional=True)
        except asyncio.CancelledError:
            state.interrupt("cancelled", "CancelledError")
            save(state)
            raise
        except Exception as error:
            state.interrupt("environment_error", type(error).__name__)
        save(state)
        return state
