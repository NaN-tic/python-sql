#!/usr/bin/env python3
"""Produce a PyPI-compatible manylinux wheel."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=ROOT)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    shutil.rmtree(DIST / "repaired", ignore_errors=True)
    for wheel in DIST.glob("*.whl"):
        wheel.unlink()

    run(sys.executable, "tools/build.py")
    run(sys.executable, "-m", "hatchling", "build", "-t", "wheel")

    wheel, = DIST.glob("*.whl")
    run(
        sys.executable,
        "-m",
        "wheel",
        "tags",
        "--platform-tag",
        "linux_x86_64",
        "--remove",
        str(wheel),
    )

    wheel, = DIST.glob("*.whl")
    repaired = DIST / "repaired"
    run(
        "auditwheel",
        "repair",
        "--plat",
        "manylinux_2_35_x86_64",
        "--wheel-dir",
        str(repaired),
        str(wheel),
    )
    wheel.unlink()
    repaired_wheel, = repaired.glob("*.whl")
    shutil.move(str(repaired_wheel), DIST)
    repaired.rmdir()


if __name__ == "__main__":
    main()
