import asyncio
import importlib.util
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(importlib.util.find_spec("ijson"), "requires the WebShop recipe packages")
class WebShopReplayTest(unittest.TestCase):
    def test_cli_recovers_only_the_matching_native_prefix_and_preserves_raw_records(self):
        from run import model_call, save_trial
        from toolkit.frameworks import run_framework
        from toolkit.prompts import render_action_feedback
        from toolkit.tasks.webshop import WebShopTask
        from toolkit.utils.files import read_json, write_json
        import webshop_benchmark as shop

        class NativeFixture:
            def __init__(self, observation, changed=False, changed_actions=False, changed_initial=False):
                self.instruction = observation
                self.changed = changed
                self.changed_actions = changed_actions
                self.changed_initial = changed_initial
                self.stepped = False

            def reset(self, session):
                return "Search", None

            def get_instruction_text(self):
                return self.instruction

            def get_available_actions(self):
                changed = self.changed_actions if self.stepped else self.changed_initial
                return {"has_search_bar": True, "clickables": ["new choice"] if changed else []}

            def step(self, action):
                self.assert_action(action)
                self.stepped = True
                return ("Changed " if self.changed else "") + "皂" * 12_000, 0.0, False, {}

            @staticmethod
            def assert_action(action):
                if action != "search[soap]":
                    raise AssertionError(f"Unexpected native action {action}")

        tasks = {str(i): WebShopTask(str(i), i, f"Instruction: Find soap {i}") for i in range(5)}
        catalog = {"human_goals": len(tasks)}
        verification = {"indexed_products_verified": 10}
        server = SimpleNamespace(goals=[{} for _ in tasks], search_engine=SimpleNamespace(num_docs=10))
        cap = 32_000

        @contextmanager
        def fixture_environment(_server, task, limit, **changes):
            yield shop.WebShopBenchmarkEnv(
                task, NativeFixture(task.observation, **changes),
                **{**shop.webshop_settings(), "max_steps": limit},
            )

        @contextmanager
        def fixture_server(_):
            yield server

        async def original_trial(path, trial_id, task):
            replies = ["Thought: inspect.\nAction: click[features]", "Action: search[soap]"]
            responses = [
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply), finish_reason="stop")],
                                usage=None, model="fixture", id=f"reply-{index}")
                for index, reply in enumerate(replies)
            ]
            client = SimpleNamespace(complete=AsyncMock(side_effect=responses))
            workspace = f"fixture-run/{trial_id}/attempt-1"
            with fixture_environment(server, task, 15) as env:
                record = await run_framework(
                    mode="eo", env=env, planner=None, executor=model_call(client, "executor", 15, max_input_bytes=cap),
                    goal=task.observation, constraints=shop.CONSTRAINTS, workspace_id=workspace,
                    executor_limit=15, planner_limit=0, return_every=2, save=lambda _: None, benchmark="webshop",
                )
            self.assertEqual(client.complete.await_count, 2)
            self.assertEqual(record["events"][-3]["error"], "PromptBudgetExceeded")
            save_trial(path, {"run_id": "fixture-run", "trial_id": trial_id, "model": "fixture",
                              "task_id": task.task_id, "arm": "eo", "attempt": 1}, {**record, "status": "unscored"})
            if task.task_id == "2":
                legacy = read_json(path)
                for event in legacy["events"]:
                    if event["type"] == "initial_observation":
                        event["observation"] = render_action_feedback(event["observation"], ["search[keywords]"])
                    elif event["type"] == "tool_event":
                        event["observation"] = render_action_feedback(event["observation"], event.pop("available_actions"))
                write_json(path, legacy)

        with TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            data_dir = Path(directory) / "data"
            write_json(data_dir / "verified.json", verification)
            manifest = {
                "schema_version": shop.SCHEMA_VERSION, "purpose": shop.PURPOSE, "run_id": "fixture-run",
                "status": "running", "budget": {"max_input_bytes_per_request": cap}, "trials": {}, "records": {},
                "benchmark": {"name": "WebShop", "split": "test", "selection": "full_split",
                              "canonical_task_count": shop.TEST_GOALS, "data_version": shop.UPSTREAM_REVISION,
                              "data_dir": str(data_dir), "catalog": catalog, "catalog_verification": verification,
                              "tasks": [{"task_id": task.task_id, "goal": task.observation, "session": task.session,
                                         "executor_limit": 15}
                                        for task in tasks.values()]},
            }
            for task in tasks.values():
                trial_id = f"m1-t{task.task_id}-eo"
                source = f"trials/{trial_id}.json"
                manifest["trials"][trial_id] = {"trial_id": trial_id, "file": source, "status": "queued",
                                                "model": "fixture", "task_id": task.task_id, "mode": "eo",
                                                "executor_limit": 15}
                manifest["records"][trial_id] = source
                asyncio.run(original_trial(run_dir / source, trial_id, task))
            write_json(run_dir / "manifest.json", manifest)
            originals = {path: path.read_bytes() for path in run_dir.rglob("*.json")}

            record = read_json(run_dir / "trials/m1-t0-eo.json")
            identity = {key: record[key] for key in (
                "run_id", "trial_id", "attempt", "workspace_id", "model", "task_id", "mode",
            )}
            self.assertIsNotNone(shop.context_limit_evidence(record, identity, cap, 15))
            for candidates in (["tampered"], [1]):
                tampered = deepcopy(record)
                action = next(event for event in tampered["events"] if event["type"] == "tool_event")
                action["available_actions"] = candidates
                self.assertIsNone(shop.context_limit_evidence(tampered, identity, cap, 15))

            def replay_environment(server, task, limit):
                return fixture_environment(server, task, limit, changed=task.task_id == "1",
                                           changed_actions=task.task_id == "3", changed_initial=task.task_id == "4")

            upstream = SimpleNamespace(engine=SimpleNamespace(__file__="/mock/web_agent_site/engine/engine.py"))
            argv = ["webshop_benchmark.py", "--run-dir", str(run_dir), "--data-dir", str(data_dir), "--replay-native"]
            with (patch.dict(sys.modules, {"web_agent_site": SimpleNamespace(engine=upstream),
                                          "web_agent_site.engine": upstream}),
                  patch.object(sys, "argv", argv),
                  patch.object(shop.subprocess, "check_output", return_value=shop.UPSTREAM_REVISION),
                  patch.object(shop, "load_test_split", return_value=(catalog, tasks)),
                  patch.object(shop, "shared_server", new=fixture_server),
                  patch.object(shop, "isolated_environment", side_effect=replay_environment),
                  patch.object(shop.os, "getenv", side_effect=AssertionError("Replay must not read a model credential"))):
                shop.main()

            for task_id in ("0", "2"):
                score = read_json(run_dir / "native-replay" / f"m1-t{task_id}-eo.json")
                record = read_json(run_dir / score["source"])
                self.assertEqual(score["outcome"], {"reason": "prompt_budget", "reward": 0.0, "success": False})
                self.assertEqual(score["tool_events_replayed"], 2)
                blocked = record["events"][score["blocked_call_event_id"] - 1]
                encoded = json.dumps(blocked["messages"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.assertGreater(len(encoded), cap)
                self.assertEqual((score["input_bytes"], score["max_input_bytes"]), (len(encoded), cap))
                self.assertEqual(score["method"], shop.REPLAY_METHOD)
            self.assertEqual(sorted(path.name for path in (run_dir / "native-replay").iterdir()),
                             ["m1-t0-eo.json", "m1-t2-eo.json"])
            self.assertEqual({path: path.read_bytes() for path in originals}, originals)
