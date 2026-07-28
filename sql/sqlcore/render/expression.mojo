"""Rendering of expression nodes."""

from std.python import PythonObject

from ..opcode import (
    AGGREGATE_EXPRESSION,
    AGGREGATE_FILTER,
    AGGREGATE_FLAG_DISTINCT,
    AGGREGATE_ORDER,
    AGGREGATE_WINDOW,
    AGGREGATE_WITHIN,
    BETWEEN_LEFT,
    BETWEEN_OPERAND,
    BETWEEN_RIGHT,
    LIKE_ESCAPE,
    LIKE_LEFT,
    LIKE_RIGHT,
    OP_AGGREGATE,
    OP_AS,
    OP_AT_TIME_ZONE,
    OP_BETWEEN,
    OP_BINARY,
    OP_CASE,
    OP_CAST,
    OP_COLLATE,
    OP_COLUMN,
    OP_CONDITIONAL,
    OP_CONFLICT,
    OP_CUBE,
    OP_EXCLUDED,
    OP_EXCLUDED_COLUMN,
    OP_EXTRACT,
    OP_FOR,
    OP_FUNCTION,
    OP_FUNCTION_KEYWORD,
    OP_FUNCTION_NOT_CALLABLE,
    OP_GROUPING,
    OP_GROUPING_SET,
    OP_IS,
    OP_JOIN,
    OP_LATERAL,
    OP_LIKE,
    OP_LIST,
    OP_LITERAL,
    OP_MATCHED,
    OP_NARY,
    OP_NONE,
    OP_NULL,
    OP_ORDER,
    OP_PARAM,
    OP_RAW,
    OP_ROLLUP,
    OP_ROLLUP_ITEM,
    OP_STAR,
    OP_TABLE,
    OP_TRIM,
    OP_UNARY,
    OP_WINDOW,
    OP_WINDOW_FUNCTION,
    OP_WITH,
    TRIM_CHARACTERS,
    TRIM_EXPRESSION,
    WINDOW_FUNCTION_ARGS,
    WINDOW_FUNCTION_FILTER,
    WINDOW_FUNCTION_WINDOW,
    is_statement,
)
from ..program import Tree
from ..text import qualified_table, quote_identifier, quote_qualified
from .context import Context
from .relation import render_for, render_from_item, render_window
from .statement import render_conflict, render_matched, render_query

comptime LITERAL_PLAIN = 0
comptime LITERAL_TRUE = 1
comptime LITERAL_FALSE = 2


def render_arg(node: Tree, mut ctx: Context) raises -> String:
    """Render a value in argument position, turning params into markers."""
    if node.op == OP_PARAM:
        return ctx.push(node.payload())
    if node.op == OP_LITERAL:
        if ctx.flavor.no_boolean:
            if node.i0 == LITERAL_TRUE:
                return String("(1 = 1)")
            if node.i0 == LITERAL_FALSE:
                return String("(1 != 1)")
        return ctx.push(node.payload())
    return render_expr(node, ctx)


def _needs_parentheses(op: Int) -> Bool:
    return (
        op == OP_BINARY
        or op == OP_NARY
        or op == OP_BETWEEN
        or op == OP_IS
        or op == OP_LIKE
    )


def render_operand(node: Tree, mut ctx: Context) raises -> String:
    """Render a value that may need parentheses inside a larger operator."""
    var op = node.op
    var result = render_arg(node, ctx)
    if _needs_parentheses(op):
        return String("(") + result + ")"
    return result


def render_list(
    node: Tree, mut ctx: Context, separator: String = ", "
) raises -> String:
    """Render every child of a list node, comma separated by default."""
    var result = String("")
    for i in range(node.count()):
        if i > 0:
            result += separator
        result += render_arg(node.kid(i)[], ctx)
    return result


def _as_clause(ctx: Context) -> String:
    return String(" ") if ctx.flavor.no_as else String(" AS ")


def render_expr(node: Tree, mut ctx: Context) raises -> String:
    var op = node.op

    if op == OP_PARAM or op == OP_LITERAL:
        return render_arg(node, ctx)
    if op == OP_NULL:
        return String("NULL")
    if op == OP_STAR:
        return String("*")
    if op == OP_RAW:
        return node.s0
    if op == OP_TABLE:
        return qualified_table(node.s0, node.s1, node.s2)
    if op == OP_EXCLUDED:
        return quote_identifier("EXCLUDED")
    if op == OP_EXCLUDED_COLUMN:
        return quote_qualified("EXCLUDED", node.s0)
    if op == OP_COLUMN:
        var name = node.s0
        var from_node = node.kid(0)
        var alias_value = ctx.aliases.get(from_node[].i1, ctx.aliases.active)
        if alias_value != "":
            return quote_qualified(alias_value, name)
        return quote_identifier(name) if name != "*" else String("*")
    if op == OP_LIST:
        return String("(") + render_list(node, ctx) + ")"

    if op == OP_BINARY:
        return _render_binary(node, ctx)
    if op == OP_UNARY:
        return _render_unary(node, ctx)
    if op == OP_NARY:
        var operator = node.s0
        var result = String("")
        for i in range(node.count()):
            if i > 0:
                result += String(" ") + operator + " "
            var kid = node.kid(i)
            var nested = render_arg(kid[], ctx)
            if _needs_parentheses(kid[].op):
                nested = String("(") + nested + ")"
            result += nested
        return result
    if op == OP_BETWEEN:
        var operand = render_operand(node.kid(BETWEEN_OPERAND)[], ctx)
        var left = render_operand(node.kid(BETWEEN_LEFT)[], ctx)
        var right = render_operand(node.kid(BETWEEN_RIGHT)[], ctx)
        return operand + " " + node.s0 + " " + left + " AND " + right
    if op == OP_IS:
        var left = render_operand(node.kid(0)[], ctx)
        return left + " " + node.s0 + " " + node.s1
    if op == OP_LIKE:
        return _render_like(node, ctx)
    if op == OP_AS:
        return (
            render_arg(node.kid(0)[], ctx)
            + _as_clause(ctx)
            + quote_identifier(node.s0)
        )
    if op == OP_CAST:
        return (
            String("CAST(")
            + render_arg(node.kid(0)[], ctx)
            + " AS "
            + node.s0
            + ")"
        )
    if op == OP_COLLATE:
        return (
            render_arg(node.kid(0)[], ctx)
            + " COLLATE "
            + quote_identifier(node.s0)
        )
    if op == OP_AT_TIME_ZONE:
        return (
            render_arg(node.kid(0)[], ctx)
            + " AT TIME ZONE "
            + render_arg(node.kid(1)[], ctx)
        )
    if op == OP_ORDER:
        return _render_order(node, ctx)
    if op == OP_CASE:
        var result = String("CASE ")
        for i in range(node.i0):
            result += "WHEN "
            result += render_arg(node.kid(i * 2)[], ctx)
            result += " THEN "
            result += render_arg(node.kid(i * 2 + 1)[], ctx)
            result += " "
        var else_node = node.kid(node.i0 * 2)
        if else_node[].op != OP_NONE:
            result += "ELSE " + render_arg(else_node[], ctx) + " "
        return result + "END"
    if op == OP_CONDITIONAL:
        return node.s0 + "(" + render_list(node, ctx) + ")"

    if op == OP_FUNCTION or op == OP_FUNCTION_KEYWORD:
        return _render_function(node, ctx)
    if op == OP_FUNCTION_NOT_CALLABLE:
        return node.s0
    if op == OP_TRIM:
        return (
            node.s0
            + "("
            + node.s1
            + " "
            + render_arg(node.kid(TRIM_CHARACTERS)[], ctx)
            + " FROM "
            + render_arg(node.kid(TRIM_EXPRESSION)[], ctx)
            + ")"
        )
    if op == OP_EXTRACT:
        return (
            String("EXTRACT(")
            + node.s0
            + " FROM "
            + render_arg(node.kid(0)[], ctx)
            + ")"
        )
    if op == OP_AGGREGATE:
        return _render_aggregate(node, ctx)
    if op == OP_WINDOW_FUNCTION:
        return _render_window_function(node, ctx)
    if op == OP_WINDOW:
        return render_window(node, ctx)

    if op == OP_GROUPING:
        return String("GROUPING SETS (") + render_list(node, ctx) + ")"
    if op == OP_GROUPING_SET or op == OP_ROLLUP_ITEM:
        return String("(") + render_list(node, ctx) + ")"
    if op == OP_ROLLUP:
        return String("ROLLUP (") + render_list(node, ctx) + ")"
    if op == OP_CUBE:
        return String("CUBE (") + render_list(node, ctx) + ")"

    if op == OP_JOIN or op == OP_LATERAL or op == OP_WITH:
        return render_from_item(node, ctx)
    if op == OP_FOR:
        return render_for(node, ctx)
    if op == OP_CONFLICT:
        return render_conflict(node, ctx)
    if op == OP_MATCHED:
        return render_matched(node, ctx)
    if is_statement(op):
        return String("(") + render_query(node, ctx) + ")"
    raise Error("unsupported Mojo SQL node: " + String(op))


def _render_binary(node: Tree, mut ctx: Context) raises -> String:
    var operator = node.s0
    var left_node = node.kid(0)
    var right_node = node.kid(1)

    if operator == "IN" or operator == "NOT IN":
        var left = render_operand(left_node[], ctx)
        var result = left + " " + operator + " "
        if right_node[].op == OP_LIST:
            return result + "(" + render_list(right_node[], ctx) + ")"
        return result + render_arg(right_node[], ctx)

    var left = render_operand(left_node[], ctx)
    if operator == "ILIKE" or operator == "NOT ILIKE":
        if not ctx.flavor.ilike:
            var mapped = String("LIKE") if operator == "ILIKE" else String(
                "NOT LIKE"
            )
            var right_value = render_operand(right_node[], ctx)
            return (
                "UPPER("
                + left
                + ") "
                + mapped
                + " UPPER("
                + right_value
                + ")"
            )
    if operator == "%":
        operator = String("%") if ctx.flavor.qmark else String("%%")
    if operator == "=" or operator == "!=":
        if left_node[].op == OP_NULL:
            var right_value = render_operand(right_node[], ctx)
            return right_value + (
                " IS NULL" if operator == "=" else " IS NOT NULL"
            )
        if right_node[].op == OP_NULL:
            return left + (" IS NULL" if operator == "=" else " IS NOT NULL")
    var right = render_operand(right_node[], ctx)
    return left + " " + operator + " " + right


def _render_unary(node: Tree, mut ctx: Context) raises -> String:
    var operator = node.s0
    var operand_node = node.kid(0)
    if operator == "ANY" or operator == "ALL":
        if operand_node[].op == OP_PARAM:
            var marker = ctx.push(operand_node[].payload())
            return operator + " (" + marker + ")"
    var operand = render_operand(operand_node[], ctx)
    return operator + " " + operand


def _render_like(node: Tree, mut ctx: Context) raises -> String:
    var operator = node.s0
    var left = render_operand(node.kid(LIKE_LEFT)[], ctx)
    var right = render_operand(node.kid(LIKE_RIGHT)[], ctx)
    if operator == "ILIKE" or operator == "NOT ILIKE":
        if not ctx.flavor.ilike:
            left = "UPPER(" + left + ")"
            operator = String("LIKE") if operator == "ILIKE" else String(
                "NOT LIKE"
            )
            right = "UPPER(" + right + ")"
    var result = left + " " + operator + " " + right
    if node.has(LIKE_ESCAPE):
        result += " ESCAPE " + render_arg(node.kid(LIKE_ESCAPE)[], ctx)
    elif ctx.flavor.escape_empty:
        result += " ESCAPE " + ctx.push(PythonObject(""))
    return result


def _render_order(node: Tree, mut ctx: Context) raises -> String:
    var order_name = node.s0
    var base_node = node.kid(0)
    if not ctx.flavor.null_ordering and (
        order_name == "NULLS FIRST" or order_name == "NULLS LAST"
    ):
        var null_base = base_node
        var inner_order = String("")
        if base_node[].op == OP_ORDER:
            null_base = base_node[].kid(0)
            inner_order = base_node[].s0
        var first = render_arg(null_base[], ctx)
        var result = String("CASE WHEN ") + first + " IS NULL THEN "
        result += ctx.placeholder() + " ELSE " + ctx.placeholder() + " END ASC, "
        if order_name == "NULLS FIRST":
            ctx.params.append(PythonObject(0))
            ctx.params.append(PythonObject(1))
        else:
            ctx.params.append(PythonObject(1))
            ctx.params.append(PythonObject(0))
        var final_base = render_arg(null_base[], ctx)
        if inner_order != "":
            final_base += " " + inner_order
        return result + final_base
    var base = render_arg(base_node[], ctx)
    if order_name != "":
        return base + " " + order_name
    return base


def _render_function(node: Tree, mut ctx: Context) raises -> String:
    var name = node.s0
    var keyword_form = node.op == OP_FUNCTION_KEYWORD
    var step = 2 if keyword_form else 1
    var count = node.count() // step
    var result = name + "("
    for i in range(count):
        if i > 0:
            result += " " if keyword_form else ", "
        if keyword_form:
            var keyword = node.kid(i * 2)[].s0
            if keyword != "":
                result += keyword + " "
        result += render_arg(node.kid(i * step + step - 1)[], ctx)
    return result + ")"


def _render_over(node: Tree, mut ctx: Context) raises -> String:
    var alias_value = ctx.aliases.get(node.i1, False)
    if alias_value != "":
        return String(" OVER ") + quote_identifier(alias_value)
    return String(" OVER (") + render_window(node, ctx) + ")"


def _render_aggregate(node: Tree, mut ctx: Context) raises -> String:
    var name = node.s0
    var expression = node.kid(AGGREGATE_EXPRESSION)
    var filter_node = node.kid(AGGREGATE_FILTER)
    var has_filter = filter_node[].op != OP_NONE
    var use_filter = has_filter and ctx.flavor.filter_

    var result = name + "("
    if node.i0 & AGGREGATE_FLAG_DISTINCT != 0:
        result += "DISTINCT "
    if has_filter and not use_filter:
        result += _render_filter_case(node, ctx)
    else:
        result += render_arg(expression[], ctx)
    var order_node = node.kid(AGGREGATE_ORDER)
    if order_node[].count() > 0:
        result += " ORDER BY " + render_list(order_node[], ctx)
    result += ")"
    var within_node = node.kid(AGGREGATE_WITHIN)
    if within_node[].count() > 0:
        result += " WITHIN GROUP (ORDER BY "
        result += render_list(within_node[], ctx)
        result += ")"
    if use_filter:
        result += " FILTER (WHERE " + render_arg(filter_node[], ctx) + ")"
    var window_node = node.kid(AGGREGATE_WINDOW)
    if window_node[].op != OP_NONE:
        result += _render_over(window_node[], ctx)
    return result


def _render_filter_case(node: Tree, mut ctx: Context) raises -> String:
    """`COUNT(x) FILTER (WHERE c)` lowered to `COUNT(CASE WHEN c THEN x END)`."""
    var name = node.s0
    var expression = node.kid(AGGREGATE_EXPRESSION)
    var filter_node = node.kid(AGGREGATE_FILTER)
    var expression_op = expression[].op
    var counts_star = name == "COUNT" and expression_op == OP_STAR
    var result = String("CASE WHEN ")
    result += render_arg(filter_node[], ctx)
    result += " THEN "
    if counts_star:
        result += ctx.push(PythonObject(1))
    else:
        result += render_arg(expression[], ctx)
    return result + " END"


def _render_window_function(node: Tree, mut ctx: Context) raises -> String:
    var result = node.s0 + "("
    result += render_list(node.kid(WINDOW_FUNCTION_ARGS)[], ctx)
    result += ")"
    var filter_node = node.kid(WINDOW_FUNCTION_FILTER)
    if filter_node[].op != OP_NONE:
        result += " FILTER (WHERE " + render_arg(filter_node[], ctx) + ")"
    var window_node = node.kid(WINDOW_FUNCTION_WINDOW)
    if window_node[].op != OP_NONE:
        result += _render_over(window_node[], ctx)
    return result
