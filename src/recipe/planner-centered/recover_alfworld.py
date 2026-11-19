"""Give the audited ALFWorld infrastructure failures one additional attempt."""

import argparse
import asyncio
import json
import os
import shutil
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "experiments/planner-centered/runs"
BASELINE = RUNS / "alfworld-test-01"
RUNTIME = RUNS / "runtime"
FROZEN = RUNTIME / "alfworld-unpaced-source/src"
EXPECTED_FAILURES = Counter(RateLimitError=99, InternalServerError=6, APIConnectionError=4, APITimeoutError=1)
SOURCE_PATCH = "unpaced-source.patch"
FROZEN_FIELDS = ("run_id", "run_order", "records", "benchmark", "models", "budget", "source", "runtime")


def wave_directory(wave):
    return RUNS / f"alfworld-test-01-recovery-{wave:02d}" if wave else BASELINE


def wave_artifact(name, wave, suffix):
    return f"recovery-{name}{f'-{wave:02d}' if wave > 1 else ''}{suffix}"


def infrastructure_failure(benchmark, record):
    status = benchmark.trial_status(record)
    error = benchmark.checkpoint_error(record, status)
    if status == "unscored" and error in EXPECTED_FAILURES:
        return error
    if status == "error" and error == "OSError" and record["events"] == []:
        return error
    return None


def audited_selection(benchmark, baseline_dir, manifest, wave=1, prior_targets=None):
    dataset = manifest["benchmark"]
    trials = manifest["trials"]
    order = manifest["run_order"]
    if (manifest["status"] != "complete" or manifest["schema_version"] != 2
            or manifest["purpose"] != benchmark.PURPOSE or dataset["name"] != "ALFWorld"
            or dataset["split"] != "test" or dataset["selection"] != "full_split"
            or dataset["canonical_task_count"] != 134 or len(order) != 2144
            or len(trials) != 2144 or set(order) != trials.keys()
            or manifest["model_order"] != list(benchmark.MODELS)):
        raise ValueError("Unexpected ALFWorld baseline schedule")
    targets = {}
    for trial_id in order:
        saved = trials[trial_id]
        if (trial_id != saved["trial_id"] or saved["file"] != f"trials/{trial_id}.json"
                or Path(trial_id).name != trial_id or saved["file"] != manifest["records"][trial_id]):
            raise ValueError(f"Unexpected ALFWorld trace path for {trial_id}")
        current = {**saved}
        current.pop("error", None)
        benchmark.restore_checkpoint(baseline_dir, manifest["run_id"], current)
        if any(current.get(key) != saved.get(key) for key in ("status", "error", "archived_attempts")):
            raise ValueError(f"ALFWorld manifest and checkpoint differ for {trial_id}")
        if current["status"] == "complete":
            continue
        if prior_targets is None:
            if current["status"] != "unscored" or current.get("error") not in EXPECTED_FAILURES:
                raise ValueError(f"Unexpected unscored ALFWorld checkpoint for {trial_id}")
        else:
            if trial_id not in prior_targets:
                continue
            record = benchmark.read_record(baseline_dir / current["file"])
            if infrastructure_failure(benchmark, record) is None:
                continue
        targets[trial_id] = {
            "baseline_attempt": len(current["archived_attempts"]) + 1,
            "error": current["error"],
            "model": current["model"],
            "task_id": current["task_id"],
            "mode": current["mode"],
        }
    if prior_targets is None and Counter(target["error"] for target in targets.values()) != EXPECTED_FAILURES:
        raise ValueError("ALFWorld failures differ from the audited selection")
    return {
        "baseline": str(baseline_dir.relative_to(ROOT)),
        "baseline_run_id": manifest["run_id"],
        "baseline_invocations": len(manifest["invocations"]),
        "source_patch": SOURCE_PATCH,
        "launcher": wave_artifact("launcher", wave, ".py"),
        "targets": targets,
        "max_additional_attempts_per_trial": 1,
    }


def validate_completed_wave(benchmark, baseline_dir, baseline, run_dir, manifest, selection, selection_file):
    if (run_dir.is_symlink() or manifest["status"] != "complete" or not manifest["finished_at"]
            or benchmark.read_record(run_dir / selection_file) != selection
            or not (run_dir / selection["launcher"]).is_file()
            or (run_dir / SOURCE_PATCH).read_bytes() != (baseline_dir / SOURCE_PATCH).read_bytes()
            or any(manifest[key] != baseline[key] for key in FROZEN_FIELDS)):
        raise ValueError("Expected an audited completed predecessor wave")
    cutoff = selection["baseline_invocations"]
    invocations = manifest["invocations"]
    if (invocations[:cutoff] != baseline["invocations"] or not invocations[cutoff:]
            or any(not invocation["finished_at"] or invocation["source_patch"] != SOURCE_PATCH
                   or invocation.get("recovery_selection") != selection_file
                   or invocation.get("recovery_launcher") != selection["launcher"]
                   for invocation in invocations[cutoff:])):
        raise ValueError("Predecessor invocation provenance differs from its recovery selection")
    for trial_id, earlier in baseline["trials"].items():
        current = manifest["trials"][trial_id]
        if trial_id not in selection["targets"]:
            if any(current.get(key) != earlier.get(key) for key in ("status", "error", "archived_attempts")):
                raise ValueError(f"Predecessor changed an out-of-scope ALFWorld trial: {trial_id}")
            continue
        attempt = selection["targets"][trial_id]["baseline_attempt"]
        archive = f"attempts/{trial_id}/attempt-{attempt:06d}.json"
        if (current["archived_attempts"] != [*earlier["archived_attempts"], archive]
                or (run_dir / archive).read_bytes() != (baseline_dir / earlier["file"]).read_bytes()):
            raise ValueError(f"Predecessor did not preserve the earlier ALFWorld attempt: {trial_id}")


def read_selection(benchmark, wave):
    source = BASELINE
    baseline = benchmark.read_record(source / "manifest.json")
    selection = audited_selection(benchmark, source, baseline)
    for number in range(1, wave):
        run_dir = wave_directory(number)
        manifest = benchmark.read_record(run_dir / "manifest.json")
        validate_completed_wave(benchmark, source, baseline, run_dir, manifest, selection,
                                wave_artifact("selection", number, ".json"))
        source, baseline = run_dir, manifest
        selection = audited_selection(benchmark, source, baseline, number + 1, selection["targets"])
    return baseline, selection


def prepare(baseline_dir, recovery_dir, selection, selection_file, write_json):
    if recovery_dir.exists() or recovery_dir.is_symlink():
        if recovery_dir.is_symlink():
            raise ValueError("The recovery run directory must not be a symlink")
        return
    with TemporaryDirectory(prefix=".alfworld-recovery-", dir=RUNS) as tmp:
        stage = Path(tmp) / "run"
        shutil.copytree(baseline_dir, stage, ignore=shutil.ignore_patterns(".run.lock", ".recovery.lock"))
        shutil.copy2(Path(__file__), stage / selection["launcher"])
        write_json(stage / selection_file, selection)
        stage.rename(recovery_dir)


def allows_retry(benchmark, targets, baseline_dir, recovery_dir, run_dir, trial):
    if run_dir != recovery_dir:
        raise ValueError("The targeted retry can only write the recovery directory")
    trial_id = trial["trial_id"]
    target = targets.get(trial_id)
    if target is None or trial["status"] == "complete":
        return False
    path = run_dir / trial["file"]
    archives = trial["archived_attempts"]
    baseline_attempt = target["baseline_attempt"]
    if not path.exists() and len(archives) == baseline_attempt:
        # An interrupted rename can archive the baseline before the next attempt starts.
        return (run_dir / archives[-1]).read_bytes() == (baseline_dir / trial["file"]).read_bytes()
    if len(archives) + 1 != baseline_attempt:
        return False
    record = benchmark.read_record(path)
    return (record["attempt"] == baseline_attempt and infrastructure_failure(benchmark, record) == target["error"]
            and path.read_bytes() == (baseline_dir / trial["file"]).read_bytes())


def record_provenance(benchmark, recovery_dir, selection, selection_file, exclusive_run_lock, write_json):
    path = recovery_dir / "manifest.json"
    with exclusive_run_lock(recovery_dir / ".run.lock"):
        manifest = benchmark.read_record(path)
        for invocation in manifest["invocations"][selection["baseline_invocations"]:]:
            invocation.update(source_patch=SOURCE_PATCH, recovery_selection=selection_file,
                              recovery_launcher=selection["launcher"])
        write_json(path, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Audit the selection without writing files")
    modes.add_argument("--prepare-only", action="store_true", help="Copy and register the recovery run without API calls")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--wave", type=int, default=1, help="Recovery wave number starting at 1")
    args = parser.parse_args()

    if args.wave < 1:
        parser.error("Choose a positive --wave")
    baseline_dir = wave_directory(args.wave - 1)
    recovery_dir = wave_directory(args.wave)
    selection_file = wave_artifact("selection", args.wave, ".json")
    if not baseline_dir.is_dir() or baseline_dir.is_symlink():
        parser.error("The preceding completed ALFWorld run directory is required")

    sys.path[:0] = [str(FROZEN / "recipe/planner-centered"), str(FROZEN), str(RUNTIME / "python311")]
    import benchmark
    from toolkit.utils.files import write_json
    from toolkit.utils.runfiles import exclusive_run_lock

    if not 1 <= args.concurrency <= benchmark.MAX_CONCURRENCY:
        parser.error(f"Choose --concurrency between 1 and {benchmark.MAX_CONCURRENCY}")
    if (benchmark.MODEL_SETTINGS["executor"]["base_url"] != "https://agi.tongji.edu.cn/v1"
            or not (BASELINE / SOURCE_PATCH).is_file() or BASELINE.is_symlink()):
        parser.error("Expected the frozen official Tongji runner and ALFWorld baseline")
    api_key = os.getenv("TONGJI_API_KEY")
    baseline_lock = nullcontext() if args.dry_run else exclusive_run_lock(baseline_dir / ".run.lock")
    with baseline_lock:
        baseline, selection = read_selection(benchmark, args.wave)
        targets = selection["targets"]
        print(json.dumps({"targets": len(targets), "by_error": Counter(target["error"] for target in targets.values()),
                          "max_model_requests": sum(baseline["trials"][key]["executor_limit"]
                                                    + baseline["trials"][key]["planner_limit"] for key in targets)},
                         ensure_ascii=False), flush=True)
        if args.dry_run or not targets:
            return
        if not (args.prepare_only or api_key):
            parser.error("Set TONGJI_API_KEY in the environment")
        prepare(baseline_dir, recovery_dir, selection, selection_file, write_json)

    with exclusive_run_lock(recovery_dir / ".recovery.lock"):
        if benchmark.read_record(recovery_dir / selection_file) != selection:
            raise ValueError("The saved recovery selection differs from the baseline audit")
        if args.prepare_only:
            print(recovery_dir, flush=True)
            return
        manifest = benchmark.read_record(recovery_dir / "manifest.json")
        for key in FROZEN_FIELDS:
            if manifest[key] != baseline[key]:
                raise ValueError(f"The recovery manifest differs from the frozen {key}")
        if manifest["invocations"][:selection["baseline_invocations"]] != baseline["invocations"]:
            raise ValueError("ALFWorld baseline invocation provenance changed")
        dataset = baseline["benchmark"]

        def retry(run_dir, trial):
            return allows_retry(benchmark, targets, baseline_dir, recovery_dir, run_dir, trial)

        trial_updates = []
        for trial_id in targets:
            trial = {**manifest["trials"][trial_id]}
            benchmark.restore_checkpoint(recovery_dir, manifest["run_id"], trial)
            trial_updates.append(trial)
        pending = sum(retry(recovery_dir, trial) for trial in trial_updates)
        if not pending and manifest["status"] == "complete":
            record_provenance(benchmark, recovery_dir, selection, selection_file, exclusive_run_lock, write_json)
            print("No additional approved ALFWorld attempts remain.", flush=True)
            return
        print(f"Starting {pending} approved ALFWorld attempts with concurrency {args.concurrency}.", flush=True)
        os.environ[benchmark.UNPACED_ENV] = "1"
        try:
            with patch.object(benchmark, "can_retry_trial", retry):
                asyncio.run(benchmark.run_benchmark(
                    recovery_dir, Path(dataset["data_dir"]), Path(dataset["gamefile_map"]), api_key,
                    concurrency=args.concurrency, resume=True,
                ))
        finally:
            record_provenance(benchmark, recovery_dir, selection, selection_file, exclusive_run_lock, write_json)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        sys.exit(f"ALFWorld recovery stopped ({type(error).__name__}).")
