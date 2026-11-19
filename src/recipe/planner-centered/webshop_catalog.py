"""Build a disk-backed catalog for the pinned upstream WebShop text simulator."""

import argparse
import contextlib
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from toolkit.utils.files import write_json, write_jsonl


UPSTREAM_REVISION = "64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd"
MIRROR_SOURCE = "https://huggingface.co/datasets/YWZBrandon/webshop-data/tree/ce990ff"
MIRROR_PRODUCT_BYTES = 5_479_720_229
MIRROR_ATTRIBUTE_BYTES = 186_295_270
CATALOG_SEED = 233
TEST_GOALS = 500
BATCH_SIZE = 8_192


def index_document(product):
    """Use the field order of upstream search_engine/convert_product_file_format.py."""
    options = ", and ".join(f"{name}: {', '.join(values)}" for name, values in product["options"].items())
    contents = " ".join((product["Title"], product["Description"], product["BulletPoints"][0], options))
    return {"id": product["asin"], "contents": contents.lower(), "product": product}


def goal_key(instruction):
    """The upstream baseline removes injected price and quotes before matching goal IDs."""
    return instruction.lower().replace('"', "").replace("'", "").split(", and price lower than", 1)[0].strip()


def prepare_catalog(output, *, catalog, attributes, human_annotations, official_goals=None, require_full=True):
    from web_agent_site.engine import engine
    from web_agent_site.engine.goal import get_human_goals

    output, catalog, attributes, human_annotations = (
        Path(path).resolve() for path in (output, catalog, attributes, human_annotations)
    )
    if require_full:
        if (catalog.stat().st_size, attributes.stat().st_size) != (MIRROR_PRODUCT_BYTES, MIRROR_ATTRIBUTE_BYTES):
            raise ValueError("Expected the pinned mirror's complete product catalog and attributes")
        if official_goals is None:
            raise ValueError("Pinned upstream human_goals.json is required for validating test indices")
    upstream = Path(engine.__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError(f"Expected upstream WebShop checkout {UPSTREAM_REVISION}")

    output.mkdir(parents=True, exist_ok=False)
    documents = output / "documents"
    documents.mkdir()
    with attributes.open("rb") as stream:
        attribute_rows = dict(ijson.kvitems(stream, "", use_float=True))
    cached_data = {attributes: attribute_rows, human_annotations: json.loads(human_annotations.read_text(encoding="utf-8"))}
    cached_reader = SimpleNamespace(load=lambda stream: cached_data[Path(stream.name)])
    seen, human_items, human_prices = set(), [], {}
    random_state = random.getstate()
    try:
        random.seed(CATALOG_SEED)
        with (catalog.open("rb") as catalog_stream,
              (documents / "products.jsonl").open("w", encoding="utf-8") as index_rows,
              contextlib.closing(sqlite3.connect(output / "products.sqlite3")) as database):
            database.execute("CREATE TABLE products (asin TEXT NOT NULL, info TEXT NOT NULL, price REAL NOT NULL)")
            products = ijson.items(catalog_stream, "item", use_float=True)
            while chunk := list(islice(products, BATCH_SIZE)):
                unique = []
                for product in chunk:
                    asin = product["asin"]
                    if asin == "nan" or len(asin) > 10 or asin in seen:
                        continue
                    seen.add(asin)
                    unique.append(product)
                cached_data[catalog] = unique
                # Keep transformations and price draws in the upstream loader while bounding each JSON read.
                with (patch.object(engine, "json", cached_reader),
                      patch.object(engine, "DEFAULT_ATTR_PATH", attributes),
                      patch.object(engine, "HUMAN_ATTR_PATH", human_annotations),
                      patch.object(engine, "tqdm", lambda values, **_: values)):
                    normalized, _, prices, _ = engine.load_products(catalog, human_goals=True)
                database.executemany("INSERT INTO products VALUES (?, ?, ?)", (
                    (product["asin"], json.dumps(product, ensure_ascii=False), prices[product["asin"]])
                    for product in normalized
                ))
                database.commit()
                for product in normalized:
                    index_rows.write(json.dumps(index_document(product)) + "\n")
                    if "instructions" in product:
                        human_items.append(product)
                        human_prices[product["asin"]] = prices[product["asin"]]
            database.execute("CREATE UNIQUE INDEX products_asin ON products(asin)")
            database.commit()
        goals = get_human_goals(human_items, human_prices)
    finally:
        random.setstate(random_state)
    shuffled_goals = list(goals)
    random.Random(CATALOG_SEED).shuffle(shuffled_goals)
    if require_full and (len(seen) < 1_000_000 or len(goals) < TEST_GOALS):
        raise ValueError("Prepared artifacts do not contain the full WebShop catalog and test cases")
    if official_goals is not None:
        reference = json.loads(Path(official_goals).read_text(encoding="utf-8"))
        actual = [goal_key(goal["instruction_text"]) for goal in shuffled_goals[:TEST_GOALS]]
        if len(actual) != TEST_GOALS or actual != [goal_key(goal) for goal in reference[:TEST_GOALS]]:
            raise ValueError("Generated goal indices do not match the published WebShop test indices")
    write_json(output / "goals.json", goals)
    write_jsonl(output / "webshop_test_tasks.jsonl", (
        {"id": str(index), "session": index, "task": f"Instruction: {goal['instruction_text']}"}
        for index, goal in enumerate(shuffled_goals[:TEST_GOALS])
    ))
    write_json(output / "catalog.json", {
        "source_revision": revision,
        "source": MIRROR_SOURCE if require_full else "local equivalence fixture",
        "full_catalog": require_full,
        "verified_official_test_ids": official_goals is not None,
        "catalog_seed": CATALOG_SEED,
        "products": len(seen),
        "human_goals": len(goals),
        "test_goals": min(TEST_GOALS, len(goals)),
        "catalog_bytes": catalog.stat().st_size,
        "attributes_bytes": attributes.stat().st_size,
    })


def build_index(output):
    with tempfile.TemporaryDirectory(prefix=".index-", dir=output) as directory:
        index = Path(directory) / "indexes"
        subprocess.run([
            sys.executable, "-m", "pyserini.index.lucene", "--collection", "JsonCollection",
            "--input", str(output / "documents"), "--index", str(index),
            "--generator", "DefaultLuceneDocumentGenerator", "--threads", "1",
            "--storePositions", "--storeDocvectors", "--storeRaw",
        ], check=True)
        index.rename(output / "indexes")


class CatalogLookup(Mapping):
    """Give upstream search and scoring lookup access without loading every product."""

    def __init__(self, database, size, *, price=False):
        self.database, self.size, self.price = database, size, price

    def __getitem__(self, asin):
        row = self.database.execute("SELECT info, price FROM products WHERE asin = ?", (asin,)).fetchone()
        if row is None:
            raise KeyError(asin)
        return row[1] if self.price else json.loads(row[0])

    def __contains__(self, asin):
        return self.database.execute("SELECT 1 FROM products WHERE asin = ?", (asin,)).fetchone() is not None

    def __iter__(self):
        return (asin for asin, in self.database.execute("SELECT asin FROM products"))

    def __len__(self):
        return self.size


@contextlib.contextmanager
def shared_server(directory):
    from pyserini.search.lucene import LuceneSearcher
    from web_agent_site.envs import web_agent_text_env

    directory = Path(directory).resolve(strict=True)
    metadata = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    goals = json.loads((directory / "goals.json").read_text(encoding="utf-8"))
    uri = (directory / "products.sqlite3").as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as database:
        products = CatalogLookup(database, metadata["products"])
        prices = CatalogLookup(database, metadata["products"], price=True)
        with contextlib.closing(LuceneSearcher(str(directory / "indexes"))) as search:
            state = random.getstate()
            try:
                with (patch.object(web_agent_text_env, "load_products", return_value=([], products, prices, {})),
                      patch.object(web_agent_text_env, "get_goals", return_value=goals),
                      patch.object(web_agent_text_env, "init_search_engine", return_value=search)):
                    server = web_agent_text_env.SimServer("http://127.0.0.1:3000", "", human_goals=True)
            finally:
                random.setstate(state)
            yield server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--attributes", required=True, type=Path)
    parser.add_argument("--human-annotations", required=True, type=Path)
    parser.add_argument("--official-goals", required=True, type=Path)
    args = parser.parse_args()
    prepare_catalog(args.data_dir, catalog=args.catalog, attributes=args.attributes,
                    human_annotations=args.human_annotations, official_goals=args.official_goals)
    build_index(args.data_dir)
    from webshop_benchmark import verify_prepared

    verify_prepared(args.data_dir, args.official_goals)


if __name__ == "__main__":
    main()
