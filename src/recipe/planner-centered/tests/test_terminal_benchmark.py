from hashlib import sha256
import importlib.util
import json
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

        def checked_task(root, task_id):
            self.assertEqual(root, roots[task_id])
            return root, SimpleNamespace(observation="Local fixture", version=terminal.REVIEWED_TASK_VERSIONS[task_id])

        async def check_matrix(path, rows, dataset, api_key, *, run_one, concurrency, resume):
            self.assertEqual((path, api_key, concurrency, resume), (run_dir, "unused", 1, True))
            self.assertEqual(dataset["selection"], "reviewed_subset")
            self.assertEqual(dataset["canonical_task_count"], 66)
            self.assertEqual(dataset["task_roots"], {key: str(root) for key, root in roots.items()})
            self.assertEqual(list(rows), list(roots))
            manifest = benchmark.scheduled_manifest(dataset, "terminal-test")
            self.assertEqual(len(manifest["trials"]), 240)
            for row in rows.values():
                await run_one(row, None, model_settings={}, max_input_bytes=128, executor_limit=40, planner_limit=0)

        with (patch.object(benchmark, "run_matrix", new=check_matrix),
              patch.object(benchmark, "source_version", return_value={}),
              patch.object(terminal, "reviewed_task", side_effect=checked_task),
              patch.object(terminal, "reviewed_wheels") as wheels,
              patch.object(terminal, "verify_reviewed_images") as images,
              patch.object(run, "model_call", return_value=None),
              patch.object(terminal, "run_terminal_trial", new_callable=AsyncMock) as dispatch):
            await terminal.run_benchmark(
                roots[terminal.MUSIC_TASK], run_dir, "unused", finance_root=roots[terminal.FINANCE_TASK],
                additional_task_roots=[(key, roots[key]) for key in (
                    terminal.PHOTONIC_TASK, terminal.PRODUCTION_TASK, terminal.SOUND_CHANGE_TASK, terminal.MVCC_TASK,
                    terminal.VF2_TASK, terminal.BATCHED_TASK, terminal.COQ_TASK, terminal.KS_TASK, terminal.DRIFT_TASK,
                    terminal.CARGO_TASK, terminal.ONTOLOGY_TASK, terminal.WAL_TASK, terminal.RISK_TASK,
                )],
                resume=True,
            )
        self.assertEqual(wheels.call_args_list, [call(roots[key], key) for key in terminal.WHEELHOUSE_BASES])
        images.assert_called_once()
        self.assertEqual(images.call_args.args[0], terminal.COQ_TASK)
        self.assertEqual(list(images.call_args.args[1]), list(terminal.COQ_IMAGES.values()))
        self.assertEqual(
            [(entry.kwargs["task_key"], entry.args[0]) for entry in dispatch.await_args_list], list(roots.items()),
        )
