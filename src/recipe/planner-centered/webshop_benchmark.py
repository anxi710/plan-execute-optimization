"""Run the matched frameworks on the complete 500-goal WebShop test split."""

import argparse
import asyncio
import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from uuid import uuid4

from benchmark import CONCURRENCY, requested_protocol, run_matrix
from run import CONFIG_PATH, load_context_window, load_model_settings, model_call
from toolkit.envs.webshop_env import WebShopEnv, webshop_settings
from toolkit.frameworks import FRAMEWORK_PROTOCOL, run_framework
from toolkit.tasks.webshop import WebShopTask
from toolkit.utils.files import read_yaml_mapping, write_json
from webshop_catalog import TEST_GOALS, UPSTREAM_REVISION, goal_key, shared_server



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
        adapter = WebShopBenchmarkEnv(task, env, **{**webshop_settings(), "max_steps": executor_limit})
        yield adapter
    finally:
        # The upstream constructor creates a random initial session before the task-specific reset.
        server.user_sessions.pop(startup_session, None)
        server.user_sessions.pop(env.session, None)
        env.close()


async def run_one(server, task, client, *, mode, workspace_id, model_settings, context_window,
                  save, executor_limit, protocol_version=FRAMEWORK_PROTOCOL):
    with isolated_environment(server, task, executor_limit) as env:
        return await run_framework(
            mode=mode, env=env, goal=task.observation,
            planner=model_call(client, "planner", model_settings=model_settings) if mode != "eo" else None,
            executor=model_call(client, "executor", model_settings=model_settings),
            workspace_id=workspace_id, executor_limit=executor_limit, context_window=context_window,
            save=save, benchmark="webshop",
            protocol_version=protocol_version,
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



async def run_webshop(run_dir, data_dir, api_key, *, concurrency=CONCURRENCY, resume=False,
                       model_settings=None, model_order=None, context_window=None):
    protocol = requested_protocol(run_dir, resume)
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
        "data_dir": str(data_dir), "catalog": metadata, "catalog_verification": verified,
        "runtime_packages": ["gym", "numpy", "openai", "pyserini", "PyYAML", "spacy", "en-core-web-sm"],
        "tasks": [{"task_id": task.task_id, "task": task.observation, "goal": task.observation,
                   "session": task.session, "executor_limit": settings["max_steps"]} for task in rows.values()],
    }
    with shared_server(data_dir) as server:
        if len(server.goals) != metadata["human_goals"] or server.search_engine.num_docs != indexed_count:
            raise ValueError("WebShop full catalog, index or goals do not match their prepared manifest")
        reset_test_sessions(server, rows, settings["max_steps"])
        await run_matrix(run_dir, rows, dataset, api_key, run_one=partial(run_one, server),
                         concurrency=concurrency, resume=resume, model_order=model_order,
                         protocol_version=protocol, model_settings=model_settings, context_window=context_window)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    model_settings, api_key = load_model_settings(args.config)
    if not all(api_key.values()):
        parser.error("Set api_key in the recipe config or OPENAI_API_KEY in the environment")
    try:
        asyncio.run(run_webshop(args.run_dir.resolve(), args.data_dir.resolve(), api_key,
                                concurrency=args.concurrency, resume=args.resume,
                                model_settings=model_settings, model_order=read_yaml_mapping(args.config).get("models"),
                                context_window=load_context_window(args.config)))
    except KeyboardInterrupt:
        parser.exit(130, "Benchmark interrupted.\n")
    except Exception as error:
        parser.exit(1, f"Benchmark stopped ({type(error).__name__}). Check the output directory for evidence.\n")


if __name__ == "__main__":
    main()
