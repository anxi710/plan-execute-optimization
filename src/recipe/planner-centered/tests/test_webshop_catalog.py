import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(os.environ.get("TOOLKIT_WEBSHOP_SMOKE"), "requires pinned upstream 1k WebShop fixture")
class WebShopCatalogTest(unittest.TestCase):
    def test_disk_catalog_matches_eager_catalog_and_isolates_sessions(self):
        from toolkit.envs.webshop_env import WebShopEnv, open_webshop_backend, webshop_settings
        from toolkit.tasks.webshop import WebShopTask
        from web_agent_site.utils import DEFAULT_ATTR_PATH, DEFAULT_FILE_PATH, HUMAN_ATTR_PATH
        from webshop_benchmark import isolated_environment
        from webshop_catalog import CATALOG_SEED, build_index, prepare_catalog, shared_server

        repo = Path(DEFAULT_FILE_PATH).resolve().parent.parent
        config = {"environments": {"webshop": {"num_products": 1000, "human_goals": True,
                                               "catalog_seed": CATALOG_SEED, "catalog_path": DEFAULT_FILE_PATH}}}
        random_state = random.getstate()
        self.addCleanup(random.setstate, random_state)
        with tempfile.TemporaryDirectory() as tmp, open_webshop_backend(config) as eager:
            directory = Path(tmp) / "prepared"
            with patch("webshop_catalog.BATCH_SIZE", 127):
                prepare_catalog(directory, catalog=DEFAULT_FILE_PATH, attributes=DEFAULT_ATTR_PATH,
                                human_annotations=HUMAN_ATTR_PATH, require_full=False)
            docs = (directory / "documents/products.jsonl").read_text(encoding="utf-8").splitlines()
            reference = (repo / "search_engine/resources_1k/documents.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(docs), 1000)
            self.assertEqual(list(map(json.loads, docs)), list(map(json.loads, reference)))
            build_index(directory)
            with shared_server(directory) as server:
                self.assertEqual(eager.server.goals, server.goals)
                self.assertEqual(server.search_engine.num_docs, 1000)
                task_index = 3
                goal = eager.server.goals[task_index]
                eager.reset(session=task_index)
                task = WebShopTask("fixture", task_index, eager.get_instruction_text())
                env = WebShopEnv(task, eager, **webshop_settings())
                start, _ = env.reset()
                search = f"search[{goal['name']}]"
                web_result, _ = env.step(f"Action: {search}")
                target = goal["asin"].lower()
                self.assertIn(target, env.available["clickables"])
                actions = [f"click[{target}]", *(f"click[{choice}]" for choice in goal["goal_options"]), "click[buy now]"]
                expected = []
                for action in actions:
                    observation, state = env.step(f"Action: {action}")
                    expected.append((observation, state.reward, state.finished, state.success))
                self.assertEqual(expected[-1][1:], (1.0, True, True))

                with (isolated_environment(server, task, 15) as first,
                      isolated_environment(server, task, 15) as second):
                    self.assertEqual(first.reset()[0], start)
                    self.assertEqual(second.reset()[0], start)
                    self.assertNotEqual(first.env.session, second.env.session)
                    for adapter in (first, second):
                        self.assertEqual(adapter.step(f"Action: {search}")[0], web_result)
                    for action, (observation, reward, done, success) in zip(actions, expected):
                        for adapter in (first, second):
                            result, state = adapter.step(f"Action: {action}")
                            self.assertEqual((state.reward, state.finished, state.success), (reward, done, success))
                            self.assertEqual(result, "Observation: The purchase ended the WebShop session." if done else observation)
                self.assertEqual(server.user_sessions, {})


if __name__ == "__main__":
    unittest.main()
