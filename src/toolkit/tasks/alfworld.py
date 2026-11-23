"""ALFWorld task selection and isolated game slots."""

import os
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from copy import copy
from dataclasses import dataclass
from pathlib import Path

from ..utils.files import read_jsonl, write_jsonl
from .rows import load_task_rows, task_rows_by_id


SPLITS = {"train": "train", "dev": "eval_in_distribution", "test": "eval_out_of_distribution"}


def load_alfworld_rows(data_dir, split, **selection):
    """Select ALFWorld tasks from the canonical split and optional gamefile map."""
    return load_task_rows(data_dir, "alfworld", split, **selection)


@dataclass
class AlfWorldTask:
    task_id: int | str
    env: object
    observation: str
    gamefile: str
    plan: str | None = None
    admissible_commands: list[str] | None = None


def _source(path, split):
    import yaml
    from alfworld.agents.environment.alfred_tw_env import AlfredTWEnv

    os.environ["ALFWORLD_DATA"] = str(path)
    config = yaml.safe_load((path / "base_config.yaml").read_text(encoding="utf-8"))
    if config["env"]["type"] != "AlfredTWEnv":
        raise ValueError("Only AlfredTWEnv is supported")
    if split == "train" and config["env"].get("domain_randomization"):
        raise ValueError("Disable ALFWorld domain_randomization for matched plan evaluation")
    return AlfredTWEnv(config, train_eval=SPLITS[split])


def _resolve_gamefile(path, split, task_id, gamefile, available):
    if not isinstance(gamefile, str) or not gamefile:
        raise ValueError(f"Invalid ALFWorld gamefile for task {task_id}")
    relative = Path(gamefile)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid ALFWorld gamefile for task {task_id}")
    resolved = (path / relative).resolve()
    if resolved not in available:
        raise ValueError(f"ALFWorld gamefile for task {task_id} is not in the {split} split: {relative}")
    return resolved


def _game_observation(observations):
    return "\n".join(observations[0].split("\n\n")[1:])


def _normalize(text):
    return " ".join(text.split())


@contextmanager
def _open_env(source):
    import textworld.gym

    registry = textworld.gym.registry
    before = set(registry)
    try:
        env = source.init_env(batch_size=1)
    finally:
        # The live environment has its own reference, so the registration can go.
        for env_id in set(registry) - before:
            registry.pop(env_id, None)
    try:
        yield env
    finally:
        env.close()


class AlfWorldRolloutSlot:
    """Reload a verified gamefile before every rollout on this backend."""

    def __init__(self, env, rows, gamefiles):
        self.env = env
        self.rows = rows
        self.gamefiles = gamefiles
        if (not hasattr(env, "batch_env")
                or not callable(getattr(env.batch_env, "load", None))
                or not callable(getattr(env.batch_env, "reset", None))):
            raise ValueError("ALFWorld concurrent sampling requires TextWorld's batch load/reset interface")

    def load_task(self, row):
        task_id = str(row["id"])
        canonical = self.rows[task_id]
        gamefile = self.gamefiles[task_id]
        # The outer Gym reset advances its iterator instead of reloading this game.
        self.env.batch_env.load([gamefile])
        self.env.last_commands = [None]
        self.env.obs, info = self.env.batch_env.reset()
        observation = _game_observation(self.env.obs)
        returned = info["extra.gamefile"][0]
        if Path(returned).resolve() != Path(gamefile).resolve():
            raise ValueError(f"ALFWorld returned the wrong gamefile for task {task_id}")
        if _normalize(observation) != _normalize(canonical["task"]):
            raise ValueError(f"ALFWorld task text changed for task {task_id}")
        return AlfWorldTask(
            canonical["id"], self.env, observation, returned, canonical.get("plan"),
            info["admissible_commands"][0].copy(),
        )


class AlfWorldRolloutPool:
    """Validate gamefile assignments and create independent rollout slots."""

    def __init__(self, path, split, rows):
        if split not in SPLITS:
            raise ValueError(f"Unsupported split: {split}")
        self.rows = task_rows_by_id(rows)
        if not self.rows or any(not row.get("gamefile") for row in self.rows.values()):
            raise ValueError("ALFWorld trajectory sampling requires gamefile metadata for every selected task")
        path = Path(path).resolve()
        self.source = _source(path, split)
        available = {Path(gamefile).resolve(): gamefile for gamefile in self.source.game_files}
        self.gamefiles = {}
        self._slot_stack = None
        self._idle_slots = []
        assigned = set()
        for task_id, row in self.rows.items():
            resolved = _resolve_gamefile(path, split, task_id, row["gamefile"], available)
            if resolved in assigned:
                raise ValueError(f"ALFWorld gamefile is assigned to multiple tasks: {row['gamefile']}")
            assigned.add(resolved)
            self.gamefiles[task_id] = available[resolved]

    @contextmanager
    def _new_slot(self):
        source = copy(self.source)
        source.game_files = list(self.gamefiles.values())
        source.num_games = len(source.game_files)
        with _open_env(source) as env:
            yield AlfWorldRolloutSlot(env, self.rows, self.gamefiles)

    @contextmanager
    def reuse_slots(self):
        """Reuse returned backends and close them together when the scope ends."""
        if self._slot_stack is not None:
            raise RuntimeError("ALFWorld slot reuse is already active")
        with ExitStack() as stack:
            self._slot_stack = stack
            try:
                yield self
            finally:
                self._slot_stack = None
                self._idle_slots.clear()

    @contextmanager
    def open_slot(self):
        """Borrow an exclusive slot, reusing it only inside reuse_slots()."""
        if self._slot_stack is None:
            with self._new_slot() as slot:
                yield slot
            return
        slot = (self._idle_slots.pop() if self._idle_slots
                else self._slot_stack.enter_context(self._new_slot()))
        try:
            yield slot
        finally:
            self._idle_slots.append(slot)


def prepare_gamefile_map(path, split, output_path):
    """Scan a split once and persist only ID-to-game matches that are unambiguous."""
    if split not in SPLITS:
        raise ValueError(f"Unsupported split: {split}")
    path = Path(path).resolve()
    canonical_path = path / f"alfworld_{split}_tasks.jsonl"
    output_path = Path(output_path)
    if output_path.resolve() == canonical_path.resolve():
        raise ValueError("The gamefile map must not overwrite the canonical task file")
    canonical = task_rows_by_id(read_jsonl(canonical_path))
    existing = task_rows_by_id(read_jsonl(output_path)) if output_path.exists() else {}
    for task_id, row in existing.items():
        if task_id not in canonical or row["task"] != canonical[task_id]["task"]:
            raise ValueError(f"Existing gamefile map task {task_id} differs from the {split} task file")

    source = _source(path, split)
    available = {Path(gamefile).resolve(): gamefile for gamefile in source.game_files}
    candidates = defaultdict(list)
    seen = set()
    with _open_env(source) as env:
        for _ in range(len(source.game_files)):
            observations, info = env.reset()
            observation = _game_observation(observations)
            gamefile = Path(info["extra.gamefile"][0]).resolve()
            if gamefile not in available or gamefile in seen:
                raise ValueError(f"ALFWorld returned an unexpected or repeated gamefile: {gamefile}")
            seen.add(gamefile)
            relative = gamefile.relative_to(path).as_posix()
            candidates[_normalize(observation)].append(relative)
    if seen != set(available):
        raise ValueError("ALFWorld did not return every gamefile in the selected split")

    text_counts = Counter(_normalize(row["task"]) for row in canonical.values())
    used = set()
    rows = []
    unresolved = 0
    missing = 0
    for task_id, row in canonical.items():
        text = _normalize(row["task"])
        options = sorted(candidates.get(text, []))
        prior = existing.get(task_id, {})
        assigned = [_resolve_gamefile(path, split, task_id, source_row["gamefile"], available)
                    for source_row in (row, prior) if "gamefile" in source_row]
        if len(set(assigned)) > 1:
            raise ValueError(f"Conflicting ALFWorld gamefiles for task {task_id}")
        gamefile = assigned[0].relative_to(path).as_posix() if assigned else None
        if gamefile is not None:
            if gamefile not in options:
                raise ValueError(f"ALFWorld task text changed for task {task_id}")
        elif text_counts[text] == 1 and len(options) == 1:
            gamefile = options[0]
        result = dict(row)
        if gamefile:
            if gamefile in used:
                raise ValueError(f"ALFWorld gamefile is assigned to multiple tasks: {gamefile}")
            used.add(gamefile)
            result["gamefile"] = gamefile
        else:
            unresolved += 1
            if not options:
                missing += 1
            result.pop("gamefile", None)
            result["candidates"] = options
        rows.append(result)
    write_jsonl(output_path, rows)
    return {"total": len(rows), "ready": len(rows) - unresolved,
            "unresolved": unresolved, "missing": missing}
