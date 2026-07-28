"""Rendering of FROM items, windows and locking clauses."""

from std.python import PythonObject

from ..opcode import (
    FOR_FLAG_NOWAIT,
    FOR_TABLES,
    JOIN_CONDITION,
    JOIN_LEFT,
    JOIN_RIGHT,
    LATERAL_INNER,
    OP_FUNCTION,
    OP_FUNCTION_KEYWORD,
    OP_JOIN,
    OP_LATERAL,
    OP_PARAM,
    OP_TABLE,
    OP_WITH,
    WINDOW_END,
    WINDOW_ORDER_BY,
    WINDOW_PARTITION,
    WINDOW_START,
    WITH_COLUMNS,
    WITH_FLAG_RECURSIVE,
    WITH_QUERY,
    is_statement,
)
from ..program import Tree
from ..text import qualified_table, quote_identifier
from .context import Context
from .expression import render_arg, render_expr, render_list
from .statement import render_query


def _as_clause(ctx: Context) -> String:
    return String(" ") if ctx.flavor.no_as else String(" AS ")


def assign_from(node: Tree, mut ctx: Context) raises:
    """Reserve aliases in FROM order, descending into joins."""
    if node.op == OP_JOIN:
        assign_from(node.kid(JOIN_LEFT)[], ctx)
        assign_from(node.kid(JOIN_RIGHT)[], ctx)
    else:
        _ = ctx.aliases.get(node.i1, True)


def render_from_item(node: Tree, mut ctx: Context) raises -> String:
    var op = node.op

    if op == OP_TABLE:
        var result = qualified_table(node.s0, node.s1, node.s2)
        var alias_value = ctx.aliases.get(node.i1, True)
        if alias_value != "":
            result += _as_clause(ctx) + quote_identifier(alias_value)
        return result

    if op == OP_WITH:
        var alias_value = ctx.aliases.get(node.i1, True)
        return quote_identifier(alias_value) + _as_clause(
            ctx
        ) + quote_identifier(alias_value)

    if op == OP_FUNCTION or op == OP_FUNCTION_KEYWORD:
        var result = render_expr(node, ctx)
        var alias_value = ctx.aliases.get(node.i1, True)
        if alias_value != "":
            result += _as_clause(ctx) + quote_identifier(alias_value)
        var definitions = node.s1
        if definitions != "":
            result += " (" + definitions + ")"
        return result

    if op == OP_LATERAL:
        var inner = node.kid(LATERAL_INNER)
        var alias_value = ctx.aliases.get(node.i1, True)
        var result = String("LATERAL ")
        if is_statement(inner[].op):
            result += "(" + render_query(inner[], ctx) + ")"
        elif inner[].op == OP_FUNCTION or inner[].op == OP_FUNCTION_KEYWORD:
            result += render_expr(inner[], ctx)
            var definitions = inner[].s1
            if definitions != "":
                result += " (" + definitions + ")"
        else:
            result += render_from_item(inner[], ctx)
        return result + _as_clause(ctx) + quote_identifier(alias_value)

    if op == OP_JOIN:
        var left_node = node.kid(JOIN_LEFT)
        var right_node = node.kid(JOIN_RIGHT)
        assign_from(left_node[], ctx)
        assign_from(right_node[], ctx)
        var left = render_from_item(left_node[], ctx)
        var right = render_from_item(right_node[], ctx)
        var result = left + " " + node.s0 + " JOIN " + right
        if node.has(JOIN_CONDITION):
            result += " ON " + render_arg(node.kid(JOIN_CONDITION)[], ctx)
        return result

    if is_statement(op):
        var alias_value = ctx.aliases.get(node.i1, True)
        var result = String("(") + render_query(node, ctx) + ")"
        return result + _as_clause(ctx) + quote_identifier(alias_value)

    raise Error("invalid FROM item: " + String(op))


def render_window(node: Tree, mut ctx: Context) raises -> String:
    var result = String("")
    var partition = node.kid(WINDOW_PARTITION)
    if partition[].count() > 0:
        result += "PARTITION BY " + render_list(partition[], ctx)
    var order = node.kid(WINDOW_ORDER_BY)
    if order[].count() > 0:
        result += " ORDER BY " + render_list(order[], ctx)
    var frame = node.s0
    if frame != "":
        result += " " + frame + " BETWEEN "
        result += _render_bound(node.kid(WINDOW_START)[], ctx, True)
        result += " AND "
        result += _render_bound(node.kid(WINDOW_END)[], ctx, False)
    var exclude = node.s1
    if exclude != "":
        result += " EXCLUDE " + exclude
    return result


def _render_bound(node: Tree, mut ctx: Context, start: Bool) raises -> String:
    """Render one window frame bound.

    An absent bound is unbounded, `0` is the current row and any other value
    becomes a parameter with PRECEDING or FOLLOWING taken from its sign.
    """
    if node.op != OP_PARAM:
        return String("UNBOUNDED PRECEDING") if start else String(
            "UNBOUNDED FOLLOWING"
        )
    var amount = Int(py=node.payload())
    if amount == 0:
        return String("CURRENT ROW")
    var marker = ctx.push(PythonObject(-amount if amount < 0 else amount))
    if amount < 0:
        return marker + " PRECEDING"
    return marker + " FOLLOWING"


def render_for(node: Tree, mut ctx: Context) raises -> String:
    var result = String("FOR ") + node.s0
    var tables = node.kid(FOR_TABLES)
    if tables[].count() > 0:
        result += " OF "
        for i in range(tables[].count()):
            if i > 0:
                result += ", "
            var table = tables[].kid(i)
            result += qualified_table(table[].s0, table[].s1, table[].s2)
    if node.i0 & FOR_FLAG_NOWAIT != 0:
        result += " NOWAIT"
    return result


def render_with_clause(list_node: Tree, mut ctx: Context) raises -> String:
    """Render the WITH prefix of a statement, empty when there is none."""
    if list_node.count() == 0:
        return String("")
    var recursive = False
    for i in range(list_node.count()):
        if list_node.kid(i)[].i0 & WITH_FLAG_RECURSIVE != 0:
            recursive = True
    var result = String("WITH") + (
        " RECURSIVE " if recursive else " "
    )
    for i in range(list_node.count()):
        if i > 0:
            result += ", "
        var with_node = list_node.kid(i)
        var alias_value = ctx.aliases.get(with_node[].i1, True)
        result += quote_identifier(alias_value)
        var columns = with_node[].kid(WITH_COLUMNS)
        if columns[].count() > 0:
            result += " ("
            for j in range(columns[].count()):
                if j > 0:
                    result += ", "
                result += quote_identifier(columns[].kid(j)[].s0)
            result += ")"
        result += " AS ("
        result += render_query(with_node[].kid(WITH_QUERY)[], ctx)
        result += ")"
    return result + " "
