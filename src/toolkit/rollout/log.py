"""Record execution events and persist rollout checkpoints."""

import time
from datetime import datetime, timezone

from ..utils.files import write_json


class EventLog:
    """Keep execution events independent of their storage format."""

    def __init__(self, events=None, *, context=dict, save=None):
        self.events = [] if events is None else events
        self._context = context
        self._save = save

    def emit(self, kind, **fields):
        event = {"event_id": len(self.events) + 1, "type": kind,
                 "timestamp": datetime.now(timezone.utc).isoformat(), **self._context(), **fields}
        self.events.append(event)
        self.flush()
        return event

    def flush(self):
        if self._save is not None:
            self._save()


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
