"""CPython entry point: registers the native SQL core as `sql._core`."""

from std.os import abort
from std.python import PythonObject
from std.python.bindings import PythonModuleBuilder

from sqlcore import Flavor, Tree
from sqlcore.api import (
    constants,
    flavor,
    identity,
    make,
    make_text,
    none,
    opcode,
    render,
    value,
)


@export
def PyInit__core() abi("C") -> PythonObject:
    try:
        var builder = PythonModuleBuilder("_core")
        _ = builder.add_type[Tree]("Node")
        _ = builder.add_type[Flavor]("Flavor")
        builder.def_function[make]("make")
        builder.def_function[make_text]("make_text")
        builder.def_function[value]("value")
        builder.def_function[none]("none")
        builder.def_function[flavor]("flavor")
        builder.def_function[render]("render")
        builder.def_function[identity]("identity")
        builder.def_function[opcode]("opcode")
        builder.def_function[constants]("constants")
        return builder.finalize()
    except e:
        abort(String("error creating sql._core: ", e))
