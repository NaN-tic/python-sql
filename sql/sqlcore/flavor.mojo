"""Native rendering options and alias assignment state.

`Flavor` is lowered once per render from the Python `Flavor` object, so the
renderer never reads a Python mapping while walking the tree.
"""

from .text import alias_name

comptime LIMIT_STYLE_LIMIT = 0
comptime LIMIT_STYLE_FETCH = 1
comptime LIMIT_STYLE_ROWNUM = 2


@fieldwise_init
struct Flavor(ImplicitlyCopyable, Movable, Writable):
    var qmark: Bool
    var ilike: Bool
    var no_as: Bool
    var no_boolean: Bool
    var null_ordering: Bool
    var filter_: Bool
    var escape_empty: Bool
    var limit_style: Int
    var max_limit: Int
    """Negative when unset."""

    @staticmethod
    def default() -> Flavor:
        return Flavor(
            qmark=False,
            ilike=False,
            no_as=False,
            no_boolean=False,
            null_ordering=True,
            filter_=False,
            escape_empty=False,
            limit_style=LIMIT_STYLE_LIMIT,
            max_limit=-1,
        )

    def placeholder(self) -> String:
        return "?" if self.qmark else "%s"

    def write_to(self, mut writer: Some[Writer]):
        writer.write("<sql flavor>")

    def write_repr_to(self, mut writer: Some[Writer]):
        writer.write("<sql flavor>")


struct AliasState(Movable):
    """Assigns `a`, `b`, `c`, ... to from-items in first-seen order.

    Keys are the stable identities carried by from-item nodes, so a copied
    subtree keeps the alias its Python object would receive.
    """

    var keys: List[Int]
    var names: List[String]
    var excluded: List[Int]
    var next_index: Int
    var initial_index: Int
    var high_water: Int
    """Largest alias index reached, kept across scope resets."""
    var external: Bool
    """True when the caller opened an explicit `AliasManager` context."""
    var active: Bool

    def __init__(out self, external: Bool = False, initial_index: Int = 0):
        self.keys = List[Int]()
        self.names = List[String]()
        self.excluded = List[Int]()
        self.next_index = initial_index
        self.initial_index = initial_index
        self.high_water = initial_index
        self.external = external
        self.active = False

    def begin(mut self):
        self.keys = List[Int]()
        self.names = List[String]()
        self.excluded = List[Int]()
        self.next_index = self.initial_index
        self.active = True

    def end(mut self):
        self.keys = List[Int]()
        self.names = List[String]()
        self.excluded = List[Int]()
        self.next_index = self.initial_index
        self.active = False

    def exclude(mut self, key: Int):
        for item in self.excluded:
            if item == key:
                return
        self.excluded.append(key)

    def get(mut self, key: Int, assign: Bool) -> String:
        if not self.active:
            return String("")
        for item in self.excluded:
            if item == key:
                return String("")
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                return self.names[i]
        if not assign:
            return String("")
        var name = alias_name(self.next_index)
        self.next_index += 1
        if self.next_index > self.high_water:
            self.high_water = self.next_index
        self.keys.append(key)
        self.names.append(name)
        return name

    def bind(mut self, key: Int, name: String):
        """Register an alias chosen outside the renderer."""
        for i in range(len(self.keys)):
            if self.keys[i] == key:
                return
        self.keys.append(key)
        self.names.append(name)
