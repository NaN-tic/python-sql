"""Conditional expressions built as native nodes.

The rendering of ``CASE`` and of the ``COALESCE`` family lives in
``sql/sqlcore``; these classes only keep their operands and build one handle.
"""
from sql import Case as _Case, Expression, _C, _make, _nodes

__all__ = ['Case', 'Coalesce', 'NullIf', 'Greatest', 'Least']

_OP_CONDITIONAL = _C['OP_CONDITIONAL']


class Conditional(Expression):
    __slots__ = ()
    _sql = ''
    table = ''
    name = ''


class Case(Conditional, _Case):
    """``CASE WHEN condition THEN result ... ELSE else_ END``.

    The node layout (flattened when pairs, else last, pair count in ``i0``)
    comes from the base class in :mod:`sql`.
    """
    __slots__ = ()


class Coalesce(Conditional):
    __slots__ = ('_node_handle', 'values')
    _conditional = 'COALESCE'

    def __init__(self, *values):
        super().__init__()
        self.values = values
        self._node_handle = _make(
            _OP_CONDITIONAL, _nodes(values), 0, 0, self._conditional)


class NullIf(Coalesce):
    __slots__ = ()
    _conditional = 'NULLIF'


class Greatest(Coalesce):
    __slots__ = ()
    _conditional = 'GREATEST'


class Least(Coalesce):
    __slots__ = ()
    _conditional = 'LEAST'
