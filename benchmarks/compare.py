from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON_SQL_ROOT = Path(
    os.environ.get(
        "PYTHON_SQL_UPSTREAM",
        PROJECT_ROOT.parent / "python-sql-upstream",
    )
)
_IMPLEMENTATION = os.environ.get("PYTHON_SQL_BENCHMARK_IMPLEMENTATION")

if _IMPLEMENTATION == "python_sql":
    from sql import Table as PythonTable
    from sql.aggregate import Count

    MojoTable = None
elif _IMPLEMENTATION == "mojo_sql":
    from sql.aggregate import Count
    from sql import Table as MojoTable

    PythonTable = None
else:
    PythonTable = None
    MojoTable = None
    Count = None


def _current_rss_bytes():
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
    except (FileNotFoundError, IndexError, ValueError):
        return 0
    return pages * resource.getpagesize()


def _process_snapshot():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss_bytes = _current_rss_bytes()
    allocated_blocks = getattr(sys, "getallocatedblocks", lambda: 0)()
    return {
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "rss_bytes": rss_bytes,
        "peak_rss_bytes": max(usage.ru_maxrss * 1024, rss_bytes),
        "allocated_blocks": allocated_blocks,
    }


def _with_process_stats(report, before, after, wall_seconds):
    user_cpu_seconds = after["user_cpu_seconds"] - before["user_cpu_seconds"]
    system_cpu_seconds = (
        after["system_cpu_seconds"] - before["system_cpu_seconds"]
    )
    cpu_seconds = user_cpu_seconds + system_cpu_seconds
    report["phase_wall_seconds"] = wall_seconds
    report["process_user_cpu_seconds"] = user_cpu_seconds
    report["process_system_cpu_seconds"] = system_cpu_seconds
    report["process_cpu_seconds"] = cpu_seconds
    report["process_cpu_percent"] = (
        cpu_seconds / wall_seconds * 100 if wall_seconds else 0.0
    )
    report["process_rss_before_mib"] = before["rss_bytes"] / (1024 * 1024)
    report["process_rss_after_mib"] = after["rss_bytes"] / (1024 * 1024)
    report["process_rss_delta_mib"] = (
        after["rss_bytes"] - before["rss_bytes"]
    ) / (1024 * 1024)
    report["process_peak_rss_mib"] = after["peak_rss_bytes"] / (1024 * 1024)
    report["process_allocated_blocks_delta"] = (
        after["allocated_blocks"] - before["allocated_blocks"]
    )
    return report


def _build_python_query(index: int):
    table = PythonTable(f"user_{index:06d}")
    return table.select(table.id, table.label, where=table.active == True)


def _build_mojo_query(index: int):
    table = MojoTable(f"user_{index:06d}")
    return table.select(table.id, table.label, where=table.active == True)


def _build_objects(builder, object_count: int):
    before = _process_snapshot()
    started = time.perf_counter()
    objects = [builder(index) for index in range(object_count)]
    after = _process_snapshot()
    report = _with_process_stats(
        {"object_count": object_count},
        before,
        after,
        time.perf_counter() - started,
    )
    return objects, report


def _object_string_digest(objects):
    digest = hashlib.sha256()
    total_bytes = 0
    first = None
    last = None
    for query in objects:
        text = query.__str__()
        encoded = text.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        total_bytes += len(encoded)
        if first is None:
            first = text
        last = text
    return {
        "sha256": digest.hexdigest(),
        "total_bytes": total_bytes,
        "first": first,
        "last": last,
    }


def _stringify_objects(objects, conversions: int):
    outputs = []
    total_bytes = 0
    for index in range(conversions):
        text = objects[index % len(objects)].__str__()
        outputs.append(text)
        total_bytes += len(text)
    return total_bytes, outputs


def measure_stringification(
    objects, conversions: int, repeats: int, warmups: int
):
    if not objects:
        raise ValueError("object_count must be positive")

    for _ in range(warmups):
        _, outputs = _stringify_objects(objects, conversions)
        del outputs
    gc.collect()

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        before = _process_snapshot()
        samples = []
        peak_rss_bytes = before["rss_bytes"]
        last_output_bytes = 0
        last_checksum = 0
        for _ in range(repeats):
            sample_before = _process_snapshot()
            started = time.perf_counter()
            output_bytes, outputs = _stringify_objects(objects, conversions)
            wall_seconds = time.perf_counter() - started
            sample_after = _process_snapshot()
            last_output_bytes = output_bytes
            last_checksum = sum(map(len, outputs))
            peak_rss_bytes = max(peak_rss_bytes, sample_after["rss_bytes"])
            samples.append(
                {
                    "wall_seconds": wall_seconds,
                    "user_cpu_seconds": (
                        sample_after["user_cpu_seconds"]
                        - sample_before["user_cpu_seconds"]
                    ),
                    "system_cpu_seconds": (
                        sample_after["system_cpu_seconds"]
                        - sample_before["system_cpu_seconds"]
                    ),
                    "cpu_seconds": (
                        sample_after["cpu_seconds"]
                        - sample_before["cpu_seconds"]
                    ),
                    "allocated_blocks_delta": (
                        sample_after["allocated_blocks"]
                        - sample_before["allocated_blocks"]
                    ),
                    "rss_with_outputs_mib": (
                        sample_after["rss_bytes"] / (1024 * 1024)
                    ),
                    "output_bytes": output_bytes,
                }
            )
            del outputs
            gc.collect()
        after = _process_snapshot()
    finally:
        if gc_was_enabled:
            gc.enable()

    median_wall = statistics.median(
        sample["wall_seconds"] for sample in samples
    )
    median_cpu = statistics.median(sample["cpu_seconds"] for sample in samples)
    median_user_cpu = statistics.median(
        sample["user_cpu_seconds"] for sample in samples
    )
    median_system_cpu = statistics.median(
        sample["system_cpu_seconds"] for sample in samples
    )
    peak_rss_bytes = max(peak_rss_bytes, after["peak_rss_bytes"])
    median_allocated_blocks = statistics.median(
        sample["allocated_blocks_delta"] for sample in samples
    )
    return {
        "object_count": len(objects),
        "conversions_per_repeat": conversions,
        "median_seconds": median_wall,
        "nanoseconds_per_conversion": median_wall * 1e9 / conversions,
        "conversions_per_second": conversions / median_wall,
        "median_user_cpu_seconds": median_user_cpu,
        "median_system_cpu_seconds": median_system_cpu,
        "median_cpu_seconds": median_cpu,
        "median_cpu_utilization_percent": (
            median_cpu / median_wall * 100 if median_wall else 0.0
        ),
        "median_allocated_blocks_delta": median_allocated_blocks,
        "output_bytes_per_repeat": last_output_bytes,
        "output_bytes_per_conversion": last_output_bytes / conversions,
        "last_checksum": last_checksum,
        "rss_before_mib": before["rss_bytes"] / (1024 * 1024),
        "rss_after_mib": after["rss_bytes"] / (1024 * 1024),
        "rss_delta_mib": (
            after["rss_bytes"] - before["rss_bytes"]
        ) / (1024 * 1024),
        "conversion_peak_rss_mib": peak_rss_bytes / (1024 * 1024),
        "conversion_peak_rss_delta_mib": (
            peak_rss_bytes - before["rss_bytes"]
        ) / (1024 * 1024),
        "samples": samples,
    }


def _query_result_digest(results):
    digest = hashlib.sha256()
    total_bytes = 0
    first = None
    last = None
    for result in results:
        encoded = repr(result).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        total_bytes += len(encoded)
        if first is None:
            first = result
        last = result
    return {
        "sha256": digest.hexdigest(),
        "total_bytes": total_bytes,
        "first": repr(first),
        "last": repr(last),
    }


def _materialize_query_results(call, conversions: int):
    results = [call(index) for index in range(conversions)]
    return sum(len(repr(result)) for result in results), results


def measure_query_materialization(
    call, conversions: int, repeats: int, warmups: int
):
    for _ in range(warmups):
        _, results = _materialize_query_results(call, conversions)
        del results
    gc.collect()

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        before = _process_snapshot()
        samples = []
        peak_rss_bytes = before["rss_bytes"]
        last_output_bytes = 0
        last_digest = None
        for _ in range(repeats):
            sample_before = _process_snapshot()
            started = time.perf_counter()
            output_bytes, results = _materialize_query_results(
                call, conversions
            )
            wall_seconds = time.perf_counter() - started
            sample_after = _process_snapshot()
            result_digest = _query_result_digest(results)
            last_output_bytes = output_bytes
            last_digest = result_digest["sha256"]
            peak_rss_bytes = max(peak_rss_bytes, sample_after["rss_bytes"])
            samples.append(
                {
                    "wall_seconds": wall_seconds,
                    "user_cpu_seconds": (
                        sample_after["user_cpu_seconds"]
                        - sample_before["user_cpu_seconds"]
                    ),
                    "system_cpu_seconds": (
                        sample_after["system_cpu_seconds"]
                        - sample_before["system_cpu_seconds"]
                    ),
                    "cpu_seconds": (
                        sample_after["cpu_seconds"]
                        - sample_before["cpu_seconds"]
                    ),
                    "allocated_blocks_delta": (
                        sample_after["allocated_blocks"]
                        - sample_before["allocated_blocks"]
                    ),
                    "rss_with_results_mib": (
                        sample_after["rss_bytes"] / (1024 * 1024)
                    ),
                    "result_bytes": output_bytes,
                    "result_sha256": result_digest["sha256"],
                }
            )
            del results
            gc.collect()
        after = _process_snapshot()
    finally:
        if gc_was_enabled:
            gc.enable()

    median_wall = statistics.median(
        sample["wall_seconds"] for sample in samples
    )
    median_cpu = statistics.median(sample["cpu_seconds"] for sample in samples)
    median_user_cpu = statistics.median(
        sample["user_cpu_seconds"] for sample in samples
    )
    median_system_cpu = statistics.median(
        sample["system_cpu_seconds"] for sample in samples
    )
    peak_rss_bytes = max(peak_rss_bytes, after["peak_rss_bytes"])
    return {
        "operations_per_repeat": conversions,
        "median_seconds": median_wall,
        "nanoseconds_per_operation": median_wall * 1e9 / conversions,
        "operations_per_second": conversions / median_wall,
        "median_user_cpu_seconds": median_user_cpu,
        "median_system_cpu_seconds": median_system_cpu,
        "median_cpu_seconds": median_cpu,
        "median_cpu_utilization_percent": (
            median_cpu / median_wall * 100 if median_wall else 0.0
        ),
        "median_allocated_blocks_delta": statistics.median(
            sample["allocated_blocks_delta"] for sample in samples
        ),
        "last_result_sha256": last_digest,
        "result_bytes_per_repeat": last_output_bytes,
        "result_bytes_per_operation": last_output_bytes / conversions,
        "rss_before_mib": before["rss_bytes"] / (1024 * 1024),
        "rss_after_mib": after["rss_bytes"] / (1024 * 1024),
        "rss_delta_mib": (
            after["rss_bytes"] - before["rss_bytes"]
        ) / (1024 * 1024),
        "materialization_peak_rss_mib": peak_rss_bytes / (1024 * 1024),
        "materialization_peak_rss_delta_mib": (
            peak_rss_bytes - before["rss_bytes"]
        ) / (1024 * 1024),
        "samples": samples,
    }


def _name_column(table):
    return table.__getattr__("name")


def _build_query_workload(implementation, workload, argument_count):
    before = _process_snapshot()
    started = time.perf_counter()
    if workload == "cold_queries":
        if implementation == "python_sql":
            def call(index):
                return tuple(_build_python_query(index))
        elif implementation == "mojo_sql":
            def call(index):
                return tuple(_build_mojo_query(index))
        else:
            raise ValueError(f"unknown implementation: {implementation}")
    elif workload == "aggregate_queries":
        if implementation == "python_sql":
            table = PythonTable("user")
        elif implementation == "mojo_sql":
            table = MojoTable("user")
        else:
            raise ValueError(f"unknown implementation: {implementation}")
        select = table.select(Count(table.id))

        def call(_):
            return tuple(select)
    elif workload in {"simple_queries", "many_arguments"}:
        if implementation == "python_sql":
            table = PythonTable("user")
        elif implementation == "mojo_sql":
            table = MojoTable("user")
        else:
            raise ValueError(f"unknown implementation: {implementation}")
        name = _name_column(table)
        select = table.select(table.id, name)

        if workload == "simple_queries":
            def call(_):
                return tuple(select)
        else:
            values = [
                f"foo-{index:08d}" for index in range(argument_count)
            ]

            def call(index):
                value = values[index % len(values)]
                select.where = name == value
                return tuple(select)
    else:
        raise ValueError(f"unknown query workload: {workload}")

    setup_report = _with_process_stats(
        {
            "implementation": implementation,
            "workload": workload,
            "argument_count": (
                argument_count if workload == "many_arguments" else 0
            ),
        },
        before,
        _process_snapshot(),
        time.perf_counter() - started,
    )
    expected = call(0)
    return call, expected, setup_report


_IMPLEMENTATION_BUILDERS = {
    "python_sql": _build_python_query,
    "mojo_sql": _build_mojo_query,
}


def _run_implementation(args):
    if args.workload == "object_to_string":
        objects, build_report = _build_objects(
            _IMPLEMENTATION_BUILDERS[args.implementation],
            args.objects,
        )
        parity = _object_string_digest(objects)
        stringification = measure_stringification(
            objects,
            args.iterations,
            args.repeats,
            args.warmups,
        )
        return {
            "implementation": args.implementation,
            "object_construction": build_report,
            "parity": parity,
            "stringification": stringification,
        }

    call, expected, setup_report = _build_query_workload(
        args.implementation,
        args.workload,
        args.arguments,
    )
    parity = _query_result_digest([expected])
    materialization = measure_query_materialization(
        call,
        args.iterations,
        args.repeats,
        args.warmups,
    )
    if materialization["last_result_sha256"] is None:
        raise AssertionError("query workload produced no results")
    return {
        "implementation": args.implementation,
        "workload": args.workload,
        "setup": setup_report,
        "parity": parity,
        "materialization": materialization,
    }


def _run_isolated_implementation(args, implementation: str, workload: str):
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--implementation",
        implementation,
        "--workload",
        workload,
        "--objects",
        str(args.objects),
        "--arguments",
        str(args.arguments),
        "--iterations",
        str(args.iterations),
        "--repeats",
        str(args.repeats),
        "--warmups",
        str(args.warmups),
        "--json",
    ]
    child_environment = os.environ.copy()
    child_environment.pop("PYTHONHOME", None)
    child_environment["PYTHON_SQL_BENCHMARK_IMPLEMENTATION"] = implementation
    package_root = (
        args.python_sql_root
        if implementation == "python_sql"
        else PROJECT_ROOT
    )
    child_environment["PYTHONPATH"] = str(package_root)
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=child_environment,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"{implementation}/{workload} benchmark failed with exit code "
            f"{error.returncode}:\n"
            f"stdout={error.stdout!r}\nstderr={error.stderr!r}"
        ) from error
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{implementation}/{workload} benchmark returned invalid JSON:\n"
            f"stdout={completed.stdout!r}\nstderr={completed.stderr!r}"
        ) from error


def run_object_benchmark(args):
    implementations = {
        name: _run_isolated_implementation(args, name, "object_to_string")
        for name in _IMPLEMENTATION_BUILDERS
    }
    parity_values = {
        (
            report["parity"]["sha256"],
            report["parity"]["total_bytes"],
        )
        for report in implementations.values()
    }
    if len(parity_values) != 1:
        raise AssertionError(
            "object-to-string parity mismatch: "
            + repr(
                {
                    name: (
                        report["parity"]["sha256"],
                        report["parity"]["total_bytes"],
                    )
                    for name, report in implementations.items()
                }
            )
        )
    return {
        "mode": "object_to_string",
        "contract": {
            "conversion_only": True,
            "object_construction_timed_separately": True,
            "string_method": "query.__str__()",
        },
        "objects": args.objects,
        "conversions_per_repeat": args.iterations,
        "repeats": args.repeats,
        "warmups": args.warmups,
        "parity": {
            "sha256": next(iter(parity_values))[0],
            "total_bytes": next(iter(parity_values))[1],
        },
        "implementations": implementations,
    }


def _workload_implementations(workload):
    return tuple(_IMPLEMENTATION_BUILDERS)


def run_query_benchmark(args, workload: str):
    implementations = {
        name: _run_isolated_implementation(args, name, workload)
        for name in _workload_implementations(workload)
    }
    parity_values = {
        (
            report["parity"]["sha256"],
            report["parity"]["total_bytes"],
        )
        for report in implementations.values()
    }
    if len(parity_values) != 1:
        raise AssertionError(
            f"{workload} parity mismatch: "
            + repr(
                {
                    name: (
                        report["parity"]["sha256"],
                        report["parity"]["total_bytes"],
                    )
                    for name, report in implementations.items()
                }
            )
        )
    sequence_values = {
        report["materialization"]["last_result_sha256"]
        for report in implementations.values()
    }
    if len(sequence_values) != 1:
        raise AssertionError(
            f"{workload} repeated-result parity mismatch: "
            + repr(
                {
                    name: report["materialization"]["last_result_sha256"]
                    for name, report in implementations.items()
                }
            )
        )
    return {
        "mode": workload,
        "contract": {
            "operation": (
                "create query and tuple(query)"
                if workload == "cold_queries"
                else (
                    "tuple(prebuilt aggregate select)"
                    if workload == "aggregate_queries"
                    else (
                        "tuple(select) on a prebuilt simple query"
                        if workload == "simple_queries"
                        else "set select.where and tuple(select)"
                    )
                )
            ),
            "setup_timed_separately": True,
        },
        "arguments": args.arguments if workload == "many_arguments" else 0,
        "operations_per_repeat": args.iterations,
        "repeats": args.repeats,
        "warmups": args.warmups,
        "parity": {
            "sha256": next(iter(parity_values))[0],
            "total_bytes": next(iter(parity_values))[1],
        },
        "implementations": implementations,
    }


def _print_query_benchmark(report):
    print(f"Hard {report['mode']} benchmark")
    print(
        f"operations/repeat={report['operations_per_repeat']} "
        f"arguments={report['arguments']} "
        f"repeats={report['repeats']} warmups={report['warmups']}"
    )
    print(
        f"parity sha256={report['parity']['sha256']} "
        f"result_bytes={report['parity']['total_bytes']}"
    )
    baseline = report["implementations"]["python_sql"]["materialization"]
    for name, implementation in report["implementations"].items():
        setup = implementation["setup"]
        stats = implementation["materialization"]
        speedup = (
            baseline["median_seconds"] / stats["median_seconds"]
            if name != "python_sql"
            else 1.0
        )
        print(f"\n{name}")
        print(
            f"  operation: {stats['nanoseconds_per_operation']:,.1f} ns "
            f"({stats['operations_per_second']:,.1f} operations/s)"
        )
        print(
            f"  CPU: {stats['median_cpu_seconds']:.6f}s "
            f"({stats['median_cpu_utilization_percent']:.1f}% CPU/wall ratio)"
        )
        print(
            f"  allocator: median CPython block delta "
            f"{stats['median_allocated_blocks_delta']:+,}"
        )
        print(
            f"  RSS: before={stats['rss_before_mib']:.2f} MiB "
            f"peak={stats['materialization_peak_rss_mib']:.2f} MiB "
            f"after={stats['rss_after_mib']:.2f} MiB "
            f"peak_delta={stats['materialization_peak_rss_delta_mib']:.2f} MiB"
        )
        print(
            f"  result: {stats['result_bytes_per_repeat']:,} bytes "
            f"({stats['result_bytes_per_operation']:.1f} bytes/op)"
        )
        print(
            f"  setup: {setup['phase_wall_seconds']:.3f}s, "
            f"CPU {setup['process_cpu_percent']:.1f}%, "
            f"RSS delta {setup['process_rss_delta_mib']:.2f} MiB"
        )
        if name != "python_sql":
            print(f"  speedup vs python-sql: {speedup:.2f}x")


def _print_object_benchmark(report):
    print("Hard python-sql object-to-string benchmark")
    print(
        f"objects={report['objects']} "
        f"conversions/repeat={report['conversions_per_repeat']} "
        f"repeats={report['repeats']} warmups={report['warmups']}"
    )
    print(
        f"parity sha256={report['parity']['sha256']} "
        f"bytes={report['parity']['total_bytes']}"
    )
    baseline = report["implementations"]["python_sql"]["stringification"]
    for name, implementation in report["implementations"].items():
        build = implementation["object_construction"]
        stats = implementation["stringification"]
        speedup = (
            baseline["median_seconds"] / stats["median_seconds"]
            if name != "python_sql"
            else 1.0
        )
        print(f"\n{name}")
        print(
            f"  conversion: {stats['nanoseconds_per_conversion']:,.1f} ns/string "
            f"({stats['conversions_per_second']:,.1f} strings/s)"
        )
        print(
            f"  CPU: {stats['median_cpu_seconds']:.6f}s "
            f"({stats['median_cpu_utilization_percent']:.1f}% CPU/wall ratio)"
        )
        print(
            f"  allocator: median CPython block delta "
            f"{stats['median_allocated_blocks_delta']:+,}"
        )
        print(
            f"  RSS: before={stats['rss_before_mib']:.2f} MiB "
            f"peak={stats['conversion_peak_rss_mib']:.2f} MiB "
            f"after={stats['rss_after_mib']:.2f} MiB "
            f"peak_delta={stats['conversion_peak_rss_delta_mib']:.2f} MiB"
        )
        print(
            f"  output: {stats['output_bytes_per_repeat']:,} bytes "
            f"({stats['output_bytes_per_conversion']:.1f} bytes/string)"
        )
        print(
            f"  object build: {build['phase_wall_seconds']:.3f}s, "
            f"CPU {build['process_cpu_percent']:.1f}%, "
            f"RSS delta {build['process_rss_delta_mib']:.2f} MiB"
        )
        if name != "python_sql":
            print(f"  speedup vs python-sql: {speedup:.2f}x")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Hard benchmarks for cold query construction, warm rendering, "
            "and repeated parameterized queries"
        )
    )
    parser.add_argument(
        "--workload",
        choices=(
            "all",
            "object_to_string",
            "cold_queries",
            "simple_queries",
            "many_arguments",
            "aggregate_queries",
        ),
        default="all",
        help="workload to run (default: all)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100_000,
        help="conversions or query operations per measured repeat",
    )
    parser.add_argument(
        "--objects",
        type=int,
        default=2_048,
        help="distinct objects for object_to_string",
    )
    parser.add_argument(
        "--arguments",
        type=int,
        default=100_000,
        help="distinct foo-* values for many_arguments",
    )
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--python-sql-root",
        type=Path,
        default=DEFAULT_PYTHON_SQL_ROOT,
        help=(
            "root containing the upstream python-sql package "
            f"(default: {DEFAULT_PYTHON_SQL_ROOT})"
        ),
    )
    parser.add_argument(
        "--implementation",
        choices=tuple(_IMPLEMENTATION_BUILDERS),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if (
        args.iterations <= 0
        or args.objects <= 0
        or args.arguments <= 0
        or args.repeats <= 0
        or args.warmups < 0
    ):
        parser.error(
            "iterations, objects, arguments, and repeats must be positive; "
            "warmups cannot be negative"
        )

    args.python_sql_root = args.python_sql_root.resolve()
    if args.implementation:
        if args.workload == "all":
            parser.error("isolated implementation requires one workload")
        print(json.dumps(_run_implementation(args), indent=2))
        return 0
    if not (args.python_sql_root / "sql" / "__init__.py").is_file():
        parser.error(
            "upstream python-sql not found under "
            f"{args.python_sql_root}; use --python-sql-root"
        )
    if args.workload == "all":
        reports = {
            "object_to_string": run_object_benchmark(args),
            "cold_queries": run_query_benchmark(args, "cold_queries"),
            "simple_queries": run_query_benchmark(args, "simple_queries"),
            "aggregate_queries": run_query_benchmark(
                args, "aggregate_queries"),
            "many_arguments": run_query_benchmark(args, "many_arguments"),
        }
        if args.as_json:
            print(json.dumps({"mode": "all", "workloads": reports}, indent=2))
        else:
            _print_object_benchmark(reports["object_to_string"])
            _print_query_benchmark(reports["cold_queries"])
            _print_query_benchmark(reports["simple_queries"])
            _print_query_benchmark(reports["aggregate_queries"])
            _print_query_benchmark(reports["many_arguments"])
        return 0

    if args.workload == "object_to_string":
        report = run_object_benchmark(args)
        printer = _print_object_benchmark
    else:
        report = run_query_benchmark(args, args.workload)
        printer = _print_query_benchmark
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        printer(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
