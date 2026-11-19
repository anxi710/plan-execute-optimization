"""Run all four frameworks on the complete 500-goal WebShop test split."""

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
from contextlib import ExitStack, closing, contextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from uuid import uuid4

from benchmark import CONCURRENCY, PURPOSE, SCHEMA_VERSION, run_matrix
from run import model_call
from runner import run_trial
from toolkit.envs.webshop_env import WebShopEnv, webshop_settings
from toolkit.tasks.webshop import WebShopTask
from toolkit.utils.files import read_json, write_json
from webshop_catalog import TEST_GOALS, UPSTREAM_REVISION, goal_key, shared_server


CONSTRAINTS = ["Act only through the provided WebShop text environment."]
REPLAY_METHOD = "webshop_native_context_limit_replay"


class WebShopBenchmarkEnv(WebShopEnv):
    """Keep the purchase page's printed score available only to the verifier."""

    def execute_action(self, action):
        result = super().execute_action(action)
        if result.done:
            return replace(result, observation="The purchase ended the WebShop session.")
        return result


@contextmanager
def isolated_environment(server, task, executor_limit):
    from web_agent_site.envs import WebAgentTextEnv

    env = WebAgentTextEnv(observation_mode="text", server=server, session_prefix=f"{uuid4().hex}-")
    startup_session = env.session
    try:
        adapter = WebShopBenchmarkEnv(task, env, plan_placement="query",
                                      **{**webshop_settings(), "max_steps": executor_limit})
        yield adapter
    finally:
        # The upstream constructor creates a random initial session before the task-specific reset.
        server.user_sessions.pop(startup_session, None)
        server.user_sessions.pop(env.session, None)
        env.close()


async def run_one(server, task, client, *, mode, workspace_id, model_settings, max_input_bytes,
                  save, executor_limit, planner_limit, return_every):
    options = {"model_settings": model_settings, "max_input_bytes": max_input_bytes}
    with isolated_environment(server, task, executor_limit) as env:
        return await run_trial(
            mode=mode, env=env, planner=model_call(client, "planner", planner_limit, **options) if planner_limit else None,
            executor=model_call(client, "executor", executor_limit, **options), goal=task.observation,
            constraints=CONSTRAINTS, workspace_id=workspace_id, executor_limit=executor_limit,
            planner_limit=planner_limit, return_every=return_every, save=save, benchmark="webshop",
        )


def load_test_split(data_dir):
    metadata = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
    if (not metadata.get("full_catalog") or not metadata.get("verified_official_test_ids")
            or metadata["source_revision"] != UPSTREAM_REVISION):
        raise ValueError("Use a full WebShop catalog with verified official test IDs")
    loaded, count = WebShopTask.load_tasks(data_dir, split="test")
    rows = {task.task_id: task for task in loaded}
    if (count != TEST_GOALS or len(rows) != TEST_GOALS
            or {task.session for task in rows.values()} != set(range(TEST_GOALS))
            or any(task.task_id != str(task.session) for task in rows.values())):
        raise ValueError("Expected the complete official WebShop test split, session indices 0–499")
    return metadata, rows


def reset_test_sessions(server, rows, executor_limit):
    for task in rows.values():
        instruction = server.goals[task.session]["instruction_text"]
        if task.observation != f"Instruction: {instruction}":
            raise ValueError(f"WebShop task {task.task_id} does not match its native session")
        with isolated_environment(server, task, executor_limit) as env:
            env.reset()
    if server.user_sessions:
        raise ValueError("WebShop preflight left live sessions")


def verify_prepared(data_dir, official_goals):
    """Verify the native index and complete session map before publishing the data."""
    metadata, rows = load_test_split(data_dir)
    reference = json.loads(official_goals.read_text(encoding="utf-8"))
    empty_asins = set()
    document_count = 0
    # Anserini rejects contents that are empty after Java String.trim().
    java_trim = "".join(chr(code) for code in range(0x21))
    with (data_dir / "documents" / "products.jsonl").open(encoding="utf-8") as documents:
        for document_count, line in enumerate(documents, start=1):
            document = json.loads(line)
            if not document["contents"].strip(java_trim):
                empty_asins.add(document["id"])
    uri = (data_dir / "products.sqlite3").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        catalog_count = database.execute("SELECT count(*) FROM products").fetchone()[0]
    if catalog_count != document_count or catalog_count != metadata["products"]:
        raise ValueError("WebShop source documents and SQLite catalog have different product counts")
    indexed_count = catalog_count - len(empty_asins)
    with shared_server(data_dir) as server:
        if (server.search_engine.num_docs != indexed_count or len(server.goals) != metadata["human_goals"]
                or not server.search_engine.search("soap", k=1)):
            raise ValueError("WebShop native index or goals do not match the prepared catalog")
        for asin in empty_asins:
            if asin not in server.product_item_dict or server.search_engine.doc(asin) is not None:
                raise ValueError(f"WebShop native index coverage differs for empty product document {asin}")
        for task in rows.values():
            goal = server.goals[task.session]
            if goal_key(goal["instruction_text"]) != goal_key(reference[task.session]):
                raise ValueError(f"WebShop native session {task.session} differs from the official goal")
            if goal["asin"] not in server.product_item_dict or server.search_engine.doc(goal["asin"]) is None:
                raise ValueError(f"WebShop native session {task.session} has a missing target product")
        reset_test_sessions(server, rows, webshop_settings()["max_steps"])
    verified = {
        "native_sessions_verified": len(rows), "reference_test_indices_verified": len(rows),
        "catalog_products_verified": catalog_count, "indexed_products_verified": indexed_count,
        "native_empty_documents": len(empty_asins), "native_search_smoke": True,
    }
    write_json(data_dir / "verified.json", verified)
    return verified


def context_limit_evidence(record, identity, max_input_bytes, executor_limit):
    """Match the local Executor rejection and its complete native action prefix."""
    if record.get("outcome") != {"reason": "runtime_error", "success": None, "reward": None}:
        return None
    if (any(record.get(key) != value for key, value in identity.items())
            or record.get("arm") != identity["mode"] or record.get("budgets", {}).get("executor_limit") != executor_limit):
        return None
    events = record["events"]
    if [event["type"] for event in events[-5:]] != [
        "model_call", "execution_feedback", "runtime_error", "stop", "verifier",
    ]:
        return None
    blocked, feedback, failure, stop, verdict = events[-5:]
    if (blocked.get("role") != "executor" or blocked.get("status") != "error"
            or blocked.get("error") != "PromptBudgetExceeded" or blocked.get("response") is not None
            or failure.get("error") != "PromptBudgetExceeded" or feedback.get("return_reason") != "runtime_error"
            or stop.get("reason") != "runtime_error"
            or any(verdict.get(key) != value for key, value in record["outcome"].items())):
        return None
    messages = blocked.get("messages")
    if (not isinstance(messages, list) or not messages or not all(isinstance(message, dict) for message in messages)
            or messages[-1].get("role") != "user"):
        return None
    # Match the byte count in model_call before it opens the HTTP request.
    size = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size <= max_input_bytes:
        return None
    event_identity = {**{key: value for key, value in identity.items() if key != "mode"}, "arm": identity["mode"]}
    if any(event.get("event_id") != index or any(event.get(key) != value for key, value in event_identity.items())
           for index, event in enumerate(events, 1)):
        return None
    initial = [event for event in events if event["type"] == "initial_observation"]
    if len(initial) != 1 or initial[0]["event_id"] != 1:
        return None
    actions = [event for event in events if event["type"] == "tool_event"]
    calls = [event for event in events[:-5] if event["type"] == "model_call" and event.get("role") == "executor"]
    if (not actions or len(actions) != len(calls) or len(actions) >= executor_limit
            or stop.get("attempts", {}).get("executor") != len(actions) + 1
            or any(event["type"] == "tool_error" for event in events)):
        return None
    prefix = []
    for action, call in zip(actions, calls, strict=True):
        reply = (call.get("response") or {}).get("text")
        if (call.get("status") != "complete" or call.get("error") is not None or not isinstance(reply, str)
                or action["model_event_id"] != call["event_id"] or action["event_id"] != call["event_id"] + 1
                or action.get("dispatched") is not (action.get("action") is not None)
                or not isinstance(action.get("observation"), str) or type(action.get("valid")) is not bool):
            return None
        prefix.append((reply, action))
    history = [(message["content"], messages[index + 1]) for index, message in enumerate(messages[:-1])
               if message.get("role") == "assistant"]
    if history != [(reply, {"role": "user", "content": action["observation"]}) for reply, action in prefix]:
        return None
    return initial[0]["observation"], prefix, blocked["event_id"], size


def replay_native_context_limits(run_dir, data_dir):
    """Write separate native scores for exact WebShop replays without model calls."""
    manifest = read_json(run_dir / "manifest.json")
    dataset = manifest["benchmark"]
    metadata, rows = load_test_split(data_dir)
    verification = read_json(data_dir / "verified.json")
    cap = manifest["budget"]["max_input_bytes_per_request"]
    if (manifest["schema_version"] != SCHEMA_VERSION or manifest["purpose"] != PURPOSE
            or dataset["name"] != "WebShop" or dataset["split"] != "test" or dataset["selection"] != "full_split"
            or dataset["data_version"] != UPSTREAM_REVISION or dataset["canonical_task_count"] != TEST_GOALS
            or Path(dataset["data_dir"]).resolve() != data_dir
            or dataset["catalog"] != metadata or dataset["catalog_verification"] != verification
            or type(cap) is not int or cap <= 0):
        raise ValueError("Replay requires the original full WebShop catalog and run manifest")
    tasks = {task["task_id"]: task for task in dataset["tasks"]}
    output = run_dir / "native-replay"
    if output.is_symlink():
        raise ValueError("Native replay output must stay separate from the original trial records")
    recovered = 0
    with ExitStack() as stack:
        server = None
        for trial_id, entry in manifest["trials"].items():
            if manifest["status"] == "complete" and entry["status"] != "unscored":
                continue
            source = f"trials/{trial_id}.json"
            path = run_dir / source
            if (Path(trial_id).name != trial_id or entry["trial_id"] != trial_id
                    or entry["file"] != source or manifest["records"][trial_id] != source or path.is_symlink()):
                raise ValueError(f"Unexpected WebShop trial path for {trial_id}")
            if not path.is_file():
                continue
            record = read_json(path)
            if record["status"] != "unscored":
                continue
            attempt = 1 + sum(1 for _ in (run_dir / "attempts" / trial_id).glob("attempt-*.json"))
            identity = {"run_id": manifest["run_id"], "trial_id": trial_id, "attempt": attempt,
                        "workspace_id": f"{manifest['run_id']}/{trial_id}/attempt-{attempt}",
                        **{key: entry[key] for key in ("model", "task_id", "mode")}}
            limit = entry["executor_limit"]
            evidence = context_limit_evidence(record, identity, cap, limit)
            if evidence is None:
                continue
            task = rows[entry["task_id"]]
            planned = tasks[entry["task_id"]]
            if (planned["session"] != task.session or planned["goal"] != task.observation
                    or record["goal"] != task.observation or planned["executor_limit"] != limit):
                raise ValueError(f"WebShop goal or Executor budget differs for {trial_id}")
            if server is None:
                from web_agent_site.engine import engine

                upstream = Path(engine.__file__).resolve().parents[2]
                revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
                if revision != UPSTREAM_REVISION:
                    raise ValueError(f"Expected upstream WebShop checkout {UPSTREAM_REVISION}")
                server = stack.enter_context(shared_server(data_dir))
                if (len(server.goals) != metadata["human_goals"]
                        or server.search_engine.num_docs != verification["indexed_products_verified"]):
                    raise ValueError("WebShop catalog and index differ from the original run")
            initial, prefix, blocked_id, input_bytes = evidence
            with isolated_environment(server, task, limit) as env:
                _, state = env.reset()
                if env.initial_observation != initial:
                    print(f"{trial_id}: initial observation changed; still unscored")
                    continue
                for reply, action in prefix:
                    _, state = env.step(reply)
                    expected = {key: action[key] for key in ("action", "observation", "valid")}
                    if state.finished or state.action_trace[-1] != expected:
                        print(f"{trial_id}: tool event {action['event_id']} changed; still unscored")
                        break
                else:
                    if type(state.reward) not in (int, float) or state.reward != 0 or state.success is not False:
                        print(f"{trial_id}: native episode was not an unpurchased zero; still unscored")
                        continue
                    write_json(output / f"{trial_id}.json", {
                        **identity, "source": source, "method": REPLAY_METHOD,
                        "blocked_call_event_id": blocked_id, "input_bytes": input_bytes, "max_input_bytes": cap,
                        "tool_events_replayed": len(prefix),
                        "outcome": {"reason": "prompt_budget", "reward": state.reward, "success": state.success},
                    })
                    recovered += 1
    return recovered


async def run_webshop(run_dir, data_dir, api_key, *, concurrency=CONCURRENCY, resume=False):
    metadata, rows = load_test_split(data_dir)
    verified = json.loads((data_dir / "verified.json").read_text(encoding="utf-8"))
    indexed_count = verified["indexed_products_verified"]
    if (verified["native_sessions_verified"] != TEST_GOALS
            or verified["reference_test_indices_verified"] != TEST_GOALS
            or metadata["test_goals"] != TEST_GOALS
            or verified["native_search_smoke"] is not True
            or verified["catalog_products_verified"] != metadata["products"]
            or indexed_count <= 1_000_000 or verified["native_empty_documents"] < 0
            or indexed_count + verified["native_empty_documents"] != metadata["products"]):
        raise ValueError("WebShop catalog and native verification counts do not match")
    settings = webshop_settings()
    dataset = {
        "name": "WebShop", "split": "test", "data_version": metadata["source_revision"],
        "selection": "full_split", "canonical_task_count": TEST_GOALS,
        "canonical_task_file": str(data_dir / "webshop_test_tasks.jsonl"),
        "data_dir": str(data_dir), "catalog": metadata, "catalog_verification": verified, "constraints": CONSTRAINTS,
        "runtime_packages": ["gym", "numpy", "openai", "pyserini", "PyYAML", "spacy", "en-core-web-sm"],
        "tasks": [{"task_id": task.task_id, "task": task.observation, "goal": task.observation,
                   "session": task.session, "executor_limit": settings["max_steps"]} for task in rows.values()],
    }
    with shared_server(data_dir) as server:
        if len(server.goals) != metadata["human_goals"] or server.search_engine.num_docs != indexed_count:
            raise ValueError("WebShop full catalog, index or goals do not match their prepared manifest")
        reset_test_sessions(server, rows, settings["max_steps"])
        await run_matrix(run_dir, rows, dataset, api_key, run_one=partial(run_one, server),
                         concurrency=concurrency, resume=resume)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--replay-native", action="store_true",
                        help="Verify local input-budget failures by replaying the recorded actions, with no model calls")
    args = parser.parse_args()
    if args.replay_native:
        if args.resume:
            parser.error("--replay-native cannot be combined with --resume")
        recovered = replay_native_context_limits(args.run_dir.resolve(), args.data_dir.resolve())
        print(f"Replayed {recovered} WebShop input-budget outcomes")
        return
    api_key = os.getenv("TONGJI_API_KEY")
    if not api_key:
        parser.error("Set TONGJI_API_KEY in the environment")
    try:
        asyncio.run(run_webshop(args.run_dir.resolve(), args.data_dir.resolve(), api_key,
                                concurrency=args.concurrency, resume=args.resume))
    except KeyboardInterrupt:
        parser.exit(130, "Benchmark interrupted.\n")
    except Exception as error:
        parser.exit(1, f"Benchmark stopped ({type(error).__name__}). Check the output directory for evidence.\n")


if __name__ == "__main__":
    main()
