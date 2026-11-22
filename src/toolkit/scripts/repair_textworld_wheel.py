"""Repair the misplaced platform tag in the upstream TextWorld 1.7.0 wheel."""

import argparse
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

from wheel.wheelfile import WheelFile


def repair(source, output_dir):
    metadata = "textworld-1.7.0.dist-info/WHEEL"
    record = "textworld-1.7.0.dist-info/RECORD"
    target = output_dir / source.name
    if target.resolve() == source.resolve():
        raise ValueError("Use a separate output directory to preserve the source wheel")
    output_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as original:
        old = original.read(metadata)
        new = old.replace(b"Root-Is-Purelib: false\n\nTag:", b"Root-Is-Purelib: false\nTag:", 1)
        if old == new or not Parser().parsestr(new.decode()).get_all("Tag"):
            raise ValueError("Expected the upstream TextWorld 1.7.0 misplaced Tag header")
        with WheelFile(target, "w") as fixed:
            for entry in original.infolist():
                if entry.filename != record:
                    fixed.writestr(entry, new if entry.filename == metadata else original.read(entry.filename))
    # WheelFile regenerates RECORD. All package code and data must remain identical.
    with ZipFile(source) as original, ZipFile(target) as fixed:
        for name in original.namelist():
            if name not in (metadata, record) and original.read(name) != fixed.read(name):
                raise ValueError(f"Package content changed: {name}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(repair(args.wheel, args.output_dir))
