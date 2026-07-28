#!/usr/bin/env python3
"""Run the upstream python-sql test suite against this package.

The reference checkout is the parity oracle: the same tests must pass with
`sql` resolving to the Mojo backed implementation.  Nothing is vendored, so the
suite cannot drift from upstream.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT.parent / "python-sql" / "sql" / "tests"


def load(tests_dir: Path, pattern: str) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for path in sorted(tests_dir.glob("test_*.py")):
        if pattern not in path.name:
            continue
        name = "upstream_" + path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--pattern", default="")
    parser.add_argument("--verbosity", type=int, default=1)
    arguments = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    suite = load(arguments.reference, arguments.pattern)
    result = unittest.TextTestRunner(verbosity=arguments.verbosity).run(suite)
    print(
        f"TOTAL {result.testsRun} "
        f"FAIL {len(result.failures)} ERR {len(result.errors)}"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
