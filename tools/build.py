#!/usr/bin/env python3
"""Compile the native core into `sql/_core.so`.

The bundled `mojo.importer` compiles a single file without an include path and
is pinned to whatever compiler sits in the active virtualenv.  This project
needs the multi-file `sql/sqlcore` package, so the extension is built ahead of
time and imported like any other C extension.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sql" / "_core.mojo"
TARGET = ROOT / "sql" / "_core.so"
DEFAULT_TOOLCHAIN = Path.home() / "Documents" / "repos" / "mojo" / ".mojo"


def toolchain_root(prefix: Path) -> Path:
    matches = sorted(prefix.glob("lib/python*/site-packages/modular"))
    if not matches:
        raise SystemExit(f"no Mojo toolchain under {prefix}")
    return matches[0]


def build(prefix: Path, source: Path, target: Path) -> int:
    root = toolchain_root(prefix)
    mojo = root / "bin" / "mojo"
    if not mojo.exists():
        raise SystemExit(f"missing mojo compiler at {mojo}")
    environment = dict(os.environ)
    environment.update(
        MODULAR_MAX_PACKAGE_ROOT=str(root),
        MODULAR_MOJO_MAX_PACKAGE_ROOT=str(root),
        MODULAR_MOJO_MAX_DRIVER_PATH=str(mojo),
        MODULAR_MOJO_MAX_IMPORT_PATH=str(root / "lib" / "mojo"),
    )
    completed = subprocess.run(
        [
            str(mojo),
            "build",
            str(source),
            "--emit",
            "shared-lib",
            "-o",
            str(target),
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    interesting = [
        line
        for line in output.splitlines()
        if ": error:" in line or ": warning:" in line
    ]
    if interesting:
        print("\n".join(interesting), file=sys.stderr)
    if completed.returncode != 0:
        print(output, file=sys.stderr)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--toolchain",
        type=Path,
        default=Path(os.environ.get("PYTHON_SQL_MOJO_TOOLCHAIN", DEFAULT_TOOLCHAIN)),
        help="virtualenv holding the Mojo compiler",
    )
    arguments = parser.parse_args()
    return build(arguments.toolchain, SOURCE, TARGET)


if __name__ == "__main__":
    raise SystemExit(main())
