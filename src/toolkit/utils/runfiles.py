"""Lock run directories and retain the settings used to create their results."""

import json
from contextlib import contextmanager
from pathlib import Path

from .files import write_json


@contextmanager
def exclusive_run_lock(path):
    """Hold an exclusive nonblocking lock on a caller-chosen file."""
    import fcntl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def save_settings(path, settings, *, equivalent=None):
    """Record settings once and verify them before continuing an existing run."""
    path = Path(path)
    if not path.exists():
        write_json(path, settings)
        return
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved != settings and (equivalent is None or not equivalent(saved, settings)):
        raise ValueError(f"Resume settings differ at {path}")
