"""Rendering of complete statements."""

from std.python import PythonObject

from ..flavor import LIMIT_STYLE_LIMIT, LIMIT_STYLE_ROWNUM
from ..opcode import (
    COMBINING_FLAG_ALL,
    COMBINING_LIMIT,
    COMBINING_OFFSET,
    COMBINING_ORDER_BY,
    COMBINING_QUERIES,
    COMBINING_WITH,
    CONFLICT_COLUMNS,
    CONFLICT_INDEXED_COLUMNS,
    CONFLICT_INDEX_WHERE,
    CONFLICT_VALUES,
    CONFLICT_WHERE,
    DELETE_FLAG_ONLY,
    DELETE_RETURNING,
    DELETE_TABLE,
    DELETE_USING,
    DELETE_WHERE,
    DELETE_WITH,
    INSERT_COLUMNS,
    INSERT_CONFLICT,
    INSERT_RETURNING,
    INSERT_TABLE,
    INSERT_VALUES,
    INSERT_WITH,
    MATCHED_ACTION_DELETE,
    MATCHED_ACTION_INSERT,
    MATCHED_ACTION_NOTHING,
    MATCHED_ACTION_UPDATE,
    MATCHED_COLUMNS,
    MATCHED_CONDITION,
    MATCHED_VALUES,
    MERGE_CONDITION,
    MERGE_SOURCE,
    MERGE_TABLE,
    MERGE_WHENS,
    MERGE_WITH,
    OP_AGGREGATE,
    OP_DELETE,
    OP_INSERT,
    OP_MERGE,
    OP_UPDATE,
    OP_AS,
    OP_EXCEPT,
    OP_INTERSECT,
    OP_LIST,
    OP_NARY,
    OP_NONE,
    OP_PARAM,
    OP_SELECT,
    OP_TABLE,
    OP_UNION,
    OP_VALUES,
    OP_WINDOW_FUNCTION,
    SELECT_COLUMNS,
    SELECT_DISTINCT_ON,
    SELECT_FLAG_DISTINCT,
    SELECT_FLAG_FROM_DIRECT,
    SELECT_FOR,
    SELECT_FROM,
    SELECT_GROUP_BY,
    SELECT_HAVING,
    SELECT_LIMIT,
    SELECT_OFFSET,
    SELECT_ORDER_BY,
    SELECT_WHERE,
    SELECT_WINDOWS,
    SELECT_WITH,
    UPDATE_COLUMNS,
    UPDATE_FROM,
    UPDATE_RETURNING,
    UPDATE_TABLE,
    UPDATE_VALUES,
    UPDATE_WHERE,
    UPDATE_WITH,
    is_combining,
    is_statement,
)
from ..program import Tree, TreePointer
from ..text import qualified_table, quote_identifier, quote_qualified
from .context import Context
from .expression import render_arg, render_list, render_operand
from .relation import (
    assign_from,
    render_for,
    render_from_item,
    render_window,
    render_with_clause,
)

comptime SYNTHETIC_BASE = 1 << 40
comptime SYNTHETIC_MIDDLE = 1 << 41


def render_query(node: Tree, mut ctx: Context) raises -> String:
    """Render a statement, opening an alias scope when none is active."""
    var op = node.op
    var started = not ctx.aliases.active
    if started:
        ctx.aliases.begin()
    var result: String
    if op == OP_SELECT:
        result = render_select(node, ctx)
    elif op == OP_VALUES:
        result = render_values(node, ctx)
    elif op == OP_INSERT:
        result = render_insert(node, ctx)
    elif op == OP_UPDATE:
        result = render_update(node, ctx)
    elif op == OP_DELETE:
        result = render_delete(node, ctx)
    elif is_combining(op):
        result = render_combining(node, ctx)
    elif op == OP_MERGE:
        result = render_merge(node, ctx)
    else:
        raise Error("unsupported Mojo SQL query: " + String(op))
    if started:
        ctx.aliases.end()
    return result


def _param_int(node: Tree) raises -> Int:
    return Int(py=node.payload())


def _has_offset(node: Tree, slot: Int) raises -> Bool:
    if not node.has(slot):
        return False
    return _param_int(node.kid(slot)[]) != 0


def _collect_windows(
    node: Tree, mut keys: List[Int], mut nodes: List[TreePointer]
) raises:
    """Window of a column, when the column itself is the window expression.

    A window nested deeper inside an expression is rendered inline, matching
    python-sql, which only inspects the projected columns.
    """
    if node.op == OP_AS:
        if node.count() > 0:
            _collect_windows(node.kid(0)[], keys, nodes)
        return
    if node.op != OP_AGGREGATE and node.op != OP_WINDOW_FUNCTION:
        return
    var last = node.count() - 1
    if last < 0:
        return
    var window = node.kid(last)
    if window[].op == OP_NONE:
        return
    var key = window[].i1
    for item in keys:
        if item == key:
            return
    keys.append(key)
    nodes.append(window)


def _select_windows(node: Tree) raises -> List[TreePointer]:
    """Explicit windows first, then the ones inferred from the columns."""
    var keys = List[Int]()
    var nodes = List[TreePointer]()
    var explicit = node.kid(SELECT_WINDOWS)
    for i in range(explicit[].count()):
        var window = explicit[].kid(i)
        keys.append(window[].i1)
        nodes.append(window)
    var columns = node.kid(SELECT_COLUMNS)
    for i in range(columns[].count()):
        _collect_windows(columns[].kid(i)[], keys, nodes)
    return nodes^


def render_select(node: Tree, mut ctx: Context) raises -> String:
    if ctx.flavor.limit_style == LIMIT_STYLE_ROWNUM:
        if node.has(SELECT_LIMIT) or _has_offset(node, SELECT_OFFSET):
            return _render_rownum(node, ctx)
    return _render_select_body(node, ctx, True, True)


def _render_select_body(
    node: Tree,
    mut ctx: Context,
    with_limit: Bool,
    with_for: Bool,
) raises -> String:
    var from_node = node.kid(SELECT_FROM)
    var direct = node.i0 & SELECT_FLAG_FROM_DIRECT != 0

    var direct_sql = String("")
    var direct_params = List[PythonObject]()
    if direct and from_node[].count() > 0:
        var saved = ctx.params^
        ctx.params = List[PythonObject]()
        direct_sql = render_query(from_node[].kid(0)[], ctx)
        direct_params = ctx.params^
        ctx.params = saved^
    else:
        for i in range(from_node[].count()):
            assign_from(from_node[].kid(i)[], ctx)

    var windows = _select_windows(node)
    for i in range(len(windows)):
        var window = windows[i]
        _ = ctx.aliases.get(window[].i1, True)

    var result = render_with_clause(node.kid(SELECT_WITH)[], ctx)
    result += "SELECT "
    if node.i0 & SELECT_FLAG_DISTINCT != 0:
        result += "DISTINCT "
    var distinct_on = node.kid(SELECT_DISTINCT_ON)
    if distinct_on[].count() > 0:
        result += "ON (" + render_list(distinct_on[], ctx) + ") "

    var columns = node.kid(SELECT_COLUMNS)
    if columns[].count() == 0:
        result += "*"
    else:
        result += render_list(columns[], ctx)

    if from_node[].count() > 0:
        result += " FROM "
        if direct:
            result += direct_sql
            for value in direct_params:
                ctx.params.append(value)
        else:
            for i in range(from_node[].count()):
                if i > 0:
                    result += ", "
                result += render_from_item(from_node[].kid(i)[], ctx)

    if node.has(SELECT_WHERE):
        result += " WHERE " + render_arg(node.kid(SELECT_WHERE)[], ctx)

    var group = node.kid(SELECT_GROUP_BY)
    if group[].count() > 0:
        result += " GROUP BY "
        for i in range(group[].count()):
            if i > 0:
                result += ", "
            var item = group[].kid(i)
            if item[].op == OP_AS:
                result += _group_by_alias(item[], columns[], ctx)
            else:
                result += render_arg(item[], ctx)

    if node.has(SELECT_HAVING):
        result += " HAVING " + render_arg(node.kid(SELECT_HAVING)[], ctx)

    if len(windows) > 0:
        result += " WINDOW "
        for i in range(len(windows)):
            if i > 0:
                result += ", "
            var window = windows[i]
            var alias_value = ctx.aliases.get(window[].i1, False)
            result += quote_identifier(alias_value) + " AS ("
            result += render_window(window[], ctx)
            result += ")"

    result += _render_order_by(node.kid(SELECT_ORDER_BY)[], ctx)

    if with_limit:
        result += _render_limit(node, SELECT_LIMIT, SELECT_OFFSET, ctx)

    if with_for:
        var for_node = node.kid(SELECT_FOR)
        for i in range(for_node[].count()):
            result += " " + render_for(for_node[].kid(i)[], ctx)
    return result


def _group_by_alias(
    item: Tree, columns: Tree, mut ctx: Context
) raises -> String:
    """`GROUP BY` on an output name uses its ordinal when it is projected."""
    var ordinal = 0
    for j in range(columns.count()):
        var column = columns.kid(j)
        if column[].op == OP_AS and column[].s0 == item.s0:
            ordinal = j + 1
    if ordinal > 0:
        return String(ordinal)
    return quote_identifier(item.s0)


def _render_order_by(order: Tree, mut ctx: Context) raises -> String:
    if order.count() == 0:
        return String("")
    var result = String(" ORDER BY ")
    for i in range(order.count()):
        if i > 0:
            result += ", "
        var item = order.kid(i)
        if item[].op == OP_AS:
            result += quote_identifier(item[].s0)
        else:
            result += render_arg(item[], ctx)
    return result


def _render_limit(
    node: Tree, limit_slot: Int, offset_slot: Int, mut ctx: Context
) raises -> String:
    var result = String("")
    var has_limit = node.has(limit_slot)
    var has_offset = _has_offset(node, offset_slot)
    var style = ctx.flavor.limit_style
    if style == LIMIT_STYLE_ROWNUM:
        style = LIMIT_STYLE_LIMIT
    if style == LIMIT_STYLE_LIMIT:
        if has_limit:
            result += " LIMIT " + ctx.push(node.kid(limit_slot)[].payload())
        elif has_offset and ctx.flavor.max_limit >= -1:
            result += " LIMIT " + String(ctx.flavor.max_limit)
        if has_offset:
            result += " OFFSET " + ctx.push(node.kid(offset_slot)[].payload())
    else:
        if has_offset:
            result += " OFFSET (" + ctx.push(
                node.kid(offset_slot)[].payload()
            ) + ") ROWS"
        if has_limit:
            result += " FETCH FIRST (" + ctx.push(
                node.kid(limit_slot)[].payload()
            ) + ") ROWS ONLY"
    return result


def _projection(
    columns: Tree, alias_value: String, all_aliases: Bool
) raises -> String:
    if not all_aliases:
        return quote_qualified(alias_value, "*")
    var result = String("")
    for i in range(columns.count()):
        if i > 0:
            result += ", "
        result += quote_qualified(alias_value, columns.kid(i)[].s0)
    return result


def _render_rownum(node: Tree, mut ctx: Context) raises -> String:
    """Emulate LIMIT/OFFSET with ROWNUM wrappers for Oracle style flavors."""
    var columns = node.kid(SELECT_COLUMNS)
    var all_aliases = columns[].count() > 0
    for i in range(columns[].count()):
        if columns[].kid(i)[].op != OP_AS:
            all_aliases = False

    var has_limit = node.has(SELECT_LIMIT)
    var has_offset = _has_offset(node, SELECT_OFFSET)

    var nested = ctx.aliases.get(node.i1, False) != ""
    var base_key = node.i1 if nested else SYNTHETIC_BASE + node.i1

    var for_node = node.kid(SELECT_FOR)

    if not has_offset:
        var base_alias = ctx.aliases.get(base_key, True)
        var base_sql = _render_select_body(node, ctx, False, False)
        var result = String("SELECT ")
        result += _projection(columns[], base_alias, all_aliases)
        result += " FROM (" + base_sql + ")"
        result += (
            String(" ") if ctx.flavor.no_as else String(" AS ")
        ) + quote_identifier(base_alias)
        result += " WHERE ROWNUM <= " + ctx.push(
            node.kid(SELECT_LIMIT)[].payload()
        )
        for i in range(for_node[].count()):
            result += " " + render_for(for_node[].kid(i)[], ctx)
        return result

    var middle_alias = ctx.aliases.get(SYNTHETIC_MIDDLE + node.i1, True)
    var base_alias = ctx.aliases.get(base_key, True)
    var base_sql = _render_select_body(node, ctx, False, False)

    var middle = String("SELECT ")
    middle += _projection(columns[], base_alias, all_aliases)
    middle += ", ROWNUM AS " + quote_identifier("rnum")
    middle += " FROM (" + base_sql + ")"
    middle += (
        String(" ") if ctx.flavor.no_as else String(" AS ")
    ) + quote_identifier(base_alias)
    if has_limit:
        var max_row = _param_int(node.kid(SELECT_LIMIT)[]) + _param_int(
            node.kid(SELECT_OFFSET)[]
        )
        middle += " WHERE ROWNUM <= " + ctx.push(PythonObject(max_row))

    var result = String("SELECT ")
    result += _projection(columns[], middle_alias, all_aliases)
    result += " FROM (" + middle + ")"
    result += (
        String(" ") if ctx.flavor.no_as else String(" AS ")
    ) + quote_identifier(middle_alias)
    result += " WHERE " + quote_identifier("rnum") + " > " + ctx.push(
        node.kid(SELECT_OFFSET)[].payload()
    )
    for i in range(for_node[].count()):
        result += " " + render_for(for_node[].kid(i)[], ctx)
    return result


def render_values(node: Tree, mut ctx: Context) raises -> String:
    var result = String("VALUES ")
    for i in range(node.count()):
        if i > 0:
            result += ", "
        result += "(" + render_list(node.kid(i)[], ctx) + ")"
    return result


def render_conflict(node: Tree, mut ctx: Context) raises -> String:
    var result = String("ON CONFLICT")
    var indexed = node.kid(CONFLICT_INDEXED_COLUMNS)
    if indexed[].count() > 0:
        result += " ("
        for i in range(indexed[].count()):
            if i > 0:
                result += ", "
            result += quote_identifier(indexed[].kid(i)[].s0)
        result += ")"
        if node.has(CONFLICT_INDEX_WHERE):
            result += " WHERE " + render_arg(
                node.kid(CONFLICT_INDEX_WHERE)[], ctx
            )

    var columns = node.kid(CONFLICT_COLUMNS)
    if columns[].count() == 0:
        return result + " DO NOTHING"
    result += " DO UPDATE SET "
    var values = node.kid(CONFLICT_VALUES)
    if values[].op == OP_VALUES:
        var row = values[].kid(0)
        if columns[].count() == 1:
            result += quote_identifier(columns[].kid(0)[].s0)
            result += " = (" + render_arg(row[].kid(0)[], ctx) + ")"
        else:
            result += "("
            for i in range(columns[].count()):
                if i > 0:
                    result += ", "
                result += quote_identifier(columns[].kid(i)[].s0)
            result += ") = (" + render_list(row[], ctx) + ")"
    else:
        result += "("
        for i in range(columns[].count()):
            if i > 0:
                result += ", "
            result += quote_identifier(columns[].kid(i)[].s0)
        result += ") = (" + render_query(values[], ctx) + ")"

    if node.has(CONFLICT_WHERE):
        result += " WHERE " + render_arg(node.kid(CONFLICT_WHERE)[], ctx)
    return result


def _render_returning(returning: Tree, mut ctx: Context) raises -> String:
    if returning.count() == 0:
        return String("")
    return String(" RETURNING ") + render_list(returning, ctx)


def render_insert(node: Tree, mut ctx: Context) raises -> String:
    var result = render_with_clause(node.kid(INSERT_WITH)[], ctx)
    var table = node.kid(INSERT_TABLE)
    var returning = node.kid(INSERT_RETURNING)
    var needs_alias = returning[].count() > 0 or node.has(INSERT_CONFLICT)

    var values = node.kid(INSERT_VALUES)
    var values_sql: String
    if not node.has(INSERT_VALUES):
        values_sql = String(" DEFAULT VALUES")
    elif values[].op == OP_VALUES:
        values_sql = String(" ") + render_values(values[], ctx)
    else:
        values_sql = String(" ") + render_query(values[], ctx)

    var conflict_sql = String("")
    if node.has(INSERT_CONFLICT):
        conflict_sql = String(" ") + render_conflict(
            node.kid(INSERT_CONFLICT)[], ctx
        )
    var returning_sql = _render_returning(returning[], ctx)

    var alias_value = ctx.aliases.get(table[].i1, needs_alias)
    result += "INSERT INTO " + qualified_table(
        table[].s0, table[].s1, table[].s2
    )
    if alias_value != "":
        result += (
            String(" ") if ctx.flavor.no_as else String(" AS ")
        ) + quote_identifier(alias_value)

    var columns = node.kid(INSERT_COLUMNS)
    if columns[].count() > 0:
        result += " ("
        for i in range(columns[].count()):
            if i > 0:
                result += ", "
            result += quote_identifier(columns[].kid(i)[].s0)
        result += ")"
    return result + values_sql + conflict_sql + returning_sql


def render_update(node: Tree, mut ctx: Context) raises -> String:
    var with_sql = render_with_clause(node.kid(UPDATE_WITH)[], ctx)
    var table = node.kid(UPDATE_TABLE)
    var from_node = node.kid(UPDATE_FROM)
    for i in range(from_node[].count()):
        assign_from(from_node[].kid(i)[], ctx)

    var columns = node.kid(UPDATE_COLUMNS)
    var values = node.kid(UPDATE_VALUES)
    var values_sql = String("")
    for i in range(columns[].count()):
        if i > 0:
            values_sql += ", "
        values_sql += quote_identifier(columns[].kid(i)[].s0)
        values_sql += " = " + render_arg(values[].kid(i)[], ctx)

    var from_sql = String("")
    if from_node[].count() > 0:
        from_sql = String(" FROM ")
        for i in range(from_node[].count()):
            if i > 0:
                from_sql += ", "
            from_sql += render_from_item(from_node[].kid(i)[], ctx)

    var where_sql = String("")
    if node.has(UPDATE_WHERE):
        where_sql = String(" WHERE ") + render_arg(
            node.kid(UPDATE_WHERE)[], ctx
        )
    var returning_sql = _render_returning(node.kid(UPDATE_RETURNING)[], ctx)

    var alias_value = ctx.aliases.get(table[].i1, True)
    var result = with_sql
    result += "UPDATE " + qualified_table(table[].s0, table[].s1, table[].s2)
    result += " AS " + quote_identifier(alias_value) + " SET "
    return result + values_sql + from_sql + where_sql + returning_sql


def render_delete(node: Tree, mut ctx: Context) raises -> String:
    var table = node.kid(DELETE_TABLE)
    ctx.aliases.exclude(table[].i1)
    var result = render_with_clause(node.kid(DELETE_WITH)[], ctx)
    result += "DELETE FROM"
    if node.i0 & DELETE_FLAG_ONLY != 0:
        result += " ONLY"
    result += " " + qualified_table(table[].s0, table[].s1, table[].s2)
    var using = node.kid(DELETE_USING)
    if using[].count() > 0:
        result += " USING "
        for i in range(using[].count()):
            if i > 0:
                result += ", "
            result += render_from_item(using[].kid(i)[], ctx)
    if node.has(DELETE_WHERE):
        result += " WHERE " + render_arg(node.kid(DELETE_WHERE)[], ctx)
    return result + _render_returning(node.kid(DELETE_RETURNING)[], ctx)


def render_combining(node: Tree, mut ctx: Context) raises -> String:
    var result = render_with_clause(node.kid(COMBINING_WITH)[], ctx)
    var operator: String
    if node.op == OP_UNION:
        operator = String("UNION")
    elif node.op == OP_INTERSECT:
        operator = String("INTERSECT")
    else:
        operator = String("EXCEPT")
    if node.i0 & COMBINING_FLAG_ALL != 0:
        operator += " ALL"
    var queries = node.kid(COMBINING_QUERIES)
    for i in range(queries[].count()):
        if i > 0:
            result += " " + operator + " "
        result += render_query(queries[].kid(i)[], ctx)
    result += _render_order_by(node.kid(COMBINING_ORDER_BY)[], ctx)
    result += _render_limit(node, COMBINING_LIMIT, COMBINING_OFFSET, ctx)
    return result


def _render_merge_condition(node: Tree, mut ctx: Context) raises -> String:
    """The ON clause never wraps its top level conjunction in parentheses."""
    if node.op != OP_NARY:
        return render_arg(node, ctx)
    var result = String("")
    for i in range(node.count()):
        if i > 0:
            result += " " + node.s0 + " "
        result += render_operand(node.kid(i)[], ctx)
    return result


def render_matched(node: Tree, mut ctx: Context) raises -> String:
    var result = String("WHEN ")
    result += "NOT MATCHED" if node.i1 != 0 else "MATCHED"
    if node.has(MATCHED_CONDITION):
        var condition = node.kid(MATCHED_CONDITION)
        if condition[].op == OP_NARY:
            result += " AND " + _render_merge_condition(condition[], ctx)
        else:
            result += " AND " + render_arg(condition[], ctx)
    result += " THEN "
    if node.i0 == MATCHED_ACTION_NOTHING:
        return result + "DO NOTHING"
    if node.i0 == MATCHED_ACTION_DELETE:
        return result + "DELETE"

    var columns = node.kid(MATCHED_COLUMNS)
    var values = node.kid(MATCHED_VALUES)
    if node.i0 == MATCHED_ACTION_INSERT:
        result += "INSERT ("
        for i in range(columns[].count()):
            if i > 0:
                result += ", "
            result += quote_identifier(columns[].kid(i)[].s0)
        result += ")"
        if not node.has(MATCHED_VALUES):
            return result + " DEFAULT VALUES"
        return result + " " + render_values(values[], ctx)

    result += "UPDATE SET "
    var row = values[].kid(0)
    for i in range(columns[].count()):
        if i > 0:
            result += ", "
        result += quote_identifier(columns[].kid(i)[].s0)
        result += " = " + render_arg(row[].kid(i)[], ctx)
    return result


def render_merge(node: Tree, mut ctx: Context) raises -> String:
    var source = node.kid(MERGE_SOURCE)

    var saved = ctx.params^
    ctx.params = List[PythonObject]()
    var source_sql: String
    if is_statement(source[].op):
        source_sql = String("(") + render_query(source[], ctx) + ")"
    else:
        source_sql = qualified_table(source[].s0, source[].s1, source[].s2)
    var condition_sql = _render_merge_condition(
        node.kid(MERGE_CONDITION)[], ctx
    )
    var pre_params = ctx.params^
    ctx.params = saved^

    var with_sql = render_with_clause(node.kid(MERGE_WITH)[], ctx)
    for value in pre_params:
        ctx.params.append(value)

    var target_sql = render_from_item(node.kid(MERGE_TABLE)[], ctx)
    var source_alias = ctx.aliases.get(source[].i1, True)
    source_sql += (
        String(" ") if ctx.flavor.no_as else String(" AS ")
    ) + quote_identifier(source_alias)

    var result = with_sql
    result += "MERGE INTO " + target_sql
    result += " USING " + source_sql
    result += " ON " + condition_sql
    var whens = node.kid(MERGE_WHENS)
    for i in range(whens[].count()):
        result += " " + render_matched(whens[].kid(i)[], ctx)
    return result
