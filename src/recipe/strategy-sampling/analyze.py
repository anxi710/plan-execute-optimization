"""Blind candidate plans, queue paired executions, and summarize the pilot."""

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from toolkit.utils.files import read_jsonl, read_yaml_mapping, write_json, write_jsonl
from toolkit.utils.runfiles import save_settings


def blind(run, tasks, *, samples_per_condition, blind_seed):
    index = []
    documents = {}
    expected = {(condition, slot) for condition in ("A", "B") for slot in range(samples_per_condition)}
    for task_id, task in sorted(tasks.items()):
        candidates = sorted(read_jsonl(run / "plans" / f"{task_id}.jsonl"),
                            key=lambda row: (row["condition"], row["sample"]))
        if len(candidates) != len(expected) or {(row["condition"], row["sample"]) for row in candidates} != expected:
            raise ValueError(f"Task {task_id} does not have all {len(expected)} candidates")
        random.Random(f"{blind_seed}/{task_id}").shuffle(candidates)
        rows = []
        for number, row in enumerate(candidates, 1):
            blind_id = f"T{task_id}-{number:02}"
            rows.append({"blind_id": blind_id, "plan": row["plan"]})
            index.append({**row, "blind_id": blind_id})
        documents[task_id] = {"task": task["task"], "plans": rows}
    index_path = run / "blind_index.jsonl"
    if index_path.exists() and read_jsonl(index_path) != index:
        raise ValueError("Blind index differs from this run. Use a new run directory.")
    save_settings(run / "blind_settings.json", {
        "blind_seed": blind_seed, "samples_per_condition": samples_per_condition,
    })
    directory = run / "blinded"
    directory.mkdir(exist_ok=True)
    for task_id, document in documents.items():
        write_json(directory / f"{task_id}.json", document)
    write_jsonl(index_path, index)


def analyze(run, tasks, *, coverage_prefixes):
    labels = {}
    for path in sorted((run / "labels").glob("*.json")):
        for row in json.loads(path.read_text()):
            if row["blind_id"] in labels:
                raise ValueError(f"Duplicate route label: {row['blind_id']}")
            labels[row["blind_id"]] = row
    index = read_jsonl(run / "blind_index.jsonl")
    valid = {row["blind_id"] for row in index if row["plan"]}
    if valid != set(labels):
        raise ValueError(f"Labels incomplete: missing={valid - set(labels)}, extra={set(labels) - valid}")
    for row in index:
        row.update(labels.get(row["blind_id"], {"route": "uncertain"}))
        row["tokens"] = row["usage"]["total_tokens"]
    rows = []
    queue = read_jsonl(run / "controls.jsonl")
    for task_id, task in sorted(tasks.items()):
        groups = {
            condition: sorted(
                (row for row in index
                 if int(row["task_id"]) == task_id and row["condition"] == condition),
                key=lambda row: row["sample"],
            )
            for condition in ("A", "B")
        }
        counts = {key: sum(row["tokens"] for row in group) for key, group in groups.items()}
        common_budget = min(counts.values())
        by_budget = {}
        for key, group in groups.items():
            used = 0
            by_budget[key] = []
            for row in group:
                used += row["tokens"]
                if used > common_budget:
                    break
                by_budget[key].append(row)

        def routes(group):
            return Counter(row["route"] for row in group if row["route"] != "uncertain")

        common_routes = {key: routes(group) for key, group in by_budget.items()}
        new_routes = set(common_routes["B"]) - set(common_routes["A"])
        rows.append({
            "task_id": task_id, "group": task["group"],
            "by_k": {key: {str(prefix): len(routes(group[:prefix]))
                           for prefix in coverage_prefixes if prefix <= len(group)}
                     for key, group in groups.items()},
            "all_routes": {key: routes(group) for key, group in groups.items()},
            "common_tokens": common_budget,
            "tokens": counts, "within_budget": {key: len(group) for key, group in by_budget.items()},
            "matched_routes": common_routes, "B_only_routes": sorted(new_routes),
            "uncertain": {key: sum(row["route"] == "uncertain" for row in group)
                          for key, group in groups.items()},
        })
        dominant = max(common_routes["A"], key=common_routes["A"].get, default=None)
        left = next((row for row in by_budget["A"] if row["route"] == dominant), None)
        right = next((row for row in by_budget["B"] if row["route"] in new_routes), None)
        if not right:
            right = next((row for group in by_budget.values() for row in group
                          if row["route"] not in (dominant, "uncertain")), None)
        if not right:
            right = next((row for row in by_budget["B"] if row["plan"]), None)
        for row in (left, right):
            if row:
                queue.append({"task_id": task_id, "task": task["task"], "plan": row["plan"],
                              "plan_id": row["blind_id"], "route": row["route"],
                              "condition": row["condition"], "sample": row["sample"]})
    write_jsonl(run / "execution_queue.jsonl", [dict(row, task_id=int(row["task_id"])) for row in queue])
    write_json(run / "coverage.json", rows)
    return queue


def report(run, *, samples_per_plan):
    files = sorted((run / "executions").glob("*/sample_*.json"))
    queue = read_jsonl(run / "execution_queue.jsonl")
    results = []
    rollouts = {}
    for path in files:
        records = json.loads(path.read_text())
        final = records[-1]
        rollouts.setdefault(path.parent.name, []).append(final)
    for plan in queue:
        trajectories = rollouts.get(plan["plan_id"], [])
        complete = [row for row in trajectories if row["finished"] and not row.get("incomplete")]
        results.append({
            "plan_id": plan["plan_id"], "task_id": plan["task_id"], "route": plan["route"],
            "condition": plan.get("condition", "reference"), "successes": sum(row["success"] for row in complete),
            "complete": len(complete), "incomplete": len(trajectories) - len(complete),
            "steps": [row["steps"] for row in complete],
            "mean_steps": statistics.mean(row["steps"] for row in complete) if complete else None,
            "requests": sum(row.get("executor_requests", 0) for row in trajectories),
            "usage": dict(sum((Counter(row["executor_usage"]) for row in trajectories), Counter())),
        })
    write_json(run / "execution_summary.json", results)
    print(f"{sum(row['complete'] for row in results)}/{samples_per_plan * len(queue)} rollouts complete")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("blind", "queue", "report"))
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    recipe = read_yaml_mapping(args.config)
    run_dir = args.run_dir or recipe["run_dir"]
    if not run_dir:
        parser.error("Set run_dir in the recipe config or pass --run-dir")
    run_dir = Path(run_dir)
    if args.stage == "report":
        execution = json.loads((run_dir / "executions/run_settings.meta").read_text(encoding="utf-8"))
        report(run_dir, samples_per_plan=execution["samples_per_plan"])
        return
    tasks = {int(row["id"]): row for row in read_jsonl(run_dir / "tasks.jsonl")}
    if args.stage == "blind":
        planner = json.loads((run_dir / "planner_settings.json").read_text(encoding="utf-8"))
        blind(run_dir, tasks, samples_per_condition=planner["samples_per_condition"],
              blind_seed=recipe["analysis"]["blind_seed"])
    else:
        prefixes = recipe["analysis"]["coverage_prefixes"]
        if not isinstance(prefixes, list) or any(type(prefix) is not int or prefix < 1 for prefix in prefixes):
            parser.error("coverage_prefixes must be a list of positive integers")
        print(f"{len(analyze(run_dir, tasks, coverage_prefixes=prefixes))} plans queued")


if __name__ == "__main__":
    main()
