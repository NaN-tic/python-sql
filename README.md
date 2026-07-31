# python-sql-mojo

A Mojo-backed, Linux-only replacement for [`python-sql`](https://pypi.org/project/python-sql/).

The distribution package is `python-sql-mojo`; its Python import remains `sql` for drop-in compatibility. It cannot coexist with the upstream `python-sql` package in one environment because both provide that import.

## Development

```bash
pixi run build
pixi run test
pixi run check
```

`pixi run build` compiles `sql/_core.mojo`, embeds the required Mojo runtime libraries, and writes a `manylinux_2_35_x86_64` wheel to `dist/`.

## Benchmark

The benchmark compares the Mojo implementation in this repository with
`python-sql` 1.8.1 installed separately. By default it expects the upstream
package under `../python-sql-upstream`:

```bash
python3 -m pip install --no-deps \
    --target ../python-sql-upstream python-sql==1.8.1
pixi run python tools/build.py
pixi run python benchmarks/compare.py
```

Use `--python-sql-root /path/to/upstream` when the reference package is stored
elsewhere. The benchmark only constructs and renders SQL queries; it does not
connect to or execute them against a database.

Both implementations run the same workload code and import
`Table` and `Count` from the same `sql` module names. The controller starts
them in separate processes and changes only `PYTHONPATH`, because the upstream
and Mojo distributions both provide the `sql` package and cannot be imported
side by side in one Python process.

## Installation

```bash
python3 -m pip install python-sql-mojo
python3 -c "from sql import Table; print(Table('party').select())"
```

Consumers do not need Mojo installed. Build and publish one wheel for each supported platform.

## Publishing

```bash
pixi run build
pixi run check
TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-... pixi run publish
```
