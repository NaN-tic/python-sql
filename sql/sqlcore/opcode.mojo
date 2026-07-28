"""Opcodes and slot layout for the native SQL AST.

Every node in a `Program` is described by an opcode from this module.  Child
slots are positional and fixed per opcode, so builders and renderers agree on
the meaning of `Node.kid_start + n` without any name lookup at render time.
"""

# --- leaves -----------------------------------------------------------------
comptime OP_NONE = 0
"""Absent value.  Rendering a `none` node is a programming error."""
comptime OP_NULL = 1
comptime OP_PARAM = 2
comptime OP_LITERAL = 3
comptime OP_RAW = 4
comptime OP_STAR = 5
comptime OP_TABLE = 6
comptime OP_COLUMN = 7
comptime OP_EXCLUDED = 8
comptime OP_EXCLUDED_COLUMN = 9
comptime OP_LIST = 10

# --- expressions ------------------------------------------------------------
comptime OP_BINARY = 20
comptime OP_UNARY = 21
comptime OP_NARY = 22
comptime OP_BETWEEN = 23
comptime OP_IS = 24
comptime OP_LIKE = 25
comptime OP_CASE = 26
comptime OP_CAST = 27
comptime OP_COLLATE = 28
comptime OP_CONDITIONAL = 29
comptime OP_AS = 30
comptime OP_ORDER = 31
comptime OP_AT_TIME_ZONE = 32

# --- functions --------------------------------------------------------------
comptime OP_FUNCTION = 40
comptime OP_FUNCTION_NOT_CALLABLE = 41
comptime OP_FUNCTION_KEYWORD = 42
comptime OP_TRIM = 43
comptime OP_EXTRACT = 44
comptime OP_AGGREGATE = 45
comptime OP_WINDOW_FUNCTION = 46
comptime OP_WINDOW = 47

# --- grouping ---------------------------------------------------------------
comptime OP_GROUPING = 50
comptime OP_GROUPING_SET = 51
comptime OP_ROLLUP = 52
comptime OP_CUBE = 53
comptime OP_ROLLUP_ITEM = 54

# --- from items -------------------------------------------------------------
comptime OP_JOIN = 60
comptime OP_LATERAL = 61
comptime OP_WITH = 62
comptime OP_FOR = 63

# --- statements -------------------------------------------------------------
comptime OP_SELECT = 70
comptime OP_VALUES = 71
comptime OP_INSERT = 72
comptime OP_UPDATE = 73
comptime OP_DELETE = 74
comptime OP_MERGE = 75
comptime OP_UNION = 76
comptime OP_INTERSECT = 77
comptime OP_EXCEPT = 78
comptime OP_CONFLICT = 79
comptime OP_MATCHED = 80

comptime OP_LAST = 81


def is_statement(op: Int) -> Bool:
    """True for nodes that render as a complete query."""
    return (
        op == OP_SELECT
        or op == OP_VALUES
        or op == OP_INSERT
        or op == OP_UPDATE
        or op == OP_DELETE
        or op == OP_MERGE
        or op == OP_UNION
        or op == OP_INTERSECT
        or op == OP_EXCEPT
    )


def is_combining(op: Int) -> Bool:
    return op == OP_UNION or op == OP_INTERSECT or op == OP_EXCEPT


def is_from_item(op: Int) -> Bool:
    """True for nodes that can appear in a FROM clause and take an alias."""
    return (
        op == OP_TABLE
        or op == OP_JOIN
        or op == OP_LATERAL
        or op == OP_WITH
        or op == OP_EXCLUDED
        or is_statement(op)
    )


# --- SELECT slots -----------------------------------------------------------
comptime SELECT_COLUMNS = 0
comptime SELECT_FROM = 1
comptime SELECT_WHERE = 2
comptime SELECT_GROUP_BY = 3
comptime SELECT_HAVING = 4
comptime SELECT_ORDER_BY = 5
comptime SELECT_LIMIT = 6
comptime SELECT_OFFSET = 7
comptime SELECT_FOR = 8
comptime SELECT_WITH = 9
comptime SELECT_DISTINCT_ON = 10
comptime SELECT_WINDOWS = 11
comptime SELECT_SLOTS = 12

# `Node.i0` bit flags for OP_SELECT.
comptime SELECT_FLAG_DISTINCT = 1
comptime SELECT_FLAG_FROM_DIRECT = 2

# --- combining query slots --------------------------------------------------
comptime COMBINING_QUERIES = 0
comptime COMBINING_ORDER_BY = 1
comptime COMBINING_LIMIT = 2
comptime COMBINING_OFFSET = 3
comptime COMBINING_WITH = 4
comptime COMBINING_SLOTS = 5

comptime COMBINING_FLAG_ALL = 1

# --- INSERT slots -----------------------------------------------------------
comptime INSERT_TABLE = 0
comptime INSERT_COLUMNS = 1
comptime INSERT_VALUES = 2
comptime INSERT_RETURNING = 3
comptime INSERT_WITH = 4
comptime INSERT_CONFLICT = 5
comptime INSERT_SLOTS = 6

# --- UPDATE slots -----------------------------------------------------------
comptime UPDATE_TABLE = 0
comptime UPDATE_COLUMNS = 1
comptime UPDATE_VALUES = 2
comptime UPDATE_FROM = 3
comptime UPDATE_WHERE = 4
comptime UPDATE_RETURNING = 5
comptime UPDATE_WITH = 6
comptime UPDATE_SLOTS = 7

# --- DELETE slots -----------------------------------------------------------
comptime DELETE_TABLE = 0
comptime DELETE_USING = 1
comptime DELETE_WHERE = 2
comptime DELETE_RETURNING = 3
comptime DELETE_WITH = 4
comptime DELETE_SLOTS = 5

comptime DELETE_FLAG_ONLY = 1

# --- MERGE slots ------------------------------------------------------------
comptime MERGE_TABLE = 0
comptime MERGE_SOURCE = 1
comptime MERGE_CONDITION = 2
comptime MERGE_WHENS = 3
comptime MERGE_WITH = 4
comptime MERGE_SLOTS = 5

# --- MATCHED slots ----------------------------------------------------------
comptime MATCHED_CONDITION = 0
comptime MATCHED_COLUMNS = 1
comptime MATCHED_VALUES = 2
comptime MATCHED_SLOTS = 3

# `Node.i0` for OP_MATCHED encodes the action, `Node.i1` whether it is a
# NOT MATCHED branch.
comptime MATCHED_ACTION_NOTHING = 0
comptime MATCHED_ACTION_UPDATE = 1
comptime MATCHED_ACTION_DELETE = 2
comptime MATCHED_ACTION_INSERT = 3

# --- CONFLICT slots ---------------------------------------------------------
comptime CONFLICT_TABLE = 0
comptime CONFLICT_INDEXED_COLUMNS = 1
comptime CONFLICT_INDEX_WHERE = 2
comptime CONFLICT_COLUMNS = 3
comptime CONFLICT_VALUES = 4
comptime CONFLICT_WHERE = 5
comptime CONFLICT_SLOTS = 6

# --- WINDOW slots -----------------------------------------------------------
comptime WINDOW_PARTITION = 0
comptime WINDOW_ORDER_BY = 1
comptime WINDOW_START = 2
comptime WINDOW_END = 3
comptime WINDOW_SLOTS = 4

# `Node.s0` holds the frame keyword, `s1` the EXCLUDE clause, `i1` the identity
# used for alias assignment.

# --- aggregate slots --------------------------------------------------------
comptime AGGREGATE_EXPRESSION = 0
comptime AGGREGATE_ORDER = 1
comptime AGGREGATE_WITHIN = 2
comptime AGGREGATE_FILTER = 3
comptime AGGREGATE_WINDOW = 4
comptime AGGREGATE_SLOTS = 5

comptime AGGREGATE_FLAG_DISTINCT = 1

# --- window function slots --------------------------------------------------
comptime WINDOW_FUNCTION_ARGS = 0
comptime WINDOW_FUNCTION_FILTER = 1
comptime WINDOW_FUNCTION_WINDOW = 2
comptime WINDOW_FUNCTION_SLOTS = 3

# --- misc expression slots --------------------------------------------------
comptime TRIM_EXPRESSION = 0
comptime TRIM_CHARACTERS = 1
comptime TRIM_SLOTS = 2

comptime LIKE_LEFT = 0
comptime LIKE_RIGHT = 1
comptime LIKE_ESCAPE = 2
comptime LIKE_SLOTS = 3

comptime BETWEEN_OPERAND = 0
comptime BETWEEN_LEFT = 1
comptime BETWEEN_RIGHT = 2
comptime BETWEEN_SLOTS = 3

comptime LATERAL_INNER = 0
comptime LATERAL_SLOTS = 1

comptime FOR_TABLES = 0
comptime FOR_SLOTS = 1

comptime FOR_FLAG_NOWAIT = 1

# --- WITH slots -------------------------------------------------------------
comptime WITH_QUERY = 0
comptime WITH_COLUMNS = 1
comptime WITH_SLOTS = 2

comptime WITH_FLAG_RECURSIVE = 1

# --- JOIN slots -------------------------------------------------------------
comptime JOIN_LEFT = 0
comptime JOIN_RIGHT = 1
comptime JOIN_CONDITION = 2
comptime JOIN_SLOTS = 3
