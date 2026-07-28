"""The native SQL node.

A node owns its own payload and *references* its children through the Python
objects that hold them.  Building a parent is therefore O(1): no child subtree
is ever copied, and CPython reference counting keeps the graph alive exactly as
long as the Python API objects that expose it.

Rendering walks the graph with `Tree.kid`, which downcasts a child handle back
to its native representation — a type check plus a pointer offset, with no
dictionary lookup and no Python attribute access.
"""

from std.python import PythonObject

from .opcode import OP_NONE

comptime TreePointer = UnsafePointer[mut=True, Tree, MutAnyOrigin]


struct Tree(Movable, Writable):
    var op: Int
    var i0: Int
    """Opcode specific integer: operator id, flags, action kind, ..."""
    var i1: Int
    """Alias identity for from-items and windows."""
    var s0: String
    var s1: String
    var s2: String
    var value: Optional[PythonObject]
    """Opaque payload of a parameter or literal node."""
    var kids: List[PythonObject]

    def __init__(
        out self,
        op: Int,
        var kids: List[PythonObject],
        i0: Int = 0,
        i1: Int = 0,
        var s0: String = String(""),
        var s1: String = String(""),
        var s2: String = String(""),
    ) raises:
        self.op = op
        self.i0 = i0
        self.i1 = i1
        self.s0 = s0^
        self.s1 = s1^
        self.s2 = s2^
        self.value = None
        self.kids = kids^

    def payload(self) raises -> PythonObject:
        """The parameter value; only parameter and literal nodes carry one."""
        if not self.value:
            raise Error("node has no value")
        return self.value.value()

    def count(self) -> Int:
        return len(self.kids)

    def kid(self, index: Int) raises -> TreePointer:
        """Child at a positional slot; a missing slot is a malformed tree."""
        if index < 0 or index >= len(self.kids):
            raise Error("missing child node")
        return self.kids[index].downcast_value_ptr[Tree]()

    def kid_op(self, index: Int) raises -> Int:
        return self.kid(index)[].op

    def has(self, index: Int) raises -> Bool:
        """True when the slot exists and is not the absent-value node."""
        if index < 0 or index >= len(self.kids):
            return False
        return self.kid(index)[].op != OP_NONE

    def write_to(self, mut writer: Some[Writer]):
        writer.write("<sql node op=", self.op, ">")

    def write_repr_to(self, mut writer: Some[Writer]):
        writer.write("<sql node op=", self.op, ">")
