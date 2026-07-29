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
