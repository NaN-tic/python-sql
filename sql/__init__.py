"""python-sql API surface over the native Mojo core.

This module owns no SQL semantics.  Quoting, alias assignment, operator
precedence, dialect handling and rendering all live in ``sql/sqlcore`` and run
as native code.  What stays here is the part CPython cannot express from an
extension type: operator overloading, ``__getattr__``, iteration, subclassing
and keyword argument validation.  Every class is therefore a thin holder of a
native node handle.
"""
from __future__ import annotations

import logging
import numbers
import os
import time
import warnings
from array import array
from collections import defaultdict
from itertools import count
from threading import current_thread, local

from . import _core

__all__ = [
    'Flavor', 'Table', 'Values', 'Literal', 'Column', 'Grouping', 'Conflict',
    'Matched', 'MatchedUpdate', 'MatchedDelete',
    'NotMatched', 'NotMatchedInsert',
    'Rollup', 'Cube', 'Excluded', 'Join', 'Asc', 'Desc', 'NullsFirst',
    'NullsLast', 'format2numeric']

__version__ = '1.8.2'

logger = logging.getLogger(__name__)
_PROFILE_MINIMUM_MS = float(os.environ.get('PYTHON_SQL_PROFILE_MIN_MS', '5'))

_C = _core.constants()
_next_identity = count(1).__next__

OP_NONE = _C['OP_NONE']
OP_NULL = _C['OP_NULL']
OP_PARAM = _C['OP_PARAM']
OP_LITERAL = _C['OP_LITERAL']
OP_RAW = _C['OP_RAW']
OP_STAR = _C['OP_STAR']
OP_TABLE = _C['OP_TABLE']
OP_COLUMN = _C['OP_COLUMN']
OP_EXCLUDED = _C['OP_EXCLUDED']
OP_EXCLUDED_COLUMN = _C['OP_EXCLUDED_COLUMN']
OP_LIST = _C['OP_LIST']

_NONE = _core.none()
_NULL = _core.make(OP_NULL, (), 0, 0)
_EMPTY = _core.make(_C['OP_LIST'], (), 0, 0)
_STAR = _core.make(OP_STAR, (), 0, 0)


_core_make = _core.make
_core_make_text = _core.make_text


def _make(op, kids=(), i0=0, i1=0, s0=None, s1=None, s2=None):
    if s0 is None and s1 is None and s2 is None:
        return _core_make(op, kids, i0, i1)
    return _core_make_text(op, kids, i0, i1, s0, s1, s2)


def _param(value):
    return _core.value(OP_PARAM, value)


def _literal(value):
    return _core.value(OP_LITERAL, value)


def _node(value):
    """Handle for any Python value used where an expression is expected."""
    if isinstance(value, _Node):
        return value._handle()
    if value is None:
        return _NONE
    if isinstance(value, (list, tuple, array)):
        return _make(OP_LIST, tuple(_node(item) for item in value))
    return _param(value)


def _value_node(value):
    return _param(None) if value is None else _node(value)


def _nodes(values):
    if values is None:
        return ()
    if isinstance(values, _Node):
        values = [values]
    return tuple(_value_node(value) for value in values)


def _normalize_expressions(value, name):
    if value is not None:
        if isinstance(value, Expression):
            value = [value]
        if any(not isinstance(expression, Expression) for expression in value):
            raise ValueError("invalid %s: %r" % (name, value))
    return value


def _list(values):
    if not values:
        return _EMPTY
    return _make(OP_LIST, _nodes(values))


def _handles(values):
    if not values:
        return _EMPTY
    return _make(OP_LIST, tuple(values))


def _name_node(name):
    return _make(OP_RAW, (), 0, 0, name)


def _escape_identifier(name):
    return '"%s"' % name.replace('"', '""')


def alias(i, letters='abcdefghijklmnopqrstuvwxyz'):
    '''
    Generate a unique alias based on integer

    >>> [alias(n) for n in range(6)]
    ['a', 'b', 'c', 'd', 'e', 'f']
    >>> [alias(n) for n in range(26, 30)]
    ['ba', 'bb', 'bc', 'bd']
    >>> [alias(26**n) for n in range(5)]
    ['b', 'ba', 'baa', 'baaa', 'baaaa']
    '''
    s = ''
    length = len(letters)
    while True:
        r = i % length
        s = letters[r] + s
        i //= length
        if i == 0:
            break
    return s


_LIMIT_STYLES = {
    'limit': _C['LIMIT_STYLE_LIMIT'],
    'fetch': _C['LIMIT_STYLE_FETCH'],
    'rownum': _C['LIMIT_STYLE_ROWNUM'],
}


class Flavor(object):
    '''
    Contains the flavor of SQL

    Contains:
        limitstyle - state the type of pagination
        max_limit - limit to use if there is no limit but an offset
        paramstyle - state the type of parameter marker formatting
        ilike - support ilike extension
        no_as - doesn't support AS keyword for column and table
        no_boolean - doesn't support boolean type
        null_ordering - support NULL ordering
        function_mapping - dictionary with Function to replace
        filter_ - support filter on aggregate functions
        escape_empty - support empty escape
    '''
    __slots__ = (
        'limitstyle', 'max_limit', 'paramstyle', 'ilike', 'no_as',
        'no_boolean', 'null_ordering', 'function_mapping', 'filter_',
        'escape_empty', '_native')

    def __init__(self, limitstyle='limit', max_limit=None, paramstyle='format',
            ilike=False, no_as=False, no_boolean=False, null_ordering=True,
            function_mapping=None, filter_=False, escape_empty=False):
        if limitstyle not in _LIMIT_STYLES:
            raise ValueError("unsupported limitstyle: %r" % limitstyle)
        self.limitstyle = limitstyle
        if (max_limit is not None
                and not isinstance(max_limit, numbers.Integral)):
            raise ValueError("unsupported max_limit: %r" % max_limit)
        self.max_limit = max_limit
        if paramstyle not in {'format', 'qmark'}:
            raise ValueError("unsupported paramstyle: %r" % paramstyle)
        self.paramstyle = paramstyle
        self.ilike = bool(ilike)
        self.no_as = bool(no_as)
        self.no_boolean = bool(no_boolean)
        self.null_ordering = bool(null_ordering)
        self.function_mapping = dict(function_mapping or {})
        self.filter_ = bool(filter_)
        self.escape_empty = bool(escape_empty)
        self._native = None

    @property
    def param(self):
        return '?' if self.paramstyle == 'qmark' else '%s'

    def _lowered(self):
        native = self._native
        if native is None:
            native = self._native = _core.flavor((
                self.paramstyle == 'qmark',
                self.ilike,
                self.no_as,
                self.no_boolean,
                self.null_ordering,
                self.filter_,
                self.escape_empty,
                _LIMIT_STYLES[self.limitstyle],
                -2 if self.max_limit is None else self.max_limit,
            ))
        return native

    @staticmethod
    def set(flavor):
        '''Set this thread's flavor to flavor.'''
        current_thread().__sql_flavor__ = flavor

    @staticmethod
    def get():
        '''
        Return this thread's flavor.

        If this thread does not yet have a flavor, returns a new flavor and
        sets this thread's flavor.
        '''
        try:
            return current_thread().__sql_flavor__
        except AttributeError:
            flavor = Flavor()
            current_thread().__sql_flavor__ = flavor
            return flavor


class AliasManager(object):
    '''
    Context Manager for unique alias generation
    '''
    __slots__ = ()

    local = local()
    local.alias = None
    local.nested = 0
    local.exclude = None
    local.reserved = 0

    def __init__(self, exclude=None):
        if exclude:
            if getattr(self.local, 'exclude', None) is None:
                self.local.exclude = []
            self.local.exclude.extend(exclude)

    @classmethod
    def __enter__(cls):
        if getattr(cls.local, 'alias', None) is None:
            cls.local.alias = defaultdict(cls.alias_factory)
            cls.local.nested = 0
        if getattr(cls.local, 'exclude', None) is None:
            cls.local.exclude = []
            cls.local.reserved = 0
        cls.local.nested += 1

    @classmethod
    def __exit__(cls, type, value, traceback):
        cls.local.nested -= 1
        if not cls.local.nested:
            cls.local.alias = None
            cls.local.exclude = None
            cls.local.reserved = 0

    @classmethod
    def get(cls, from_):
        if getattr(cls.local, 'alias', None) is None:
            return ''
        if from_ in cls.local.exclude:
            return ''
        return cls.local.alias[from_._identity]

    @classmethod
    def contains(cls, from_):
        if getattr(cls.local, 'alias', None) is None:
            return False
        if from_ in cls.local.exclude:
            return False
        return from_._identity in cls.local.alias

    @classmethod
    def set(cls, from_, alias):
        assert cls.local.alias.get(from_._identity) is None
        cls.local.alias[from_._identity] = alias

    @classmethod
    def alias_factory(cls):
        i = len(cls.local.alias) + getattr(cls.local, 'reserved', 0)
        return alias(i)

    @classmethod
    def _reserve(cls, count):
        """Account for the aliases the renderer assigned on its own."""
        used = count - len(cls.local.alias)
        if used > getattr(cls.local, 'reserved', 0):
            cls.local.reserved = used

    @classmethod
    def _bindings(cls):
        """Aliases already fixed by the caller, handed to the renderer."""
        aliases = getattr(cls.local, 'alias', None)
        if aliases is None:
            return None
        return len(aliases), tuple(aliases.items())


def format2numeric(query, params):
    '''
    Convert format paramstyle query to numeric paramstyle

    >>> format2numeric('SELECT * FROM table WHERE col = %s', ('foo',))
    ('SELECT * FROM table WHERE col = :0', ('foo',))
    >>> format2numeric('SELECT * FROM table WHERE col1 = %s AND col2 = %s',
    ...     ('foo', 'bar'))
    ('SELECT * FROM table WHERE col1 = :0 AND col2 = :1', ('foo', 'bar'))
    '''
    return (query % tuple(':%i' % i for i, _ in enumerate(params)), params)


class _Node(object):
    """Base holder for one native node handle.

    Only ``__weakref__`` is declared here so that subclasses may also inherit
    from ``list``; every concrete class that stores a handle declares
    ``_node_handle`` in its own ``__slots__``.
    """
    __slots__ = ('__weakref__',)

    _node_handle = None

    def __init__(self, handle=None):
        if handle is not None:
            self._node_handle = handle

    def _handle(self):
        handle = self._node_handle
        if handle is None:
            raise NotImplementedError
        return handle

    def __deepcopy__(self, memo):
        from copy import deepcopy
        clone = self.__class__.__new__(self.__class__)
        memo[id(self)] = clone
        for klass in type(self).__mro__:
            for name in getattr(klass, '__slots__', ()):
                if name in {'__weakref__', '_node_handle'}:
                    continue
                try:
                    value = getattr(self, name)
                except AttributeError:
                    continue
                object.__setattr__(clone, name, deepcopy(value, memo))
        if type(self)._node_handle is not self._node_handle:
            object.__setattr__(clone, '_node_handle', self._node_handle)
        return clone

    def _render(self):
        flavor = Flavor.get()
        bindings = AliasManager._bindings()
        sql, params, aliases = _core.render(
            self._handle(), flavor._lowered(), bindings)
        if bindings is not None:
            AliasManager._reserve(aliases)
        return sql, tuple(params)

    def __str__(self):
        return self._render()[0]

    @property
    def params(self):
        return self._render()[1]

    def __iter__(self):
        if logger.isEnabledFor(logging.INFO):
            start = time.perf_counter()
            sql, params = self._render()
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed >= _PROFILE_MINIMUM_MS:
                logger.info(
                    "query %s rendered in %.3f ms", type(self).__name__,
                    elapsed)
        else:
            sql, params = self._render()
        yield sql
        yield params


class _MappedNode(_Node):
    """A node whose SQL name can be replaced through ``function_mapping``."""
    __slots__ = ()

    def _mapped(self):
        return Flavor.get().function_mapping.get(type(self))

    @property
    def params(self):
        mapped = self._mapped()
        if mapped is not None:
            mapped_params = getattr(type(mapped), 'params', None)
            if mapped_params is not None and not isinstance(
                    mapped_params, property):
                return tuple(mapped_params)
        return self._render()[1]


class Query(_Node):
    __slots__ = ()

    def __or__(self, other):
        return Union(self, other)

    def __and__(self, other):
        return Intersect(self, other)

    def __sub__(self, other):
        return Except(self, other)

    def select(self, *columns, **kwargs):
        return Select(columns=columns, from_=[self], **kwargs)

    def as_(self, output_name):
        return As(self, output_name)


class Expression(_Node):
    __slots__ = ()

    def _binary(self, operator, other):
        return BinaryExpression(
            _make(OP_BINARY, (self._handle(), _node(other)), 0, 0, operator))

    def __and__(self, other):
        from sql.operators import And
        return And((self, other))

    def __or__(self, other):
        from sql.operators import Or
        return Or((self, other))

    def __invert__(self):
        from sql.operators import Not
        return Not(self)

    def __add__(self, other):
        from sql.operators import Add
        return Add(self, other)

    def __sub__(self, other):
        from sql.operators import Sub
        return Sub(self, other)

    def __mul__(self, other):
        from sql.operators import Mul
        return Mul(self, other)

    def __div__(self, other):
        from sql.operators import Div
        return Div(self, other)

    __truediv__ = __div__

    def __floordiv__(self, other):
        from sql.functions import Div
        return Div(self, other)

    def __mod__(self, other):
        from sql.operators import Mod
        return Mod(self, other)

    def __pow__(self, other):
        from sql.operators import Pow
        return Pow(self, other)

    def __neg__(self):
        from sql.operators import Neg
        return Neg(self)

    def __pos__(self):
        from sql.operators import Pos
        return Pos(self)

    def __abs__(self):
        from sql.operators import Abs
        return Abs(self)

    def __lshift__(self, other):
        from sql.operators import LShift
        return LShift(self, other)

    def __rshift__(self, other):
        from sql.operators import RShift
        return RShift(self, other)

    def __lt__(self, other):
        from sql.operators import Less
        return Less(self, other)

    def __le__(self, other):
        from sql.operators import LessEqual
        return LessEqual(self, other)

    def __eq__(self, other):
        from sql.operators import Equal
        return Equal(self, other)

    __hash__ = object.__hash__

    def __ne__(self, other):
        from sql.operators import NotEqual
        return NotEqual(self, other)

    def __gt__(self, other):
        from sql.operators import Greater
        return Greater(self, other)

    def __ge__(self, other):
        from sql.operators import GreaterEqual
        return GreaterEqual(self, other)

    def in_(self, values):
        from sql.operators import In
        return In(self, values)

    def like(self, test):
        from sql.operators import Like
        return Like(self, test)

    def ilike(self, test):
        from sql.operators import ILike
        return ILike(self, test)

    def as_(self, output_name):
        return As(self, output_name)

    def cast(self, typename):
        return Cast(self, typename)

    def collate(self, collation):
        return Collate(self, collation)

    @property
    def asc(self):
        return Asc(self)

    @property
    def desc(self):
        return Desc(self)

    @property
    def nulls_first(self):
        return NullsFirst(self)

    @property
    def nulls_last(self):
        return NullsLast(self)


class BinaryExpression(Expression):
    __slots__ = ('_node_handle')


class UnaryExpression(Expression):
    __slots__ = ()


class FromItem(_Node):
    __slots__ = ('_identity',)

    def __init__(self, handle=None):
        super().__init__(handle)
        self._identity = _next_identity()

    @property
    def alias(self):
        return AliasManager.get(self)

    @property
    def has_alias(self):
        return AliasManager.contains(self)

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return Column(self, name)

    def __add__(self, other):
        if not isinstance(other, FromItem):
            return NotImplemented
        return From((self, other))

    def select(self, *args, **kwargs):
        return From((self,)).select(*args, **kwargs)

    def join(self, right, type_='INNER', condition=None):
        return Join(self, right, type_=type_, condition=condition)

    def left_join(self, right, condition=None):
        return self.join(right, type_='LEFT', condition=condition)

    def left_outer_join(self, right, condition=None):
        return self.join(right, type_='LEFT OUTER', condition=condition)

    def right_join(self, right, condition=None):
        return self.join(right, type_='RIGHT', condition=condition)

    def right_outer_join(self, right, condition=None):
        return self.join(right, type_='RIGHT OUTER', condition=condition)

    def full_join(self, right, condition=None):
        return self.join(right, type_='FULL', condition=condition)

    def full_outer_join(self, right, condition=None):
        return self.join(right, type_='FULL OUTER', condition=condition)

    def cross_join(self, right, condition=None):
        return self.join(right, type_='CROSS', condition=condition)

    def lateral(self):
        return Lateral(self)


class Table(FromItem):
    __slots__ = ('_node_handle', '_name', '_schema', '_database')

    def __init__(self, name, schema=None, database=None):
        super().__init__()
        self._name = name
        self._schema = schema
        self._database = database
        self._node_handle = _make(
            OP_TABLE, (), 0, self._identity,
            name, schema or '', database or '')

    def insert(self, columns=None, values=None, returning=None, with_=None,
            on_conflict=None):
        return Insert(self, columns=columns, values=values,
            returning=returning, with_=with_, on_conflict=on_conflict)

    def update(self, columns, values, from_=None, where=None, returning=None,
            with_=None):
        return Update(self, columns=columns, values=values, from_=from_,
            where=where, returning=returning, with_=with_)

    def delete(self, only=False, using=None, where=None, returning=None,
            with_=None):
        return Delete(self, only=only, using=using, where=where,
            returning=returning, with_=with_)

    def merge(self, source, condition, *whens, with_=None):
        return Merge(self, source, condition, *whens, with_=with_)


class Column(Expression):
    __slots__ = ('_node_handle', '_from', '_name')

    def __init__(self, from_, name):
        super().__init__()
        self._node_handle = None
        self._from = from_
        self._name = name

    def _handle(self):
        """Columns are immutable, so the node is built once and reused."""
        handle = self._node_handle
        if handle is None:
            handle = self._node_handle = _make(
                OP_COLUMN, (self._from._handle(),), 0, 0, self._name)
        return handle

    @property
    def table(self):
        return self._from

    @property
    def name(self):
        return self._name

    @property
    def column_name(self):
        return _escape_identifier(self._name)


class Literal(Expression):
    __slots__ = ('_node_handle', 'value',)

    def __init__(self, value):
        super().__init__(_literal(value))
        self.value = value


Null = None


class _Excluded(FromItem):
    __slots__ = ('_node_handle')

    def __init__(self):
        super().__init__()
        self._node_handle = _make(OP_EXCLUDED, (), 0, self._identity)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return _ExcludedColumn(name)

    @property
    def alias(self):
        return 'EXCLUDED'

    @property
    def has_alias(self):
        return False


class _ExcludedColumn(Expression):
    __slots__ = ('_node_handle', '_name',)

    def __init__(self, name):
        super().__init__(_make(OP_EXCLUDED_COLUMN, (), 0, 0, name))
        self._name = name

    @property
    def name(self):
        return self._name


Excluded = _Excluded()


class From(list):
    """A plain list of from items; only ``Select`` consumes it."""

    def select(self, *args, **kwargs):
        return Select(columns=args, from_=self, **kwargs)

    @property
    def tables(self):
        return list(self)

    def __add__(self, other):
        if not isinstance(other, FromItem):
            return NotImplemented
        elif isinstance(other, CombiningQuery):
            return NotImplemented
        return From(super().__add__([other]))

    def __str__(self):
        return str(Select([Literal('*')], from_=self))

    @property
    def params(self):
        return Select([Literal('*')], from_=self).params


OP_BINARY = _C['OP_BINARY']
OP_UNARY = _C['OP_UNARY']
OP_NARY = _C['OP_NARY']
OP_BETWEEN = _C['OP_BETWEEN']
OP_IS = _C['OP_IS']
OP_LIKE = _C['OP_LIKE']
OP_CASE = _C['OP_CASE']
OP_CAST = _C['OP_CAST']
OP_COLLATE = _C['OP_COLLATE']
OP_CONDITIONAL = _C['OP_CONDITIONAL']
OP_AS = _C['OP_AS']
OP_ORDER = _C['OP_ORDER']
OP_AT_TIME_ZONE = _C['OP_AT_TIME_ZONE']
OP_FUNCTION = _C['OP_FUNCTION']
OP_FUNCTION_NOT_CALLABLE = _C['OP_FUNCTION_NOT_CALLABLE']
OP_FUNCTION_KEYWORD = _C['OP_FUNCTION_KEYWORD']
OP_TRIM = _C['OP_TRIM']
OP_EXTRACT = _C['OP_EXTRACT']
OP_AGGREGATE = _C['OP_AGGREGATE']
OP_WINDOW_FUNCTION = _C['OP_WINDOW_FUNCTION']
OP_WINDOW = _C['OP_WINDOW']
OP_GROUPING = _C['OP_GROUPING']
OP_GROUPING_SET = _C['OP_GROUPING_SET']
OP_ROLLUP = _C['OP_ROLLUP']
OP_CUBE = _C['OP_CUBE']
OP_ROLLUP_ITEM = _C['OP_ROLLUP_ITEM']
OP_JOIN = _C['OP_JOIN']
OP_LATERAL = _C['OP_LATERAL']
OP_WITH = _C['OP_WITH']
OP_FOR = _C['OP_FOR']
OP_SELECT = _C['OP_SELECT']
OP_VALUES = _C['OP_VALUES']
OP_INSERT = _C['OP_INSERT']
OP_UPDATE = _C['OP_UPDATE']
OP_DELETE = _C['OP_DELETE']
OP_MERGE = _C['OP_MERGE']
OP_UNION = _C['OP_UNION']
OP_INTERSECT = _C['OP_INTERSECT']
OP_EXCEPT = _C['OP_EXCEPT']
OP_CONFLICT = _C['OP_CONFLICT']
OP_MATCHED = _C['OP_MATCHED']


class Join(FromItem):
    __slots__ = ('_node_handle', '_left', '_right', '_type', '_condition')

    def __init__(self, left, right, type_='INNER', condition=None):
        super().__init__()
        self._left = None
        self._right = None
        self._type = None
        self._condition = None
        self.left = left
        self.right = right
        self.type_ = type_
        self.condition = condition

    @property
    def left(self):
        return self._left

    @left.setter
    def left(self, value):
        if not isinstance(value, FromItem):
            raise ValueError("invalid left: %r" % (value,))
        self._left = value

    @property
    def right(self):
        return self._right

    @right.setter
    def right(self, value):
        if not isinstance(value, FromItem):
            raise ValueError("invalid right: %r" % (value,))
        self._right = value

    @property
    def type_(self):
        return self._type

    @type_.setter
    def type_(self, value):
        value = value.upper()
        if value not in {'INNER', 'LEFT', 'LEFT OUTER', 'RIGHT',
                'RIGHT OUTER', 'FULL', 'FULL OUTER', 'CROSS'}:
            raise ValueError("invalid type: %r" % (value,))
        self._type = value

    @property
    def condition(self):
        return self._condition

    @condition.setter
    def condition(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid condition: %r" % (value,))
        self._condition = value

    def _handle(self):
        return _make(
            OP_JOIN,
            (self._left._handle(), self._right._handle(),
                _node(self._condition)),
            0, self._identity, self._type)

    @property
    def alias(self):
        raise AttributeError('Join has no alias')

    @property
    def has_alias(self):
        raise AttributeError('Join has no alias')

    def __getattr__(self, name):
        raise AttributeError(name)


class Lateral(FromItem):
    __slots__ = ('_node_handle', '_from_item',)

    def __init__(self, from_item):
        super().__init__()
        self._from_item = from_item

    def _handle(self):
        return _make(
            OP_LATERAL, (self._from_item._handle(),), 0, self._identity)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._from_item, name)


def _normalize_with(value):
    if value is not None:
        if isinstance(value, With):
            value = [value]
        if any(not isinstance(item, With) for item in value):
            raise ValueError("invalid with: %r" % (value,))
    return value


def _with_definition_handles(value):
    return _handles(
        tuple(item._definition() for item in (value or ())))


class SelectQuery(Query, FromItem):
    """Common ORDER BY / LIMIT / OFFSET tail of the query statements."""
    __slots__ = ('_node_handle', '_order_by', '_limit', '_offset', '_with')

    def __init__(self, order_by=None, limit=None, offset=None, with_=None):
        FromItem.__init__(self)
        self._order_by = None
        self._limit = None
        self._offset = None
        self._with = None
        self.order_by = order_by
        self.limit = limit
        self.offset = offset
        self.with_ = with_

    @property
    def order_by(self):
        return self._order_by

    @order_by.setter
    def order_by(self, value):
        self._order_by = _normalize_expressions(value, 'order by')

    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, value):
        if value is not None:
            if not isinstance(value, numbers.Integral):
                raise ValueError("invalid limit: %r" % (value,))
        self._limit = value

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, value):
        if value is not None:
            if not isinstance(value, numbers.Integral):
                raise ValueError("invalid offset: %r" % (value,))
        self._offset = value

    @property
    def with_(self):
        return self._with

    @with_.setter
    def with_(self, value):
        self._with = _normalize_with(value)

    def _with_handles(self):
        return _with_definition_handles(self._with)

    def _limit_handle(self):
        return _NONE if self._limit is None else _param(self._limit)

    def _offset_handle(self):
        return _NONE if self._offset is None else _param(self._offset)

    def _order_handles(self):
        return _handles(
            tuple(item._handle() for item in (self._order_by or ())))


class With(FromItem):
    __slots__ = ('columns', 'query', 'recursive')

    def __init__(self, *columns, **kwargs):
        super().__init__()
        self.recursive = kwargs.pop('recursive', False)
        self.columns = columns
        self.query = kwargs.pop('query', None)

    def statement(self):
        columns = (' (%s)' % ', '.join('"%s"' % c for c in self.columns)
            if self.columns else '')
        return '"%s"%s AS (%s)' % (self.alias, columns, self.query)

    def statement_params(self):
        return self.query.params

    def __str__(self):
        return '"%s"' % self.alias

    @property
    def params(self):
        return tuple()

    def _handle(self):
        """Reference form: only the identity, so a recursive CTE terminates."""
        return _make(OP_WITH, (), 0, self._identity)

    def _definition(self):
        """Full form, used once in the WITH clause of the statement."""
        return _make(
            OP_WITH,
            (self.query._handle(),
                _handles(tuple(_name_node(c) for c in self.columns))),
            1 if self.recursive else 0, self._identity)

    def select(self, *columns, **kwargs):
        return Select(columns=columns, from_=[self], **kwargs)


class WithQuery(Query):
    __slots__ = ('_with',)

    def __init__(self, with_=None, **kwargs):
        super().__init__(**kwargs)
        self._with = None
        self.with_ = with_

    @property
    def with_(self):
        return self._with

    @with_.setter
    def with_(self, value):
        self._with = _normalize_with(value)

    def _with_handles(self):
        return _with_definition_handles(self._with)

    def _with_str(self):
        if not self.with_:
            return ''
        recursive = (' RECURSIVE'
            if any(w.recursive for w in self.with_) else '')
        return 'WITH%s %s ' % (
            recursive, ', '.join(w.statement() for w in self.with_))

    def _with_params(self):
        return tuple(
            param for w in (self.with_ or ()) for param in w.statement_params())


class Select(SelectQuery):
    __slots__ = ('_columns', '_from', '_from_direct', '_where', '_group_by',
        '_having', '_for', '_distinct', '_distinct_on', '_windows')

    def __init__(self, columns=(), from_=None, where=None, group_by=None,
            having=None, for_=None, distinct=False, distinct_on=None,
            windows=None, **kwargs):
        self._columns = ()
        self._from = None
        self._from_direct = False
        self._where = None
        self._group_by = None
        self._having = None
        self._for = None
        self._distinct = False
        self._distinct_on = None
        self._windows = None
        super().__init__(**kwargs)
        self.columns = columns
        self.from_ = from_
        self.where = where
        self.group_by = group_by
        self.having = having
        self.for_ = for_
        self.distinct = distinct
        self.distinct_on = distinct_on
        self.windows = windows

    @property
    def columns(self):
        return self._columns

    @columns.setter
    def columns(self, value):
        value = tuple(value)
        if any(not isinstance(col, (Expression, Query)) for col in value):
            raise ValueError("invalid columns: %r" % (value,))
        self._columns = value

    @property
    def from_(self):
        return self._from

    @from_.setter
    def from_(self, value):
        if value is None:
            self._from = None
            self._from_direct = False
            return
        if isinstance(value, FromItem):
            self._from = value if isinstance(value, From) else From([value])
            self._from_direct = isinstance(value, Query) and not isinstance(
                value, From)
        else:
            from sql.functions import Function
            values = tuple(value)
            if any(not isinstance(item, (FromItem, Query, Function))
                    for item in values):
                raise ValueError("invalid from: %r" % (value,))
            self._from = From(values)
            self._from_direct = False

    @property
    def where(self):
        return self._where

    @where.setter
    def where(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid where: %r" % (value,))
        self._where = value

    @property
    def group_by(self):
        return self._group_by

    @group_by.setter
    def group_by(self, value):
        if value is not None:
            if isinstance(value, Expression):
                value = [value]
            if any(not isinstance(col, Expression) for col in value):
                raise ValueError("invalid group by: %r" % (value,))
        self._group_by = value

    @property
    def having(self):
        return self._having

    @having.setter
    def having(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid having: %r" % (value,))
        self._having = value

    @property
    def for_(self):
        return self._for

    @for_.setter
    def for_(self, value):
        if value is not None:
            if isinstance(value, For):
                value = [value]
            if any(not isinstance(f, For) for f in value):
                raise ValueError("invalid for: %r" % (value,))
        self._for = value

    @property
    def distinct(self):
        return self._distinct

    @distinct.setter
    def distinct(self, value):
        self._distinct = bool(value)

    @property
    def distinct_on(self):
        return self._distinct_on

    @distinct_on.setter
    def distinct_on(self, value):
        if value is not None:
            if isinstance(value, Expression):
                value = [value]
            if any(not isinstance(col, Expression) for col in value):
                raise ValueError("invalid distinct on: %r" % (value,))
            self._distinct = True
        self._distinct_on = value

    def _inferred_windows(self):
        from sql.aggregate import Aggregate
        from sql.functions import WindowFunction
        values = list(self._windows or ())
        for expression in self._columns:
            if not isinstance(expression, (Aggregate, WindowFunction)):
                continue
            window = expression.window
            if window is not None and window not in values:
                values.append(window)
        return values

    @property
    def windows(self):
        return self._inferred_windows()

    @windows.setter
    def windows(self, value):
        if value is not None:
            value = list(value)
            if any(not isinstance(item, Window) for item in value):
                raise ValueError("invalid windows: %r" % (value,))
        self._windows = value

    def _check_output_names(self):
        """An output name reused in GROUP BY/ORDER BY must be the same value."""
        for expression in list(self._group_by or ()) + list(
                self._order_by or ()):
            if not isinstance(expression, As):
                continue
            for column in self._columns:
                if not isinstance(column, As):
                    continue
                if column.output_name != expression.output_name:
                    continue
                same = (
                    str(column.expression) == str(expression.expression)
                    and column.expression.params
                    == expression.expression.params)
                if not same:
                    raise ValueError("%r != %r" % (expression, column))

    def _handle(self):
        self._check_output_names()
        slots = [_NONE] * _C['SELECT_SLOTS']
        slots[_C['SELECT_COLUMNS']] = _list(self._columns)
        slots[_C['SELECT_FROM']] = _handles(
            tuple(item._handle() for item in (self._from or ())))
        slots[_C['SELECT_WHERE']] = _node(self._where)
        slots[_C['SELECT_GROUP_BY']] = _list(self._group_by)
        slots[_C['SELECT_HAVING']] = _node(self._having)
        slots[_C['SELECT_ORDER_BY']] = self._order_handles()
        slots[_C['SELECT_LIMIT']] = self._limit_handle()
        slots[_C['SELECT_OFFSET']] = self._offset_handle()
        slots[_C['SELECT_FOR']] = _handles(
            tuple(item._handle() for item in (self._for or ())))
        slots[_C['SELECT_WITH']] = self._with_handles()
        slots[_C['SELECT_DISTINCT_ON']] = _list(self._distinct_on)
        slots[_C['SELECT_WINDOWS']] = _handles(
            tuple(w._handle() for w in (self._windows or ())))
        flags = 0
        if self._distinct:
            flags |= _C['SELECT_FLAG_DISTINCT']
        if self._from_direct:
            flags |= _C['SELECT_FLAG_FROM_DIRECT']
        return _make(OP_SELECT, tuple(slots), flags, self._identity)


class Values(Query, FromItem):
    __slots__ = ('_node_handle', '_values',)

    def __init__(self, values, **kwargs):
        FromItem.__init__(self)
        self._values = list(values)

    @property
    def values(self):
        return self._values

    def _handle(self):
        return _make(
            OP_VALUES,
            tuple(_list(row) for row in self._values),
            0, self._identity)

    def select(self, *columns, **kwargs):
        return Select(columns=columns, from_=[self], **kwargs)


class CombiningQuery(SelectQuery):
    __slots__ = ('_queries', 'all_')
    _operator = 'UNION'
    _opcode = None

    def __init__(self, *queries, **kwargs):
        self.all_ = kwargs.pop('all_', kwargs.pop('all', False))
        super().__init__(**kwargs)
        self.queries = queries

    @property
    def queries(self):
        return self._queries

    @queries.setter
    def queries(self, value):
        value = tuple(value)
        if any(not isinstance(query, Query) for query in value):
            raise ValueError("invalid queries: %r" % (value,))
        self._queries = value

    def _handle(self):
        slots = [_NONE] * _C['COMBINING_SLOTS']
        slots[_C['COMBINING_QUERIES']] = _handles(
            tuple(query._handle() for query in self._queries))
        slots[_C['COMBINING_ORDER_BY']] = self._order_handles()
        slots[_C['COMBINING_LIMIT']] = self._limit_handle()
        slots[_C['COMBINING_OFFSET']] = self._offset_handle()
        slots[_C['COMBINING_WITH']] = self._with_handles()
        flags = _C['COMBINING_FLAG_ALL'] if self.all_ else 0
        return _make(self._opcode, tuple(slots), flags, self._identity)


class Union(CombiningQuery):
    __slots__ = ()
    _operator = 'UNION'
    _opcode = OP_UNION


class Intersect(CombiningQuery):
    __slots__ = ()
    _operator = 'INTERSECT'
    _opcode = OP_INTERSECT


class Interesect(Intersect):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        warnings.warn(
            'Interesect query is deprecated, use Intersect',
            DeprecationWarning, stacklevel=2)
        super().__init__(*args, **kwargs)


class Except(CombiningQuery):
    __slots__ = ()
    _operator = 'EXCEPT'
    _opcode = OP_EXCEPT


class Insert(WithQuery):
    __slots__ = ('_node_handle', '_table', '_columns', '_values', '_returning',
        '_on_conflict')

    def __init__(self, table, columns=None, values=None, returning=None,
            on_conflict=None, **kwargs):
        self._table = None
        self._columns = None
        self._values = None
        self._returning = None
        self._on_conflict = None
        super().__init__(**kwargs)
        self.table = table
        self.columns = columns
        self.values = values
        self.returning = returning
        self.on_conflict = on_conflict

    @property
    def table(self):
        return self._table

    @table.setter
    def table(self, value):
        if not isinstance(value, Table):
            raise ValueError("invalid table: %r" % (value,))
        self._table = value

    @property
    def columns(self):
        return self._columns

    @columns.setter
    def columns(self, value):
        if value is not None:
            value = list(value)
            if any(not isinstance(col, Column) for col in value):
                raise ValueError("invalid columns: %r" % (value,))
        self._columns = value

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        if (value is not None
                and not isinstance(value, (list, Select, Values))):
            raise ValueError("invalid values: %r" % (value,))
        self._values = value

    @property
    def returning(self):
        return self._returning

    @returning.setter
    def returning(self, value):
        if value is not None:
            if not isinstance(value, list):
                raise ValueError("invalid returning: %r" % (value,))
        self._returning = value

    @property
    def on_conflict(self):
        return self._on_conflict

    @on_conflict.setter
    def on_conflict(self, value):
        if value is not None:
            if not isinstance(value, Conflict) or value.table != self.table:
                raise ValueError("invalid on conflict: %r" % (value,))
        self._on_conflict = value

    def _values_handle(self):
        if self._values is None:
            return _NONE
        if isinstance(self._values, (Select, Values)):
            return self._values._handle()
        return _make(OP_VALUES, tuple(_list(row) for row in self._values))

    def _handle(self):
        slots = [_NONE] * _C['INSERT_SLOTS']
        slots[_C['INSERT_TABLE']] = self._table._handle()
        slots[_C['INSERT_COLUMNS']] = _handles(
            tuple(_name_node(c.name) for c in (self._columns or ())))
        slots[_C['INSERT_VALUES']] = self._values_handle()
        slots[_C['INSERT_RETURNING']] = _list(self._returning)
        slots[_C['INSERT_WITH']] = self._with_handles()
        slots[_C['INSERT_CONFLICT']] = _node(self._on_conflict)
        return _make(OP_INSERT, tuple(slots))


class Update(Insert):
    __slots__ = ('_where', '_from')

    def __init__(self, table, columns, values, from_=None, where=None,
            **kwargs):
        self._where = None
        self._from = None
        super().__init__(table, columns=columns, values=values, **kwargs)
        self.from_ = from_
        self.where = where

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        if not isinstance(value, (list, Select)):
            raise ValueError("invalid values: %r" % (value,))
        self._values = value

    @property
    def from_(self):
        return self._from

    @from_.setter
    def from_(self, value):
        if value is not None:
            if not isinstance(value, From):
                value = From(value)
        self._from = value

    @property
    def where(self):
        return self._where

    @where.setter
    def where(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid where: %r" % (value,))
        self._where = value

    def _handle(self):
        slots = [_NONE] * _C['UPDATE_SLOTS']
        slots[_C['UPDATE_TABLE']] = self._table._handle()
        slots[_C['UPDATE_COLUMNS']] = _handles(
            tuple(_name_node(c.name) for c in (self._columns or ())))
        slots[_C['UPDATE_VALUES']] = _list(self._values)
        slots[_C['UPDATE_FROM']] = _handles(
            tuple(item._handle() for item in (self._from or ())))
        slots[_C['UPDATE_WHERE']] = _node(self._where)
        slots[_C['UPDATE_RETURNING']] = _list(self._returning)
        slots[_C['UPDATE_WITH']] = self._with_handles()
        return _make(OP_UPDATE, tuple(slots))


class Delete(WithQuery):
    __slots__ = ('_node_handle', '_table', '_only', '_using', '_where', '_returning')

    def __init__(self, table, only=False, using=None, where=None,
            returning=None, **kwargs):
        self._table = None
        self._only = False
        self._using = None
        self._where = None
        self._returning = None
        super().__init__(**kwargs)
        self.table = table
        self.only = only
        self.using = using
        self.where = where
        self.returning = returning

    @property
    def table(self):
        return self._table

    @table.setter
    def table(self, value):
        if not isinstance(value, Table):
            raise ValueError("invalid table: %r" % (value,))
        self._table = value

    @property
    def only(self):
        return self._only

    @only.setter
    def only(self, value):
        self._only = bool(value)

    @property
    def using(self):
        return self._using

    @using.setter
    def using(self, value):
        if value is not None:
            if not isinstance(value, From):
                value = From(value)
        self._using = value

    @property
    def where(self):
        return self._where

    @where.setter
    def where(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid where: %r" % (value,))
        self._where = value

    @property
    def returning(self):
        return self._returning

    @returning.setter
    def returning(self, value):
        if value is not None:
            if not isinstance(value, list):
                raise ValueError("invalid returning: %r" % (value,))
        self._returning = value

    def _handle(self):
        slots = [_NONE] * _C['DELETE_SLOTS']
        slots[_C['DELETE_TABLE']] = self._table._handle()
        slots[_C['DELETE_USING']] = _handles(
            tuple(item._handle() for item in (self._using or ())))
        slots[_C['DELETE_WHERE']] = _node(self._where)
        slots[_C['DELETE_RETURNING']] = _list(self._returning)
        slots[_C['DELETE_WITH']] = self._with_handles()
        flags = _C['DELETE_FLAG_ONLY'] if self._only else 0
        return _make(OP_DELETE, tuple(slots), flags)


class Merge(WithQuery):
    __slots__ = ('_node_handle', '_table', '_source', '_condition', '_whens')

    def __init__(self, table, source, condition, *whens, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(table, Table):
            raise ValueError("invalid table: %r" % (table,))
        if not isinstance(source, (Table, SelectQuery, Values)):
            raise ValueError("invalid source: %r" % (source,))
        if not isinstance(condition, Expression):
            raise ValueError("invalid condition: %r" % (condition,))
        if any(not isinstance(when, Matched) for when in whens):
            raise ValueError("invalid whens: %r" % (whens,))
        self._table = table
        self._source = source
        self._condition = condition
        self._whens = whens

    def _handle(self):
        slots = [_NONE] * _C['MERGE_SLOTS']
        slots[_C['MERGE_TABLE']] = self._table._handle()
        slots[_C['MERGE_SOURCE']] = self._source._handle()
        slots[_C['MERGE_CONDITION']] = self._condition._handle()
        slots[_C['MERGE_WHENS']] = _handles(
            tuple(when._handle() for when in self._whens))
        slots[_C['MERGE_WITH']] = self._with_handles()
        return _make(OP_MERGE, tuple(slots))


class Conflict(Expression):
    __slots__ = ('_table', '_indexed_columns', '_index_where', '_columns',
        '_values', '_where')

    def __init__(self, table, indexed_columns=None, index_where=None,
            columns=None, values=None, where=None):
        super().__init__()
        self._table = None
        self._indexed_columns = None
        self._index_where = None
        self._columns = None
        self._values = None
        self._where = None
        self.table = table
        self.indexed_columns = indexed_columns
        self.index_where = index_where
        self.columns = columns
        self.values = values
        self.where = where

    @property
    def table(self):
        return self._table

    @table.setter
    def table(self, value):
        if not isinstance(value, Table):
            raise ValueError("invalid table: %r" % (value,))
        self._table = value

    @property
    def indexed_columns(self):
        return self._indexed_columns

    @indexed_columns.setter
    def indexed_columns(self, value):
        if value is not None:
            if any(not isinstance(col, Column) or col.table is not self.table
                    for col in value):
                raise ValueError("invalid indexed columns: %r" % (value,))
        self._indexed_columns = value

    @property
    def index_where(self):
        return self._index_where

    @index_where.setter
    def index_where(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid index where: %r" % (value,))
        self._index_where = value

    @property
    def columns(self):
        return self._columns

    @columns.setter
    def columns(self, value):
        if value is not None:
            if any(not isinstance(col, Column) or col.table is not self.table
                    for col in value):
                raise ValueError("invalid columns: %r" % (value,))
        self._columns = value

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        if value is not None and not isinstance(value, (list, Select)):
            raise ValueError("invalid values: %r" % (value,))
        if isinstance(value, list):
            value = Values([value])
        self._values = value

    @property
    def where(self):
        return self._where

    @where.setter
    def where(self, value):
        if value is not None and not isinstance(value, Expression):
            raise ValueError("invalid where: %r" % (value,))
        self._where = value

    def _handle(self):
        slots = [_NONE] * _C['CONFLICT_SLOTS']
        slots[_C['CONFLICT_TABLE']] = self._table._handle()
        slots[_C['CONFLICT_INDEXED_COLUMNS']] = _handles(
            tuple(_name_node(c.name) for c in (self._indexed_columns or ())))
        slots[_C['CONFLICT_INDEX_WHERE']] = _node(self._index_where)
        slots[_C['CONFLICT_COLUMNS']] = _handles(
            tuple(_name_node(c.name) for c in (self._columns or ())))
        slots[_C['CONFLICT_VALUES']] = _node(self._values)
        slots[_C['CONFLICT_WHERE']] = _node(self._where)
        return _make(OP_CONFLICT, tuple(slots))


class Matched(_Node):
    __slots__ = ('_node_handle', 'condition', 'columns', 'values')
    _not_matched = False
    _action = _C['MATCHED_ACTION_NOTHING']

    def __init__(self, condition=None):
        super().__init__()
        if condition is not None and not isinstance(condition, Expression):
            raise ValueError("invalid condition: %r" % (condition,))
        self.condition = condition
        self.columns = ()
        self.values = None

    def _values_handle(self):
        if self.values is None:
            return _NONE
        return _make(OP_VALUES, (_list(self.values),))

    def _handle(self):
        slots = [_NONE] * _C['MATCHED_SLOTS']
        slots[_C['MATCHED_CONDITION']] = _node(self.condition)
        slots[_C['MATCHED_COLUMNS']] = _handles(
            tuple(_name_node(c.name) for c in self.columns))
        slots[_C['MATCHED_VALUES']] = self._values_handle()
        return _make(
            OP_MATCHED, tuple(slots), self._action,
            1 if self._not_matched else 0)


class MatchedUpdate(Matched):
    __slots__ = ()
    _action = _C['MATCHED_ACTION_UPDATE']

    def __init__(self, columns, values, condition=None):
        super().__init__(condition=condition)
        if any(not isinstance(col, Column) for col in columns):
            raise ValueError("invalid columns: %r" % (columns,))
        self.columns = tuple(columns)
        self.values = list(values)


class MatchedDelete(Matched):
    __slots__ = ()
    _action = _C['MATCHED_ACTION_DELETE']


class NotMatched(Matched):
    __slots__ = ()
    _not_matched = True


class NotMatchedInsert(NotMatched):
    __slots__ = ()
    _action = _C['MATCHED_ACTION_INSERT']

    def __init__(self, columns=None, values=None, condition=None):
        super().__init__(condition=condition)
        columns = tuple(columns or ())
        if any(not isinstance(col, Column) for col in columns):
            raise ValueError("invalid columns: %r" % (columns,))
        self.columns = columns
        self.values = list(values) if values is not None else None


class Grouping(Expression):
    __slots__ = ('_node_handle', '_sets',)

    def __init__(self, *sets):
        super().__init__()
        for set_ in sets:
            if not isinstance(set_, tuple):
                raise ValueError("invalid set: %r" % (set_,))
            if any(not isinstance(e, Expression) for e in set_):
                raise ValueError("invalid set: %r" % (set_,))
        self._sets = sets
        self._node_handle = _make(
            OP_GROUPING,
            tuple(_make(OP_GROUPING_SET, _nodes(s)) for s in sets))

    @property
    def sets(self):
        return self._sets


class Rollup(Expression):
    __slots__ = ('_node_handle', '_expressions',)
    _opcode = OP_ROLLUP

    def __init__(self, *expressions):
        super().__init__()
        for expression in expressions:
            if not isinstance(expression, (Expression, tuple)):
                raise ValueError("invalid expression: %r" % (expression,))
            if isinstance(expression, tuple):
                if any(not isinstance(e, Expression) for e in expression):
                    raise ValueError("invalid expression: %r" % (expression,))
        self._expressions = tuple(expressions)
        self._node_handle = _make(
            self._opcode,
            tuple(
                _make(OP_ROLLUP_ITEM, _nodes(e))
                if isinstance(e, tuple) else _node(e)
                for e in expressions))

    @property
    def expressions(self):
        return self._expressions


class Cube(Rollup):
    __slots__ = ()
    _opcode = OP_CUBE


class Window(Expression):
    __slots__ = ('_node_handle', '_partition', '_order_by', '_frame', '_start', '_end',
        '_exclude', '_identity')

    def __init__(self, partition=(), order_by=None, frame=None, start=None,
            end=0, exclude=None):
        super().__init__()
        self._identity = _next_identity()
        self._partition = None
        self._order_by = None
        self._frame = None
        self._start = None
        self._end = None
        self._exclude = None
        self.partition = partition
        self.order_by = order_by
        self.frame = frame
        self.start = start
        self.end = end
        self.exclude = exclude

    @property
    def partition(self):
        return self._partition

    @partition.setter
    def partition(self, value):
        value = tuple(value)
        if any(not isinstance(e, Expression) for e in value):
            raise ValueError("invalid partition: %r" % (value,))
        self._partition = value

    @property
    def order_by(self):
        return self._order_by

    @order_by.setter
    def order_by(self, value):
        if value is not None:
            if isinstance(value, Expression):
                value = [value]
            if any(not isinstance(col, Expression) for col in value):
                raise ValueError("invalid order by: %r" % (value,))
        self._order_by = value

    @property
    def frame(self):
        return self._frame

    @frame.setter
    def frame(self, value):
        if value is not None and value not in {'RANGE', 'ROWS', 'GROUPS'}:
            raise ValueError("invalid frame: %r" % (value,))
        self._frame = value

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        if value is not None and not isinstance(value, numbers.Integral):
            raise ValueError("invalid start: %r" % (value,))
        self._start = value

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, value):
        if value is not None and not isinstance(value, numbers.Integral):
            raise ValueError("invalid end: %r" % (value,))
        self._end = value

    @property
    def exclude(self):
        return self._exclude

    @exclude.setter
    def exclude(self, value):
        if value is not None and value not in {
                'CURRENT ROW', 'GROUP', 'TIES', 'NO OTHERS'}:
            raise ValueError("invalid exclude: %r" % (value,))
        self._exclude = value

    @property
    def alias(self):
        return AliasManager.get(self)

    @property
    def has_alias(self):
        return AliasManager.contains(self)

    def _handle(self):
        slots = [_NONE] * _C['WINDOW_SLOTS']
        slots[_C['WINDOW_PARTITION']] = _list(self._partition)
        slots[_C['WINDOW_ORDER_BY']] = _list(self._order_by)
        slots[_C['WINDOW_START']] = (
            _NONE if self._start is None else _param(self._start))
        slots[_C['WINDOW_END']] = (
            _NONE if self._end is None else _param(self._end))
        return _make(
            OP_WINDOW, tuple(slots), 0, self._identity,
            self._frame or '', self._exclude or '')


class Order(Expression):
    __slots__ = ('_node_handle', 'expression',)
    _sql = ''

    def __init__(self, expression):
        super().__init__()
        if not isinstance(expression, (Expression, Query)):
            raise ValueError("invalid expression: %r" % (expression,))
        self.expression = expression
        self._node_handle = _make(
            OP_ORDER, (expression._handle(),), 0, 0, self._sql)


class Asc(Order):
    __slots__ = ()
    _sql = 'ASC'


class Desc(Order):
    __slots__ = ()
    _sql = 'DESC'


class NullOrder(Order):
    __slots__ = ()
    _sql = ''

    def _case_values(self):
        raise NotImplementedError


class NullsFirst(NullOrder):
    __slots__ = ()
    _sql = 'NULLS FIRST'

    def _case_values(self):
        return 0, 1


class NullsLast(NullOrder):
    __slots__ = ()
    _sql = 'NULLS LAST'

    def _case_values(self):
        return 1, 0


class For(_Node):
    __slots__ = ('_type', '_tables', '_nowait')

    def __init__(self, type_, *tables, **kwargs):
        super().__init__()
        self._type = None
        self._tables = None
        self._nowait = None
        self.type_ = type_
        self.tables = list(tables)
        self.nowait = kwargs.get('nowait', False)

    @property
    def type_(self):
        return self._type

    @type_.setter
    def type_(self, value):
        value = value.upper()
        if value not in {'UPDATE', 'NO KEY UPDATE', 'SHARE', 'KEY SHARE'}:
            raise ValueError("invalid type: %r" % (value,))
        self._type = value

    @property
    def tables(self):
        return self._tables

    @tables.setter
    def tables(self, value):
        if isinstance(value, Table):
            value = [value]
        if any(not isinstance(table, Table) for table in value):
            raise ValueError("invalid tables: %r" % (value,))
        self._tables = value

    @property
    def nowait(self):
        return self._nowait

    @nowait.setter
    def nowait(self, value):
        self._nowait = bool(value)

    def _handle(self):
        return _make(
            OP_FOR,
            (_handles(tuple(table._handle() for table in self._tables)),),
            1 if self._nowait else 0, 0, self._type)


class As(Expression):
    __slots__ = ('_node_handle', 'expression', 'output_name')

    def __init__(self, expression, output_name):
        super().__init__()
        self.expression = expression
        self.output_name = output_name
        self._node_handle = _make(
            OP_AS, (_node(expression),), 0, 0, output_name)

    def __str__(self):
        return _escape_identifier(self.output_name)


class Cast(Expression):
    __slots__ = ('_node_handle', 'expression', 'typename')

    def __init__(self, expression, typename):
        super().__init__()
        self.expression = expression
        self.typename = typename
        self._node_handle = _make(
            OP_CAST, (_node(expression),), 0, 0, typename)


class Collate(Expression):
    __slots__ = ('_node_handle', 'expression', 'collation')

    def __init__(self, expression, collation):
        super().__init__()
        self.expression = expression
        self.collation = collation
        self._node_handle = _make(
            OP_COLLATE, (_node(expression),), 0, 0, collation)


class AtTimeZone(Expression):
    __slots__ = ('_node_handle', 'expression', 'zone')

    def __init__(self, expression, zone):
        super().__init__()
        self.expression = expression
        self.zone = zone
        self._node_handle = _make(
            OP_AT_TIME_ZONE, (_node(expression), _node(zone)))


class Case(Expression):
    __slots__ = ('_node_handle', 'whens', 'else_')

    def __init__(self, *whens, **kwargs):
        super().__init__()
        self.whens = whens
        self.else_ = kwargs.get('else_')
        kids = []
        for condition, result in whens:
            kids.append(_node(condition))
            kids.append(_node(result))
        kids.append(_node(self.else_))
        self._node_handle = _make(OP_CASE, tuple(kids), len(whens))
