import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from toolkit.envs.alfworld_env import alfworld_settings
from toolkit.rollout.state import State
from toolkit.tasks import alfworld
from toolkit.utils.files import read_jsonl, read_yaml_mapping, write_jsonl
from toolkit.utils.runfiles import save_settings


RECIPE_DIR = Path(__file__).resolve().parents[1]


def load_script(name):
    path = RECIPE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"strategy_sampling_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StrategySamplingTest(unittest.IsolatedAsyncioTestCase):
    def test_reasoning_rename_preserves_equivalent_saved_execution_settings(self):
        experiment = load_script("execute")
        settings = {"environment": {"instruction_path": None},
                    "executor": {"model_name": "fake-model", "thinking": "disabled"}}
        saved = deepcopy(settings)
        saved["executor"]["deepseek_thinking"] = saved["executor"].pop("thinking")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_settings.meta"
            save_settings(path, saved)
            original = path.read_bytes()
            save_settings(path, settings, equivalent=experiment.equivalent_instruction_path)
            self.assertEqual(path.read_bytes(), original)
            for override in ({"thinking": "enabled"}, {"reasoning_effort": "none"}):
                with self.subTest(override=override):
                    changed = deepcopy(settings)
                    changed["executor"].update(override)
                    with self.assertRaisesRegex(ValueError, "Resume settings differ"):
                        save_settings(path, changed, equivalent=experiment.equivalent_instruction_path)

    def test_instruction_relocation_requires_matching_text_and_other_settings(self):
        experiment = load_script("execute")
        settings = {"environment": {"instruction_path": None, "max_steps": 30},
                    "executor_instruction": "Exact instruction.\n", "executor": {"model_name": "fake-model"}}
        saved = deepcopy(settings)
        saved["environment"]["instruction_path"] = "/removed/instructions/alfworld_inst.txt"
        self.assertTrue(experiment.equivalent_instruction_path(saved, settings))
        self.assertEqual(saved, settings)

        for change in ("text", "max_steps", "missing_text", "missing_path"):
            with self.subTest(change=change):
                saved = deepcopy(settings)
                saved["environment"]["instruction_path"] = "/removed/instructions/alfworld_inst.txt"
                if change == "text":
                    saved["executor_instruction"] = "Different instruction.\n"
                elif change == "max_steps":
                    saved["environment"]["max_steps"] = 29
                elif change == "missing_text":
                    del saved["executor_instruction"]
                else:
                    del saved["environment"]["instruction_path"]
                self.assertFalse(experiment.equivalent_instruction_path(saved, settings))

    def test_only_condition_b_receives_its_earlier_routes(self):
        planner = load_script("sample")

        replies = []
        for index in range(4):
            content = f"<Route>route-{index} details</Route><Plan>plan {index}</Plan>"
            choice = SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="length" if index == 3 else "stop",
            )
            replies.append(SimpleNamespace(id=str(index), model="fake-model", choices=[choice], usage=None))

        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}),
              patch.object(planner, "AsyncChatClient") as client_factory):
            client = client_factory.return_value.__aenter__.return_value
            client.complete = AsyncMock(side_effect=replies)
            run_dir = Path(directory)
            config = read_yaml_mapping(RECIPE_DIR / "config.yaml")
            config["run_dir"] = directory
            config["planner"].update(
                concurrency=2, samples_per_condition=2, request_timeout_seconds=20, history_words=1,
                token_parameter="max_completion_tokens",
            )
            config["toolkit"]["environments"]["alfworld"]["max_steps"] = 17
            default_steps = alfworld_settings()["max_steps"]
            config_path = run_dir / "config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            write_jsonl(run_dir / "tasks.jsonl", [{"id": 7, "task": "Find the lamp."}])
            planner.main(["--config", str(config_path), "--model", "fake-model"])
            self.assertEqual(alfworld_settings()["max_steps"], default_steps)
            rows = read_jsonl(run_dir / "plans/7.jsonl")
            settings = json.loads((run_dir / "planner_settings.json").read_text())
            analyzer = load_script("analyze")
            analyzer.main(["blind", "--config", str(config_path)])
            self.assertEqual(len(read_jsonl(run_dir / "blind_index.jsonl")), 4)
            config["analysis"]["blind_seed"] += 1
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Blind index differs|Resume settings differ"):
                analyzer.main(["blind", "--config", str(config_path)])

        client_factory.assert_called_once_with(
            base_url="https://api.deepseek.com", api_key="fake", timeout=20, max_retries=0, max_concurrency=2,
        )
        self.assertEqual(client.complete.await_count, 4)
        self.assertEqual(client.complete.await_args.kwargs["max_completion_tokens"], 320)
        self.assertEqual(settings["model"], "fake-model")
        self.assertEqual(settings["samples_per_condition"], 2)
        self.assertNotIn("api_key", settings)
        self.assertNotIn("reasoning_effort", settings)
        self.assertEqual(client.complete.await_args.kwargs["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertNotIn("reasoning_effort", client.complete.await_args.kwargs)
        samples = {(row["condition"], row["sample"]): row for row in rows}
        base_prompt = samples["A", 0]["prompt"]
        self.assertEqual(base_prompt, samples["A", 1]["prompt"])
        self.assertEqual(base_prompt, samples["B", 0]["prompt"])
        history_prompt = samples["B", 1]["prompt"]
        self.assertTrue(history_prompt.startswith(base_prompt))
        self.assertIn("17 turns", base_prompt)
        self.assertIn(f"- {samples['B', 0]['route'].split()[0]}\n", history_prompt)
        self.assertNotIn(samples["B", 0]["route"], history_prompt)
        self.assertNotIn(samples["A", 0]["route"].split()[0], history_prompt)
        self.assertEqual(rows[-1]["response"], replies[-1].choices[0].message.content)
        self.assertEqual((rows[-1]["route"], rows[-1]["plan"]), ("", ""))

    def test_planner_connection_config_overrides_environment_without_saving_key(self):
        planner = load_script("sample")
        reply = SimpleNamespace(
            id="id", model="fake-model", usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="<route>Search</route><plan>Find it</plan>"),
                                     finish_reason="stop")],
        )
        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(os.environ, {"OPENAI_API_KEY": "environment-key"}),
              patch.object(planner, "AsyncChatClient") as client_factory):
            run = Path(directory)
            config = read_yaml_mapping(RECIPE_DIR / "config.yaml")
            config["run_dir"] = directory
            config["planner"].update(api_base="http://model.test/v1", api_key="configured-key",
                                      samples_per_condition=1, thinking=None, reasoning_effort="none")
            config_path = run / "config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            write_jsonl(run / "tasks.jsonl", [{"id": 7, "task": "Find the lamp."}])
            client_factory.return_value.__aenter__.return_value.complete = AsyncMock(return_value=reply)
            planner.main(["--config", str(config_path)])
            self.assertEqual(client_factory.call_args.kwargs["base_url"], "http://model.test/v1")
            self.assertEqual(client_factory.call_args.kwargs["api_key"], "configured-key")
            settings = (run / "planner_settings.json").read_text()
            self.assertNotIn("api_key", json.loads(settings))
            self.assertNotIn("configured-key", settings)
            request = client_factory.return_value.__aenter__.return_value.complete.await_args.kwargs
            self.assertEqual(request["reasoning_effort"], "none")
            self.assertNotIn("extra_body", request)
            planner.main(["--config", str(config_path)])

    async def test_same_task_runs_distinct_plans_and_records_interruption(self):
        experiment = load_script("execute")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            task = {"id": 7, "task": "same initial observation"}
            row = {**task, "gamefile": "room.tw-pddl"}
            plans = {
                "table": "Search the table",
                "timeout": "Search the stairs",
                "cabinet": "Search the cabinet",
            }
            write_jsonl(output / "alfworld_dev_tasks.jsonl", [task])
            write_jsonl(output / "tasks.jsonl", [task])
            write_jsonl(output / "gamefiles.jsonl", [row])
            write_jsonl(output / "execution_queue.jsonl", [
                {"task_id": task["id"], "task": task["task"], "plan_id": plan_id, "plan": f"<plan>{plan}</plan>"}
                for plan_id, plan in plans.items()
            ])
            jobs = [experiment.rollout_job(plan_id, queued, 0, output / f"{plan_id}.json", seed=29)
                    for plan_id, queued in experiment.load_queue(output, output, "dev").items()]
            resets = []
            checkpoints = []
            executed_actions = []

            def step(actions):
                executed_actions.extend(actions)
                return ["Finished."], [1], [True], {"won": [True], "admissible_commands": [[]]}

            def load_task(task_row):
                resets.append(task_row["gamefile"])
                return SimpleNamespace(
                    observation=task_row["task"], env=SimpleNamespace(step=step), admissible_commands=list(plans),
                )

            @contextmanager
            def open_slot():
                yield SimpleNamespace(load_task=load_task)

            async def complete(**options):
                prompt = options["messages"][0]["content"]
                self.assertEqual(options["seed"], 29)
                plan_id = next(key for key, plan in plans.items() if prompt.endswith(plan))
                checkpoint = json.loads((output / f"{plan_id}.json").read_text())[-1]
                checkpoints.append((plan_id, checkpoint["incomplete"], row["task"] in prompt))
                if plan_id == "timeout":
                    raise RuntimeError("provider details")
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=f"Action: {plan_id}"))],
                    model="fake-model", usage=SimpleNamespace(total_tokens=4),
                )

            client = SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=complete)), close=AsyncMock(),
            )
            with (patch.object(alfworld, "AlfWorldRolloutPool", return_value=SimpleNamespace(open_slot=open_slot)),
                  patch("toolkit.models.openai.openai.OpenAI"),
                  patch("toolkit.models.openai.openai.AsyncOpenAI", return_value=client)):
                result = await experiment.execute(
                    jobs, output, alfworld_settings(),
                    {"model_name": "fake", "request_max_retries": 0},
                    split="dev", plan_placement="query", concurrency=1,
                )

            self.assertEqual(result, (2, 1))
            self.assertEqual(resets, [row["gamefile"]] * 3)
            self.assertEqual(checkpoints, [(plan_id, True, True) for plan_id in plans])
            self.assertEqual(executed_actions, ["table", "cabinet"])
            client.close.assert_awaited_once()
            for job in jobs:
                plan_id = job.metadata["plan_id"]
                data = json.loads(job.path.read_text())
                final = data[-1]
                state = State.load_json(data)
                self.assertEqual(final["plan_id"], plan_id)
                self.assertEqual(final["sample_id"], job.metadata["sample_id"])
                self.assertEqual(final["executor_seed"], 29)
                self.assertEqual(final["task_id"], str(row["id"]))
                self.assertEqual(final["gamefile"], row["gamefile"])
                self.assertEqual(final["executor_requests"], 1)
                if plan_id == "timeout":
                    self.assertTrue(state.incomplete)
                    self.assertFalse(state.finished)
                    self.assertEqual(final["terminate_reason"], "executor_request_error")
                    self.assertNotIn("provider details", final["error"])
                    self.assertEqual(final["executor_responses"], 0)
                    self.assertEqual(final["executor_usage"], {})
                else:
                    self.assertTrue(state.success)
                    self.assertFalse(state.incomplete)
                    self.assertEqual(state.action_trace, [{
                        "action": plan_id, "observation": "Observation: Finished.", "valid": True,
                    }])
                    self.assertEqual(final["executor_responses"], 1)
                    self.assertEqual(final["executor_usage"], {"total_tokens": 4})

    def test_execution_and_report_use_the_configured_sample_count(self):
        experiment = load_script("execute")
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            recipe = read_yaml_mapping(RECIPE_DIR / "config.yaml")
            recipe.update(run_dir=directory, data_dir=directory, split="test")
            recipe["rollout"].update(samples_per_plan=2, concurrency=3, plan_placement="observation")
            recipe["toolkit"]["executor"].update(seed=71, max_completion_tokens=80, api_base="http://model.test/v1")
            config_path = run / "config.yaml"
            config_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
            task = {"id": 7, "task": "Find the lamp."}
            row = {**task, "gamefile": "room.tw-pddl"}
            write_jsonl(run / "alfworld_test_tasks.jsonl", [task])
            write_jsonl(run / "tasks.jsonl", [task])
            write_jsonl(run / "gamefiles.jsonl", [row])
            write_jsonl(run / "execution_queue.jsonl", [
                {"task_id": 7, "task": task["task"], "plan_id": "lamp", "plan": "Look for it", "route": "search"},
            ])
            with (patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}),
                  patch.object(experiment, "execute", new_callable=AsyncMock, return_value=(2, 0)) as execute):
                self.assertEqual(experiment.main(["--config", str(config_path)]), 0)
                self.assertEqual(execute.await_args.args[3]["api_key"], "fake")
                recipe["toolkit"]["executor"]["api_key"] = "configured-key"
                config_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
                self.assertEqual(experiment.main(["--config", str(config_path)]), 0)
            jobs, _, _, agent = execute.await_args.args
            self.assertEqual([job.seed for job in jobs], [71, 71])
            self.assertEqual(len(jobs), 2)
            self.assertEqual(agent["max_completion_tokens"], 80)
            self.assertEqual(agent["api_base"], "http://model.test/v1")
            self.assertEqual(agent["api_key"], "configured-key")
            self.assertEqual(execute.await_args.kwargs, {
                "split": "test", "plan_placement": "observation", "concurrency": 3,
            })
            settings = json.loads((run / "executions/run_settings.meta").read_text())
            self.assertNotIn("api_key", settings["executor"])
            self.assertNotIn("configured-key", json.dumps(settings))
            with patch("builtins.print") as output:
                load_script("analyze").main(["report", "--config", str(config_path)])
            output.assert_called_once_with("0/2 rollouts complete")
