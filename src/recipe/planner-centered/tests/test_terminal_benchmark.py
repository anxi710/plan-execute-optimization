from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, call, patch

if importlib.util.find_spec("harbor") is None:
    raise unittest.SkipTest("Terminal recipe tests require Harbor")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import benchmark
import run
import terminal_benchmark as terminal


class TerminalBenchmarkTest(unittest.IsolatedAsyncioTestCase):
    def test_terminal_entry_uses_recipe_connection_and_models(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text(
                "models: [custom-model]\ntoolkit:\n  planner_generation:\n    model_name: planner-model\n"
                "    api_base: http://planner.test/v1\n    api_key: planner-key\n  executor:\n"
                "    model_name: custom-model\n    api_base: http://executor.test/v1\n    api_key: executor-key\n"
                "  context_window:\n    max_input_tokens: 12345\n",
                encoding="utf-8",
            )
            with (patch.dict(os.environ, {}, clear=True),
                  patch.object(terminal, "run_benchmark", new_callable=AsyncMock) as dispatch):
                terminal.main(["--config", str(config), "--terminal-bench-root", directory, "--run-dir", directory])
            self.assertEqual(dispatch.await_args.args[2], {"planner": "planner-key", "executor": "executor-key"})
            self.assertEqual(dispatch.await_args.kwargs["model_order"], ["custom-model"])
            self.assertEqual(dispatch.await_args.kwargs["context_window"], {"max_input_tokens": 12345})
            self.assertEqual(dispatch.await_args.kwargs["model_settings"]["planner"]["base_url"], "http://planner.test/v1")
            self.assertEqual(dispatch.await_args.kwargs["model_settings"]["planner"]["model"], "planner-model")
            self.assertEqual(dispatch.await_args.kwargs["model_settings"]["executor"]["base_url"], "http://executor.test/v1")
            for key in ("planner-key", "executor-key"):
                self.assertNotIn(key, json.dumps(dispatch.await_args.kwargs))

    def test_preflight_does_not_load_connection_config(self):
        with (TemporaryDirectory() as directory,
              patch.object(terminal, "load_model_settings", side_effect=AssertionError("Unexpected connection load")),
              patch.object(terminal, "preflight", new_callable=AsyncMock) as preflight):
            terminal.main(["--config", str(Path(directory) / "missing.yaml"), "--terminal-bench-root", directory,
                           "--preflight-output", directory])
            preflight.assert_awaited_once()

    def test_coq_offline_build_uses_each_reviewed_image(self):
        with TemporaryDirectory() as directory:
            trial = Path(directory)
            for phase, (tag, image_id) in terminal.COQ_IMAGES.items():
                with self.subTest(phase=phase):
                    with patch.object(terminal.subprocess, "check_output", return_value="sha256:other linux/amd64\n"):
                        with self.assertRaisesRegex(ValueError, "reviewed amd64 image configs"):
                            terminal.offline_coq_build(trial / phase, trial)
                    self.assertFalse((trial / f"coq-{phase}-offline.Dockerfile").exists())
                    with patch.object(terminal.subprocess, "check_output", return_value=f"{image_id} linux/amd64\n") as inspect:
                        overlay = terminal.offline_coq_build(trial / phase, trial)
                    self.assertEqual(inspect.call_args.args[0][-1], tag)
                    build = json.loads(overlay.read_text())["services"]["main"]["build"]
                    self.assertEqual(Path(build["dockerfile"]).read_text(), f"FROM {tag}\n")

    def test_debian_build_installs_only_verified_archives(self):
        cases = (
            (terminal.SOUND_CHANGE_TASK, "environment", "dpkg -i --", "./reviewed.deb"),
            (terminal.MVCC_TASK, "environment", "apt-get -o Acquire::Retries=0 --no-install-recommends -y install", "/debs/reviewed.deb"),
            (terminal.VF2_TASK, "environment", "apt-get -o Acquire::Retries=0 --no-install-recommends -y install", "/debs/reviewed.deb"),
            (terminal.BATCHED_TASK, "tests", "dpkg -i --", "./reviewed.deb"),
            (terminal.KS_TASK, "tests", "apt-get -o Acquire::Retries=0 --no-install-recommends -y install", "/debs/reviewed.deb"),
            (terminal.DRIFT_TASK, "tests", "apt-get -o Acquire::Retries=0 --no-install-recommends -y install", "/debs/reviewed.deb"),
            (terminal.CARGO_TASK, "tests", "dpkg -i --", "./reviewed.deb"),
            (terminal.ONTOLOGY_TASK, "tests", "dpkg -i --", "./reviewed.deb"),
            (terminal.WAL_TASK, "tests", "dpkg -i --", "./reviewed.deb"),
        )
        for task_key, phase, installer, archive in cases:
            with self.subTest(task_key=task_key), TemporaryDirectory() as directory:
                _, online_commands = terminal.DEBIAN_BUILDS[task_key][phase]
                command = terminal.offline_debian_build("\n".join(online_commands), task_key, phase)
                install = command.split("cd /debs && ", 1)[1].split(" && dpkg-query", 1)[0]
                self.assertIn(installer, install)
                script = 'install_archives() { printf "installed %s\\n" "$@"; }\n'
                script += install.replace(installer, "install_archives")
                debs = Path(directory)
                reviewed = debs / "reviewed.deb"
                reviewed.write_bytes(b"reviewed fixture")
                (debs / "unlisted.deb").write_bytes(b"not in manifest")
                digest = sha256(reviewed.read_bytes()).hexdigest()
                (debs / "SHA256SUMS").write_text(f"{digest}  ./reviewed.deb\n")
                result = subprocess.run(["sh", "-ec", script], cwd=debs, capture_output=True, text=True, check=True)
                self.assertIn(f"installed {archive}", result.stdout)
                self.assertNotIn("unlisted.deb", result.stdout)
                reviewed.write_bytes(b"edited fixture")
                result = subprocess.run(["sh", "-ec", script], cwd=debs, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("installed", result.stdout)

    def test_risk_debian_install_preserves_verifier_compiler_cleanup(self):
        for phase, (packages, (online,)) in terminal.DEBIAN_BUILDS[terminal.RISK_TASK].items():
            with self.subTest(phase=phase):
                cleanup = "RUN apt-get purge -y --auto-remove gcc libc6-dev"
                result = terminal.offline_debian_build(f"{online}\n{cleanup}\n", terminal.RISK_TASK, phase)
                self.assertIn("sha256sum --strict -c SHA256SUMS", result)
                self.assertIn("file:/debs", result)
                self.assertIn("Dir::Etc::sourceparts=- update", result)
                self.assertIn(f"Dir::Etc::sourceparts=- install -y --no-install-recommends {packages}", result)
                self.assertTrue(result.endswith(f"\n{cleanup}\n"))

    def test_vf2_requires_its_reviewed_rust_manifest(self):
        with TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            review = checkout.parent / f"{terminal.VF2_TASK}-review"
            wheelhouse = review / "wheels"
            wheelhouse.mkdir(parents=True)
            for phase in ("environment", "tests"):
                manifest = review / "deb" / phase / "SHA256SUMS"
                manifest.parent.mkdir(parents=True)
                manifest.touch()
            inspected = "".join(
                f"{image_id} linux/amd64\n" for _, image_id in terminal.WHEELHOUSE_BASES[terminal.VF2_TASK].values()
            )
            with patch.object(terminal.subprocess, "check_output", return_value=inspected):
                with self.assertRaisesRegex(FileNotFoundError, "Rust toolchain manifest"):
                    terminal.reviewed_wheels(checkout, terminal.VF2_TASK)
                manifest = review / "rust" / "SHA256SUMS"
                manifest.parent.mkdir()
                manifest.touch()
                self.assertEqual(terminal.reviewed_wheels(checkout, terminal.VF2_TASK), wheelhouse)

    def test_extra_roots_cannot_duplicate_or_add_unreviewed_tasks(self):
        primary = Path("music")
        with self.assertRaisesRegex(ValueError, "outside the reviewed recipe scope"):
            terminal.selected_task_roots(primary, terminal.MUSIC_TASK, None, [("other", "other")])
        with self.assertRaisesRegex(ValueError, "has more than one root"):
            terminal.selected_task_roots(primary, terminal.MUSIC_TASK, "finance", [(terminal.FINANCE_TASK, "finance")])

    async def test_reviewed_manifest_dispatches_each_task_into_its_own_checkout(self):
        roots = {key: Path(key).resolve() for key in terminal.REVIEWED_TASK_VERSIONS}
        run_dir = Path("unused-dry-run")
        window = {"max_input_tokens": 12345}

        def checked_task(root, task_id):
            self.assertEqual(root, roots[task_id])
            return root, SimpleNamespace(observation="Local fixture", version=terminal.REVIEWED_TASK_VERSIONS[task_id])

        async def check_matrix(path, rows, dataset, api_key, *, run_one, concurrency, resume, protocol_version,
                               model_settings, model_order, context_window):
            self.assertIsNone(model_settings)
            self.assertIsNone(model_order)
            self.assertEqual((path, api_key, concurrency, resume), (run_dir, "unused", 1, True))
            self.assertEqual(dataset["selection"], "reviewed_subset")
            self.assertEqual(dataset["canonical_task_count"], 66)
            self.assertEqual(dataset["task_roots"], {key: str(root) for key, root in roots.items()})
            self.assertNotIn("max_input_bytes", dataset)
            self.assertNotIn("return_every", dataset)
            self.assertIs(context_window, window)
            self.assertEqual(list(rows), list(roots))
            manifest = benchmark.scheduled_manifest(dataset, "terminal-test", protocol_version=protocol_version)
            self.assertEqual(len(manifest["trials"]), 360)
            for row in rows.values():
                await run_one(row, None, mode="eo", model_settings={}, context_window=context_window,
                              executor_limit=40, workspace_id="offline-terminal", save=lambda _: None)

        with (patch.object(benchmark, "run_matrix", new=check_matrix),
              patch.object(benchmark, "requested_protocol", return_value=benchmark.FRAMEWORK_PROTOCOL),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(terminal, "reviewed_task", side_effect=checked_task),
              patch.object(terminal, "reviewed_wheels") as wheels,
              patch.object(terminal, "verify_reviewed_images") as images,
              patch.object(run, "model_call", return_value=None) as model_factory,
              patch.object(terminal, "run_terminal_trial", new_callable=AsyncMock) as dispatch):
            await terminal.run_benchmark(
                roots[terminal.MUSIC_TASK], run_dir, "unused", finance_root=roots[terminal.FINANCE_TASK],
                additional_task_roots=[(key, roots[key]) for key in (
                    terminal.PHOTONIC_TASK, terminal.PRODUCTION_TASK, terminal.SOUND_CHANGE_TASK, terminal.MVCC_TASK,
                    terminal.VF2_TASK, terminal.BATCHED_TASK, terminal.COQ_TASK, terminal.KS_TASK, terminal.DRIFT_TASK,
                    terminal.CARGO_TASK, terminal.ONTOLOGY_TASK, terminal.WAL_TASK, terminal.RISK_TASK,
                )],
                resume=True, context_window=window,
            )
        self.assertEqual(wheels.call_args_list, [call(roots[key], key) for key in terminal.WHEELHOUSE_BASES])
        images.assert_called_once()
        self.assertEqual(images.call_args.args[0], terminal.COQ_TASK)
        self.assertEqual(list(images.call_args.args[1]), list(terminal.COQ_IMAGES.values()))
        self.assertEqual(
            [(entry.kwargs["task_key"], entry.args[0]) for entry in dispatch.await_args_list], list(roots.items()),
        )
        self.assertTrue(all(entry.kwargs["context_window"] is window for entry in dispatch.await_args_list))
        self.assertTrue(all(entry.kwargs["protocol_version"] == terminal.FRAMEWORK_PROTOCOL
                            for entry in dispatch.await_args_list))
        self.assertEqual(model_factory.call_args_list, [call(None, "executor", model_settings={})] * len(roots))

    async def test_scripted_preflight_uses_current_pc_stages_and_executor_submission(self):
        environment = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(
            return_code=0, stdout="workspace retained\n", stderr="",
        )))
        records = []

        async def trial(_root, directory, *, task_key, **options):
            record = await terminal.run_framework(
                env=terminal.TerminalWorkspace(environment, "Inspect the public input.", options["executor_limit"]),
                goal="Inspect the public input.", benchmark="terminalbench", external_verifier=True, **options,
            )
            record["outcome"] = {"reason": record["events"][-1]["reason"], "success": False, "reward": 0.0}
            record["events"].append({"type": "verifier", **record["outcome"]})
            record["harbor"] = {}
            for field in ("result", "lock", "verifier_dockerfile"):
                path = directory.parent / field
                path.touch()
                record["harbor"][field] = str(path)
            records.append(record)
            return record

        with (TemporaryDirectory() as directory,
              patch.object(terminal, "run_terminal_trial", new=trial), patch("builtins.print")):
            await terminal.preflight(Path(directory), Path(directory) / "output")
        record, = records
        self.assertEqual(record["mode"], "pc-s")
        self.assertEqual(record["protocol_version"], terminal.FRAMEWORK_PROTOCOL)
        self.assertEqual(environment.exec.await_count, 2)
        stop = next(event for event in record["events"] if event["type"] == "stop")
        self.assertEqual((stop["reason"], stop["real_environment_steps"]), ("task_finish", 2))
        requests = [event for event in record["events"] if event["type"] == "execution_request"]
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(event["assessment"] for event in record["events"] if event["type"] == "planner_decision"))
