"""The whole surface exposed to CPython.

Three primitives are enough to express every SQL construct: `make` builds a
node from child handles, `value` wraps a Python object as a parameter or
literal, and `render` turns a tree into `(sql, params)`.
"""

from std.python import Python, PythonObject

from .flavor import LIMIT_STYLE_FETCH, LIMIT_STYLE_LIMIT, LIMIT_STYLE_ROWNUM
from .flavor import AliasState, Flavor
from .opcode import *
from .program import Tree
from .render.context import Context
from .render.expression import render_expr
from .render.statement import render_query

comptime LITERAL_PLAIN = 0
comptime LITERAL_TRUE = 1
comptime LITERAL_FALSE = 2


def _string(value: PythonObject) raises -> String:
    if value is None:
        return String("")
    return String(py=value)


def make(
    op: PythonObject,
    kids: PythonObject,
    i0: PythonObject,
    i1: PythonObject,
) raises -> PythonObject:
    """Build a node without any text payload."""
    var count = len(kids)
    var children = List[PythonObject](capacity=count)
    for i in range(count):
        children.append(kids[i])
    var tree = Tree(Int(py=op), children^, i0=Int(py=i0), i1=Int(py=i1))
    return PythonObject(alloc=tree^)


def make_text(
    op: PythonObject,
    kids: PythonObject,
    i0: PythonObject,
    i1: PythonObject,
    s0: PythonObject,
    s1: PythonObject,
    s2: PythonObject,
) raises -> PythonObject:
    """Build a node carrying up to three strings."""
    var count = len(kids)
    var children = List[PythonObject](capacity=count)
    for i in range(count):
        children.append(kids[i])
    var tree = Tree(
        Int(py=op),
        children^,
        i0=Int(py=i0),
        i1=Int(py=i1),
        s0=_string(s0),
        s1=_string(s1),
        s2=_string(s2),
    )
    return PythonObject(alloc=tree^)


def value(op: PythonObject, payload: PythonObject) raises -> PythonObject:
    """Build a parameter or literal node holding an opaque Python value."""
    var opcode = Int(py=op)
    var flag = LITERAL_PLAIN
    if opcode == OP_LITERAL:
        var text = String(py=payload)
        if text == "True":
            flag = LITERAL_TRUE
        elif text == "False":
            flag = LITERAL_FALSE
    var tree = Tree(opcode, List[PythonObject](), i0=flag)
    tree.value = Optional(payload)
    return PythonObject(alloc=tree^)


def none() raises -> PythonObject:
    var tree = Tree(OP_NONE, List[PythonObject]())
    return PythonObject(alloc=tree^)


def flavor(options: PythonObject) raises -> PythonObject:
    """Lower the Python `Flavor` into its native form, once per change."""
    var result = Flavor(
        qmark=Bool(py=options[0]),
        ilike=Bool(py=options[1]),
        no_as=Bool(py=options[2]),
        no_boolean=Bool(py=options[3]),
        null_ordering=Bool(py=options[4]),
        filter_=Bool(py=options[5]),
        escape_empty=Bool(py=options[6]),
        limit_style=Int(py=options[7]),
        max_limit=Int(py=options[8]),
    )
    return PythonObject(alloc=result^)


def render(
    node: PythonObject,
    flavor_object: PythonObject,
    aliases: PythonObject,
) raises -> PythonObject:
    """Render a tree to `(sql, params, alias_count)`.

    `aliases` is `None`, or `(count, [(identity, name), ...])` when the caller
    manages aliases through an explicit `AliasManager` context.
    """
    var tree = node.downcast_value_ptr[Tree]()
    var native_flavor = flavor_object.downcast_value_ptr[Flavor]()[].copy()
    var external = aliases is not None
    var initial = 0
    if external:
        initial = Int(py=aliases[0])
    var state = AliasState(external, initial)
    if external:
        state.begin()
        var bindings = aliases[1]
        for i in range(len(bindings)):
            state.bind(Int(py=bindings[i][0]), String(py=bindings[i][1]))
    var ctx = Context(native_flavor, state^)

    var sql: String
    if is_statement(tree[].op):
        sql = render_query(tree[], ctx)
    else:
        sql = render_expr(tree[], ctx)

    var params = Python.list()
    for item in ctx.params:
        params.append(item)
    return Python.tuple(sql, params, ctx.aliases.high_water)


def identity(node: PythonObject) raises -> PythonObject:
    """The alias identity carried by a from-item node."""
    return PythonObject(node.downcast_value_ptr[Tree]()[].i1)


def opcode(node: PythonObject) raises -> PythonObject:
    return PythonObject(node.downcast_value_ptr[Tree]()[].op)


def constants() raises -> PythonObject:
    """Every opcode and slot index, so Python never duplicates the contract."""
    var result = Python.dict()
    result["OP_NONE"] = OP_NONE
    result["OP_NULL"] = OP_NULL
    result["OP_PARAM"] = OP_PARAM
    result["OP_LITERAL"] = OP_LITERAL
    result["OP_RAW"] = OP_RAW
    result["OP_STAR"] = OP_STAR
    result["OP_TABLE"] = OP_TABLE
    result["OP_COLUMN"] = OP_COLUMN
    result["OP_EXCLUDED"] = OP_EXCLUDED
    result["OP_EXCLUDED_COLUMN"] = OP_EXCLUDED_COLUMN
    result["OP_LIST"] = OP_LIST
    result["OP_BINARY"] = OP_BINARY
    result["OP_UNARY"] = OP_UNARY
    result["OP_NARY"] = OP_NARY
    result["OP_BETWEEN"] = OP_BETWEEN
    result["OP_IS"] = OP_IS
    result["OP_LIKE"] = OP_LIKE
    result["OP_CASE"] = OP_CASE
    result["OP_CAST"] = OP_CAST
    result["OP_COLLATE"] = OP_COLLATE
    result["OP_CONDITIONAL"] = OP_CONDITIONAL
    result["OP_AS"] = OP_AS
    result["OP_ORDER"] = OP_ORDER
    result["OP_AT_TIME_ZONE"] = OP_AT_TIME_ZONE
    result["OP_FUNCTION"] = OP_FUNCTION
    result["OP_FUNCTION_NOT_CALLABLE"] = OP_FUNCTION_NOT_CALLABLE
    result["OP_FUNCTION_KEYWORD"] = OP_FUNCTION_KEYWORD
    result["OP_TRIM"] = OP_TRIM
    result["OP_EXTRACT"] = OP_EXTRACT
    result["OP_AGGREGATE"] = OP_AGGREGATE
    result["OP_WINDOW_FUNCTION"] = OP_WINDOW_FUNCTION
    result["OP_WINDOW"] = OP_WINDOW
    result["OP_GROUPING"] = OP_GROUPING
    result["OP_GROUPING_SET"] = OP_GROUPING_SET
    result["OP_ROLLUP"] = OP_ROLLUP
    result["OP_CUBE"] = OP_CUBE
    result["OP_ROLLUP_ITEM"] = OP_ROLLUP_ITEM
    result["OP_JOIN"] = OP_JOIN
    result["OP_LATERAL"] = OP_LATERAL
    result["OP_WITH"] = OP_WITH
    result["OP_FOR"] = OP_FOR
    result["OP_SELECT"] = OP_SELECT
    result["OP_VALUES"] = OP_VALUES
    result["OP_INSERT"] = OP_INSERT
    result["OP_UPDATE"] = OP_UPDATE
    result["OP_DELETE"] = OP_DELETE
    result["OP_MERGE"] = OP_MERGE
    result["OP_UNION"] = OP_UNION
    result["OP_INTERSECT"] = OP_INTERSECT
    result["OP_EXCEPT"] = OP_EXCEPT
    result["OP_CONFLICT"] = OP_CONFLICT
    result["OP_MATCHED"] = OP_MATCHED
    result["OP_LAST"] = OP_LAST
    result["SELECT_COLUMNS"] = SELECT_COLUMNS
    result["SELECT_FROM"] = SELECT_FROM
    result["SELECT_WHERE"] = SELECT_WHERE
    result["SELECT_GROUP_BY"] = SELECT_GROUP_BY
    result["SELECT_HAVING"] = SELECT_HAVING
    result["SELECT_ORDER_BY"] = SELECT_ORDER_BY
    result["SELECT_LIMIT"] = SELECT_LIMIT
    result["SELECT_OFFSET"] = SELECT_OFFSET
    result["SELECT_FOR"] = SELECT_FOR
    result["SELECT_WITH"] = SELECT_WITH
    result["SELECT_DISTINCT_ON"] = SELECT_DISTINCT_ON
    result["SELECT_WINDOWS"] = SELECT_WINDOWS
    result["SELECT_SLOTS"] = SELECT_SLOTS
    result["SELECT_FLAG_DISTINCT"] = SELECT_FLAG_DISTINCT
    result["SELECT_FLAG_FROM_DIRECT"] = SELECT_FLAG_FROM_DIRECT
    result["COMBINING_QUERIES"] = COMBINING_QUERIES
    result["COMBINING_ORDER_BY"] = COMBINING_ORDER_BY
    result["COMBINING_LIMIT"] = COMBINING_LIMIT
    result["COMBINING_OFFSET"] = COMBINING_OFFSET
    result["COMBINING_WITH"] = COMBINING_WITH
    result["COMBINING_SLOTS"] = COMBINING_SLOTS
    result["COMBINING_FLAG_ALL"] = COMBINING_FLAG_ALL
    result["INSERT_TABLE"] = INSERT_TABLE
    result["INSERT_COLUMNS"] = INSERT_COLUMNS
    result["INSERT_VALUES"] = INSERT_VALUES
    result["INSERT_RETURNING"] = INSERT_RETURNING
    result["INSERT_WITH"] = INSERT_WITH
    result["INSERT_CONFLICT"] = INSERT_CONFLICT
    result["INSERT_SLOTS"] = INSERT_SLOTS
    result["UPDATE_TABLE"] = UPDATE_TABLE
    result["UPDATE_COLUMNS"] = UPDATE_COLUMNS
    result["UPDATE_VALUES"] = UPDATE_VALUES
    result["UPDATE_FROM"] = UPDATE_FROM
    result["UPDATE_WHERE"] = UPDATE_WHERE
    result["UPDATE_RETURNING"] = UPDATE_RETURNING
    result["UPDATE_WITH"] = UPDATE_WITH
    result["UPDATE_SLOTS"] = UPDATE_SLOTS
    result["DELETE_TABLE"] = DELETE_TABLE
    result["DELETE_USING"] = DELETE_USING
    result["DELETE_WHERE"] = DELETE_WHERE
    result["DELETE_RETURNING"] = DELETE_RETURNING
    result["DELETE_WITH"] = DELETE_WITH
    result["DELETE_SLOTS"] = DELETE_SLOTS
    result["DELETE_FLAG_ONLY"] = DELETE_FLAG_ONLY
    result["MERGE_TABLE"] = MERGE_TABLE
    result["MERGE_SOURCE"] = MERGE_SOURCE
    result["MERGE_CONDITION"] = MERGE_CONDITION
    result["MERGE_WHENS"] = MERGE_WHENS
    result["MERGE_WITH"] = MERGE_WITH
    result["MERGE_SLOTS"] = MERGE_SLOTS
    result["MATCHED_CONDITION"] = MATCHED_CONDITION
    result["MATCHED_COLUMNS"] = MATCHED_COLUMNS
    result["MATCHED_VALUES"] = MATCHED_VALUES
    result["MATCHED_SLOTS"] = MATCHED_SLOTS
    result["MATCHED_ACTION_NOTHING"] = MATCHED_ACTION_NOTHING
    result["MATCHED_ACTION_UPDATE"] = MATCHED_ACTION_UPDATE
    result["MATCHED_ACTION_DELETE"] = MATCHED_ACTION_DELETE
    result["MATCHED_ACTION_INSERT"] = MATCHED_ACTION_INSERT
    result["CONFLICT_TABLE"] = CONFLICT_TABLE
    result["CONFLICT_INDEXED_COLUMNS"] = CONFLICT_INDEXED_COLUMNS
    result["CONFLICT_INDEX_WHERE"] = CONFLICT_INDEX_WHERE
    result["CONFLICT_COLUMNS"] = CONFLICT_COLUMNS
    result["CONFLICT_VALUES"] = CONFLICT_VALUES
    result["CONFLICT_WHERE"] = CONFLICT_WHERE
    result["CONFLICT_SLOTS"] = CONFLICT_SLOTS
    result["WINDOW_PARTITION"] = WINDOW_PARTITION
    result["WINDOW_ORDER_BY"] = WINDOW_ORDER_BY
    result["WINDOW_START"] = WINDOW_START
    result["WINDOW_END"] = WINDOW_END
    result["WINDOW_SLOTS"] = WINDOW_SLOTS
    result["AGGREGATE_EXPRESSION"] = AGGREGATE_EXPRESSION
    result["AGGREGATE_ORDER"] = AGGREGATE_ORDER
    result["AGGREGATE_WITHIN"] = AGGREGATE_WITHIN
    result["AGGREGATE_FILTER"] = AGGREGATE_FILTER
    result["AGGREGATE_WINDOW"] = AGGREGATE_WINDOW
    result["AGGREGATE_SLOTS"] = AGGREGATE_SLOTS
    result["AGGREGATE_FLAG_DISTINCT"] = AGGREGATE_FLAG_DISTINCT
    result["WINDOW_FUNCTION_ARGS"] = WINDOW_FUNCTION_ARGS
    result["WINDOW_FUNCTION_FILTER"] = WINDOW_FUNCTION_FILTER
    result["WINDOW_FUNCTION_WINDOW"] = WINDOW_FUNCTION_WINDOW
    result["WINDOW_FUNCTION_SLOTS"] = WINDOW_FUNCTION_SLOTS
    result["TRIM_EXPRESSION"] = TRIM_EXPRESSION
    result["TRIM_CHARACTERS"] = TRIM_CHARACTERS
    result["TRIM_SLOTS"] = TRIM_SLOTS
    result["LIKE_LEFT"] = LIKE_LEFT
    result["LIKE_RIGHT"] = LIKE_RIGHT
    result["LIKE_ESCAPE"] = LIKE_ESCAPE
    result["LIKE_SLOTS"] = LIKE_SLOTS
    result["BETWEEN_OPERAND"] = BETWEEN_OPERAND
    result["BETWEEN_LEFT"] = BETWEEN_LEFT
    result["BETWEEN_RIGHT"] = BETWEEN_RIGHT
    result["BETWEEN_SLOTS"] = BETWEEN_SLOTS
    result["LATERAL_INNER"] = LATERAL_INNER
    result["LATERAL_SLOTS"] = LATERAL_SLOTS
    result["FOR_TABLES"] = FOR_TABLES
    result["FOR_SLOTS"] = FOR_SLOTS
    result["FOR_FLAG_NOWAIT"] = FOR_FLAG_NOWAIT
    result["WITH_QUERY"] = WITH_QUERY
    result["WITH_COLUMNS"] = WITH_COLUMNS
    result["WITH_SLOTS"] = WITH_SLOTS
    result["WITH_FLAG_RECURSIVE"] = WITH_FLAG_RECURSIVE
    result["JOIN_LEFT"] = JOIN_LEFT
    result["JOIN_RIGHT"] = JOIN_RIGHT
    result["JOIN_CONDITION"] = JOIN_CONDITION
    result["JOIN_SLOTS"] = JOIN_SLOTS
    result["LIMIT_STYLE_LIMIT"] = LIMIT_STYLE_LIMIT
    result["LIMIT_STYLE_FETCH"] = LIMIT_STYLE_FETCH
    result["LIMIT_STYLE_ROWNUM"] = LIMIT_STYLE_ROWNUM
    return result
