import gzip
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import asynccontextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import benchmark
from report import accumulate_attempt_cost, benchmark_token_count, matched_trials, render_benchmark
from toolkit.utils.files import read_json, write_json


class APIConnectionError(Exception):
    pass


@asynccontextmanager
async def offline_client(**kwargs):
    yield object()


class BenchmarkStorageTest(unittest.IsolatedAsyncioTestCase):
    async def test_shared_rate_file_paces_distinct_clients_and_ignores_old_boot(self):
        transport = SimpleNamespace(complete=AsyncMock(return_value="reply"))
        with tempfile.TemporaryDirectory() as directory:
            rate_file = Path(directory) / "rate"
            rate_file.write_text("old-boot 9000\n", encoding="ascii")
            with (patch.dict(os.environ, PLANNER_BENCHMARK_RATE_FILE=str(rate_file)),
                  patch.object(benchmark, "monotonic", side_effect=[100.0, 100.0, 100.0, 100.6]),
                  patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock) as sleep):
                first = benchmark.PacedClient(transport)
                second = benchmark.PacedClient(transport)
                self.assertEqual(await first.complete(model="first"), "reply")
                self.assertEqual(await second.complete(model="second"), "reply")
            sleep.assert_awaited_once()
            self.assertAlmostEqual(sleep.await_args.args[0], 0.6)
            self.assertEqual(transport.complete.await_count, 2)
            boot, timestamp = rate_file.read_text(encoding="ascii").split()
            self.assertEqual(boot, first.boot_id)
            self.assertAlmostEqual(float(timestamp), 101.2)

    async def test_unconfigured_rate_remains_local_to_each_client(self):
        transport = SimpleNamespace(complete=AsyncMock())
        with (patch.dict(os.environ, PLANNER_BENCHMARK_RATE_FILE=""),
              patch.object(benchmark, "REQUESTS_PER_MINUTE", 1),
              patch.object(benchmark.asyncio, "sleep", new_callable=AsyncMock) as sleep):
            first = benchmark.PacedClient(transport)
            second = benchmark.PacedClient(transport)
            await first.complete()
            await second.complete()
            sleep.assert_not_awaited()
            await first.complete()
        sleep.assert_awaited_once()
        self.assertGreater(sleep.await_args.args[0], 0)

    async def test_partial_alfworld_catalog_cannot_claim_full_split(self):
        partial_split = [{"id": "1", "task": "A test goal", "gamefile": "only-one"}]
        with patch.object(benchmark, "load_alfworld_rows", return_value=partial_split):
            with self.assertRaisesRegex(ValueError, "all 134 official test games"):
                await benchmark.run_benchmark(Path("unused"), Path("unused"), Path("unused"), "unused")

    def test_json_codec_preserves_plain_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            plain = Path(directory) / "trial.json"
            compressed = Path(directory) / "trial.json.gz"
            value = {"task": "测量", "events": [{"text": "重复的观察"}] * 100}
            for path in (plain, compressed):
                write_json(path, value)
                self.assertEqual(read_json(path), value)
            self.assertEqual(plain.read_text(encoding="utf-8"), json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            self.assertEqual(gzip.decompress(compressed.read_bytes()), plain.read_bytes())

    def test_startup_error_before_any_events_has_zero_request_cost(self):
        cost = Counter()
        accumulate_attempt_cost(cost, {"status": "error", "error": "OSError", "events": []})
        self.assertEqual(benchmark_token_count(cost, "total_tokens"), "0")
        accumulate_attempt_cost(cost, {})
        self.assertEqual(benchmark_token_count(cost, "total_tokens"), "未知")

    def test_retry_budget_ignores_archived_startup_error_before_any_events(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            trial = {"status": "unscored", "error": "APIConnectionError", "file": "trial.json",
                     "archived_attempts": ["startup.json"]}
            write_json(run / "startup.json", {"status": "error", "error": "OSError", "events": []})
            write_json(run / "trial.json", {"status": "unscored", "events": [{"type": "model_call"}]})
            self.assertTrue(benchmark.can_retry_trial(run, trial))
            trial["archived_attempts"].append("model.json")
            write_json(run / "model.json", {"status": "unscored", "events": [{"type": "model_call"}]})
            self.assertFalse(benchmark.can_retry_trial(run, trial))

    async def test_model_selection_preserves_trial_identity_and_checks_resume(self):
        dataset = {"tasks": [{"task_id": "sample", "executor_limit": 4}], "compress_traces": True}
        rows = {"sample": dataset["tasks"][0]}
        model = benchmark.MODELS[0]
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              patch.object(benchmark, "run_pending", new_callable=AsyncMock) as run_pending):
            run_dir = Path(directory)
            full = benchmark.scheduled_manifest(dataset, "run-id")
            selected = benchmark.scheduled_manifest(dataset, "run-id", model_order=(model,))
            self.assertEqual(full["model_order"], list(benchmark.MODELS))
            self.assertEqual(selected["model_order"], [model])
            self.assertEqual(selected["trials"], {key: trial for key, trial in full["trials"].items()
                                                   if trial["model"] == model})
            write_json(run_dir / "manifest.json", selected)
            await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=None, resume=True,
                                       model_order=(model,))
            with self.assertRaisesRegex(ValueError, "Saved schedule or runtime differs"):
                await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=None, resume=True)
            run_pending.assert_awaited_once()

    async def test_resume_and_report_read_both_trace_formats(self):
        task = {"task_id": "example", "goal": "测量样品", "executor_limit": 4}
        rows = {"example": task}

        async def run_one(_task, _client, *, mode, workspace_id, save, **_limits):
            if mode == "eo" and workspace_id.endswith("/attempt-1"):
                raise APIConnectionError
            outcome = {"reason": "environment_done", "reward": 0.75, "success": False}
            record = {
                "mode": mode, "workspace_id": workspace_id, "outcome": outcome,
                "events": [{"type": "stop", "timestamp": "end", "reason": outcome["reason"]},
                           {"type": "verifier", "timestamp": "end", **outcome}],
            }
            save(record)
            return record

        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "AsyncChatClient", offline_client),
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={}),
              redirect_stdout(StringIO())):
            output = Path(directory) / "report.html"
            for suffix, options in ((".json", {}), (".json.gz", {"compress_traces": True})):
                with self.subTest(suffix=suffix):
                    dataset = {"name": "Storage test", "split": "test", "selection": "full_split",
                               "canonical_task_count": 1, "tasks": [task], **options}
                    run_dir = output.parent / f"run{suffix}"
                    trial_id = "m1-texample-eo"
                    record_path = f"trials/{trial_id}{suffix}"
                    archive_path = f"attempts/{trial_id}/attempt-000001{suffix}"
                    with patch.dict(os.environ, {benchmark.RATE_FILE_ENV: str(output.parent / "matrix.rate")}):
                        await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one, concurrency=1)
                    self.assertEqual(read_json(run_dir / record_path)["error"], "APIConnectionError")
                    missing_html = render_benchmark(run_dir, output, "storage-test")
                    self.assertNotIn(f'href="{run_dir.name}/{record_path}"', missing_html)
                    self.assertIn('aria-label="offline · EO · 任务 example · 缺评 · '
                                  '运行启动或基础设施错误 · APIConnectionError"', missing_html)
                    self.assertIn(">缺评</td>", missing_html)

                    await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one,
                                               concurrency=1, resume=True)
                    self.assertEqual(read_json(run_dir / archive_path)["attempt"], 1)
                    self.assertEqual(read_json(run_dir / record_path)["attempt"], 2)

                    await benchmark.run_matrix(run_dir, rows, dataset, "unused", run_one=run_one,
                                               concurrency=1, resume=True)
                    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(manifest["invocations"][0]["dispatch_rate_scope"], "host_shared")
                    self.assertEqual(manifest["trials"][trial_id]["archived_attempts"], [archive_path])
                    self.assertEqual(manifest["invocations"][-1]["pending_trials"], 0)
                    self.assertEqual(manifest["trial_counts"], {"complete": 4})
                    html = render_benchmark(run_dir, output, "storage-test")
                    self.assertIn(f'href="{run_dir.name}/{record_path}"', html)
                    self.assertNotIn(f'href="{run_dir.name}/{archive_path}"', html)
                    self.assertIn("已把 1 / 1 条归档尝试中可核对的消耗计入总量。", html)
                    self.assertIn(">0.75</a>", html)

                    stale = benchmark.scheduled_manifest(dataset, manifest["run_id"])
                    observed = matched_trials(run_dir, stale, preview=True)["offline", "example", "eo"]
                    self.assertEqual(observed.score, 0.75)
                    self.assertEqual(observed.past, (run_dir / archive_path,))

    def test_report_compares_common_tasks_and_validates_attempts(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("first", "second")),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            dataset = {"name": "ScienceWorld", "split": "test", "selection": "full_split",
                       "canonical_task_count": 2, "tasks": [{"task_id": "a"}, {"task_id": "b"}]}
            manifest = benchmark.scheduled_manifest(dataset, "example")
            manifest["status"] = "complete"
            missing_trial = "m2-tb-pc"
            for trial_id, trial in manifest["trials"].items():
                if trial_id == missing_trial:
                    trial["status"] = "error"
                    continue
                trial["status"] = "complete"
                score = 0.75 if trial["task_id"] == "a" else 1
                outcome = {"reason": "task_finish", "reward": score, "success": score == 1}
                record = {**trial, "run_id": manifest["run_id"], "attempt": 1, "outcome": outcome,
                          "events": [{"type": "stop", "reason": outcome["reason"]},
                                     {"type": "verifier", **outcome}]}
                write_json(run_dir / manifest["records"][trial_id], record)
            manifest_path = run_dir / "manifest.json"
            output = run_dir / "report.html"
            write_json(manifest_path, manifest)
            html = render_benchmark(run_dir, output, "comparison")
            self.assertIn("有效评分 15 / 16。全配置配对任务 1 / 2。", html)
            for model, count, average in (("first", 2, "0.875"), ("second", 1, "0.75")):
                self.assertIn(
                    f'{model}<br><span class="small">配对任务 {count} / 2</span></th>'
                    '<th scope="row" class="mode">EO</th><td class="number">0.875</td>'
                    f'<td class="number">{average}</td><td class="number"><strong>0.75</strong></td>', html,
                )
            self.assertIn("ScienceWorld 模拟器分数除以 100", html)
            self.assertIn("/sciworld_benchmark.py", html)

            trial = manifest["trials"][missing_trial]
            trial["status"] = "complete"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "score and completed status disagree"):
                render_benchmark(run_dir, output, "comparison")

            trial["status"] = "error"
            trial["archived_attempts"] = [trial["file"]]
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "Duplicate benchmark attempt path"):
                render_benchmark(run_dir, output, "comparison")

    def test_report_keeps_raw_trace_and_validates_native_webshop_replay(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            dataset = {"name": "WebShop", "split": "test", "selection": "full_split",
                       "canonical_task_count": 1, "tasks": [{"task_id": "a"}], "max_input_bytes": 5}
            manifest = benchmark.scheduled_manifest(dataset, "webshop-run")
            manifest["status"] = "complete"
            for trial in manifest["trials"].values():
                trial["status"] = "error"
            trial_id = "m1-ta-eo"
            trial = manifest["trials"][trial_id]
            trial.update(status="unscored", error="PromptBudgetExceeded")
            identity = {**trial, "run_id": manifest["run_id"], "attempt": 1}
            original_outcome = {"reason": "runtime_error", "reward": None, "success": None}
            messages = [{"role": "user", "content": "找杯子"}]
            events = [{"type": "model_call", "event_id": 1, "role": "executor", "response": None,
                       "messages": messages, "error": "PromptBudgetExceeded"},
                      {"type": "stop", "reason": "runtime_error"}, {"type": "verifier", **original_outcome}]
            original = run_dir / trial["file"]
            write_json(original, {**identity, "outcome": original_outcome, "events": events})
            write_json(run_dir / "manifest.json", manifest)
            sidecar = run_dir / "native-replay" / f"{trial_id}.json"
            input_bytes = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            replay = {**identity, "source": trial["file"], "method": "webshop_native_context_limit_replay",
                      "blocked_call_event_id": 1, "input_bytes": input_bytes, "max_input_bytes": 5,
                      "tool_events_replayed": 0, "outcome": {"reason": "prompt_budget", "reward": 0, "success": False}}
            write_json(sidecar, replay)
            html = render_benchmark(run_dir, run_dir / "report.html", "webshop")
            self.assertIn("有效评分 1 / 4。全配置配对任务 0 / 1。", html)
            self.assertIn(
                'offline<br><span class="small">配对任务 0 / 1</span></th>'
                '<th scope="row" class="mode">EO</th><td class="number">0</td>'
                '<td class="number">未评</td><td class="number"><strong>未评</strong></td>', html,
            )
            self.assertIn(f'href="native-replay/{trial_id}.json"', html)
            self.assertIn(f'href="trials/{trial_id}.json"', html)
            self.assertIn(">0</a>", html)
            self.assertEqual(read_json(original)["outcome"], original_outcome)
            write_json(sidecar, {**replay, "outcome": {"reason": "prompt_budget", "reward": 1, "success": True}})
            with self.assertRaisesRegex(ValueError, "native replay does not match"):
                render_benchmark(run_dir, run_dir / "report.html", "webshop")
            write_json(sidecar, {**replay, "blocked_call_event_id": 2})
            with self.assertRaisesRegex(ValueError, "native replay does not match"):
                render_benchmark(run_dir, run_dir / "report.html", "webshop")

    def test_report_imports_only_matching_terminal_budget_verdict(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            run_dir = Path(directory)
            output = run_dir / "report.html"
            messages = [{"role": "user", "content": "查任务"}]
            size = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            dataset = {"name": "Terminal-Bench", "split": "test", "selection": "reviewed_subset",
                       "canonical_task_count": 66, "source_commit": "official", "data_version": "v4.1.0",
                       "tasks": [{"task_id": "a", "task_version": "2.2.1"}], "max_input_bytes": size - 1}
            manifest = benchmark.scheduled_manifest(dataset, "terminal-run")
            manifest["status"] = "complete"
            for trial in manifest["trials"].values():
                trial["status"] = "error"
            trial = manifest["trials"]["m1-ta-eo"]
            trial.update(status="unscored", error="PromptBudgetExceeded")
            original = run_dir / trial["file"]
            manifest_path = run_dir / "manifest.json"
            result = run_dir / "harbor/a-native/result.json"
            lock = result.with_name("lock.json")
            harbor = {"release": "v4.1.0", "commit": "official", "task_version": "2.2.1",
                      "agent_network": "no-network", "verifier_phase_network": "no-network",
                      "result": str(result), "lock": str(lock)}
            outcome = {"reason": "runtime_error", "reward": None, "success": None}
            call = {"type": "model_call", "role": "executor", "status": "error", "response": None,
                    "messages": messages, "error": "PromptBudgetExceeded"}
            verdict = {"type": "verifier", **outcome, "native_result": str(result),
                       "timestamp": "2026-11-19T10:00:00+00:00"}
            events = [call, {"type": "execution_feedback", "return_reason": "runtime_error"},
                      {"type": "runtime_error", "error": "PromptBudgetExceeded"},
                      {"type": "stop", "reason": "runtime_error"}, verdict]
            record = {**trial, "run_id": manifest["run_id"], "attempt": 1, "outcome": outcome,
                      "events": events, "harbor": harbor}
            native = {"task_name": "terminal-bench/a", "finished_at": "2026-11-19T10:00:00Z",
                      "trial_name": "a-native", "reward_valid": True, "exception_info": None,
                      "verifier_environment_mode": "separate", "verifier_result": {"rewards": {"reward": 0}}}
            locked = {"task": {"name": "a", "version": "2.2.1"}}
            write_json(lock, locked)
            write_json(result, native)
            write_json(original, record)
            write_json(manifest_path, manifest)

            html = render_benchmark(run_dir, output, "terminal")
            self.assertIn("有效评分 1 / 4", html)
            self.assertIn("1 格在本地输入预算处停止", html)
            self.assertIn('href="harbor/a-native/result.json"', html)
            self.assertIn('href="trials/m1-ta-eo.json"', html)
            self.assertNotIn("原生重放", html)
            self.assertEqual(read_json(original), record)
            self.assertEqual(read_json(manifest_path), manifest)

            for name, path, changed, baseline in (
                ("provider fault", original, {**record, "events": [
                    {**call, "error": "RateLimitError"}, events[1],
                    {**events[2], "error": "RateLimitError"}, *events[-2:],
                ]}, record),
                ("tool after local rejection", original,
                 {**record, "events": [call, {"type": "tool_event", "action": "look"}, *events[1:]]}, record),
                ("response present", original, {**record, "events": [{**call, "response": {}}, *events[1:]]}, record),
                ("unlinked result", original,
                 {**record, "events": [*events[:-1], {**verdict, "native_result": str(lock)}]}, record),
                ("wrong source commit", original, {**record, "harbor": {**harbor, "commit": "other"}}, record),
                ("wrong task lock", lock, {"task": {"name": "a", "version": "2.2.0"}}, locked),
                ("invalid reward", result, {**native, "reward_valid": False}, native),
                ("wrong result time", result, {**native, "finished_at": "2026-11-19T11:00:00Z"}, native),
                ("native exception", result, {**native, "exception_info": {"type": "Error"}}, native),
                ("shared environment", result, {**native, "verifier_environment_mode": "shared"}, native),
                ("at byte limit", manifest_path,
                 {**manifest, "budget": {**manifest["budget"], "max_input_bytes_per_request": size}}, manifest),
            ):
                with self.subTest(name=name):
                    write_json(path, changed)
                    self.assertIn("有效评分 0 / 4", render_benchmark(run_dir, output, "terminal"))
                    write_json(path, baseline)

            external_lock = run_dir / "external-lock.json"
            write_json(external_lock, locked)
            lock.unlink()
            lock.symlink_to(external_lock)
            self.assertIn("有效评分 0 / 4", render_benchmark(run_dir, output, "terminal"))

    def test_report_combines_only_disjoint_matching_terminal_supplements(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(benchmark, "MODELS", ("offline",)),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(benchmark, "runtime_versions", return_value={})):
            root = Path(directory)
            runs = []
            for task_id in ("a", "b"):
                run_dir = root / task_id
                dataset = {"name": "Terminal-Bench", "split": "test", "selection": "reviewed_subset",
                           "canonical_task_count": 66, "source_commit": "official", "tasks": [{"task_id": task_id}]}
                manifest = benchmark.scheduled_manifest(dataset, task_id)
                manifest["status"] = "complete"
                for trial in manifest["trials"].values():
                    trial["status"] = "complete"
                    outcome = {"reason": "task_finish", "reward": 0, "success": False}
                    record = {**trial, "run_id": task_id, "attempt": 1, "outcome": outcome,
                              "events": [{"type": "stop", "reason": "task_finish"}, {"type": "verifier", **outcome}]}
                    write_json(run_dir / trial["file"], record)
                write_json(run_dir / "manifest.json", manifest)
                runs.append((run_dir, manifest))
            output = root / "report.html"
            html = render_benchmark(runs[0][0], output, "terminal", supplements=runs[1:])
            self.assertIn("2 / 66 个官方任务", html)
            self.assertIn("有效评分 8 / 8", html)
            self.assertIn('href="b/trials/m1-tb-eo.json"', html)
            with self.assertRaisesRegex(ValueError, "duplicate configurations"):
                render_benchmark(runs[0][0], output, "terminal", supplements=runs[:1])
            runs[1][1]["benchmark"]["source_commit"] = "different"
            with self.assertRaisesRegex(ValueError, "differs from the completed matching protocol"):
                render_benchmark(runs[0][0], output, "terminal", supplements=runs[1:])
