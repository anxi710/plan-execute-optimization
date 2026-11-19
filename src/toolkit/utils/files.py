"""Read YAML and JSON, and write files atomically."""

import gzip
import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


def read_json(path):
    path = Path(path)
    if path.suffixes[-2:] == [".json", ".gz"]:
        with gzip.open(path, mode="rt", encoding="utf-8") as stream:
            return json.load(stream)
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_yaml_mapping(path):
    import yaml

    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def write_json(path, value):
    path = Path(path)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.suffixes[-2:] == [".json", ".gz"]:
        with _atomic_output(path, mode="wb") as stream:
            stream.write(gzip.compress(text.encode("utf-8"), compresslevel=1, mtime=0))
    else:
        write_text_atomic(path, text)


def write_jsonl(path, rows):
    write_text_atomic(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def write_text_atomic(path, text):
    with _atomic_output(Path(path), mode="w", encoding="utf-8") as stream:
        stream.write(text)


@contextmanager
def _atomic_output(path, **options):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False, **options) as stream:
        temporary = Path(stream.name)
        try:
            yield stream
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
