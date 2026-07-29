#!/usr/bin/env python3
"""Build sql._core and bundle its Mojo runtime libraries."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "sql"
SOURCE = PACKAGE / "_core.mojo"
EXTENSION = PACKAGE / "_core.so"
RUNTIME = PACKAGE / "_runtime"
RUNTIME_LIBRARIES = (
    "libKGENCompilerRTShared.so",
    "libMSupportGlobals.so",
    "libAsyncRTRuntimeGlobals.so",
    "libNVPTX.so",
    "libAsyncRTMojoBindings.so",
)


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> None:
    mojo = shutil.which("mojo")
    patchelf = shutil.which("patchelf")
    if not mojo or not patchelf:
        raise SystemExit("run this script through `pixi run build`")

    prefix = Path(os.environ.get("CONDA_PREFIX", Path(mojo).resolve().parents[1]))
    runtime_source = prefix / "lib"
    if not runtime_source.is_dir():
        raise SystemExit(f"Mojo runtime directory not found: {runtime_source}")

    RUNTIME.mkdir(exist_ok=True)
    EXTENSION.unlink(missing_ok=True)
    run(mojo, "build", str(SOURCE), "--emit", "shared-lib", "-o", str(EXTENSION))
    run(patchelf, "--set-rpath", "$ORIGIN/_runtime", str(EXTENSION))

    for library in RUNTIME_LIBRARIES:
        source = runtime_source / library
        destination = RUNTIME / library
        if not source.is_file():
            raise SystemExit(f"required Mojo runtime library not found: {source}")
        shutil.copy2(source, destination)
        run(patchelf, "--set-rpath", "$ORIGIN", str(destination))


if __name__ == "__main__":
    main()
