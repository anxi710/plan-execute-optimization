"""Run one trajectory with the supplied task, environment, and agent."""

import asyncio

from ..prompts import PlanInjection
from .session import RolloutSession
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
        session = None
        try:
            task = self._load_task(row)
            environment = self._environment_factory(task)
            injection = PlanInjection(self._plan_placement, plan)

            async def complete(messages):
                prefix = injection.thought_prefix
                text = (await self._agent.async_call(messages) if prefix is None else
                        await self._agent.async_continue_assistant(messages, prefix))
                return {"text": text}

            session = RolloutSession(environment, {"executor": complete}, plan_injection=injection)
            _, state = session.reset()
            save(state, provisional=True)

            def checkpoint(_event):
                save(session.state, provisional=True)

            await session.run(after_step=checkpoint)
            state = session.state
        except asyncio.CancelledError:
            state = session.state if session is not None else state
            state.interrupt("cancelled", "CancelledError")
            save(state)
            raise
        except (Exception, KeyboardInterrupt) as error:
            state = session.state if session is not None else state
            request_error = session is not None and session.phase == "request"
            if isinstance(error, KeyboardInterrupt) and not request_error:
                raise
            code = "request_error" if request_error else "environment_error"
            error_type = getattr(error, "error_type", type(error).__name__) if request_error else type(error).__name__
            state.interrupt(code, error_type)
        save(state)
        return state
