"""Persist one rollout's checkpoints and final state."""

import time

from ..utils.files import write_json


class JsonRolloutLog:
    """Write checkpoints and the final state to one trajectory file."""

    def __init__(self, path, metadata, *, usage_metadata):
        self._path = path
        self._metadata = dict(metadata)
        self._usage_metadata = usage_metadata
        self._started = time.monotonic()

    def save(self, state, *, provisional=False):
        data = state.to_dict()
        data[-1].update(self._metadata)
        data[-1].update(self._usage_metadata())
        data[-1]["elapsed_seconds"] = round(time.monotonic() - self._started, 3)
        if provisional:
            data[-1]["incomplete"] = True
        write_json(self._path, data)
