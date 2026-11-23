import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from toolkit.tasks import alfworld


class AlfWorldSlotReuseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name)
        source = SimpleNamespace(game_files=[str(path / "game")])
        source_patch = patch.object(alfworld, "_source", return_value=source)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.created = []
        self.closed = []

        @contextmanager
        def open_env(_source):
            env = SimpleNamespace(batch_env=SimpleNamespace(load=Mock(), reset=Mock()))
            self.created.append(env)
            try:
                yield env
            finally:
                self.closed.append(env)

        env_patch = patch.object(alfworld, "_open_env", side_effect=open_env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.pool = alfworld.AlfWorldRolloutPool(
            path, "test", [{"id": 1, "task": "Goal", "gamefile": "game"}],
        )

    def test_sequential_leases_reuse_one_backend(self):
        with self.pool.reuse_slots():
            with self.pool.open_slot() as first:
                pass
            self.assertEqual(self.closed, [])
            for _ in range(20):
                with self.pool.open_slot() as current:
                    self.assertIs(current, first)
            self.assertEqual(len(self.created), 1)
            self.assertEqual(self.closed, [])
        self.assertEqual(self.closed, self.created)

    def test_overlapping_leases_are_exclusive(self):
        with self.pool.reuse_slots():
            with self.pool.open_slot() as first:
                with self.pool.open_slot() as second:
                    self.assertIsNot(second, first)
                    self.assertIsNot(second.env, first.env)
                with self.pool.open_slot() as next_lease:
                    self.assertIs(next_lease, second)
                    self.assertIsNot(next_lease, first)
                self.assertEqual(self.closed, [])
            self.assertEqual(len(self.created), 2)
        self.assertCountEqual(self.closed, self.created)

    def test_exception_closes_backends_and_a_new_scope_starts_fresh(self):
        with self.assertRaisesRegex(RuntimeError, "task failed"):
            with self.pool.reuse_slots():
                with self.pool.open_slot() as first:
                    with self.pool.open_slot():
                        raise RuntimeError("task failed")
        self.assertCountEqual(self.closed, self.created)
        with self.pool.reuse_slots():
            with self.pool.open_slot() as current:
                self.assertIsNot(current, first)
        self.assertEqual(len(self.created), 3)
        self.assertCountEqual(self.closed, self.created)

    def test_unscoped_leases_still_close_immediately(self):
        with self.pool.open_slot() as first:
            self.assertEqual(self.closed, [])
        self.assertEqual(len(self.closed), 1)
        with self.pool.open_slot() as second:
            self.assertIsNot(second, first)
        self.assertEqual(self.closed, self.created)
