"""Mutable state carried through one render pass."""

from std.python import PythonObject

from ..flavor import AliasState, Flavor


struct Context(Movable):
    var flavor: Flavor
    var aliases: AliasState
    var params: List[PythonObject]

    def __init__(out self, flavor: Flavor, var aliases: AliasState):
        self.flavor = flavor.copy()
        self.aliases = aliases^
        self.params = List[PythonObject]()

    def placeholder(self) -> String:
        return self.flavor.placeholder()

    def push(mut self, value: PythonObject) -> String:
        self.params.append(value)
        return self.flavor.placeholder()
