"""Aggregate expressions built as native nodes.

Every class here only validates its operands and assembles one ``OP_AGGREGATE``
handle; the quantifier, the ``ORDER BY`` tail, ``WITHIN GROUP``, ``FILTER`` and
the ``OVER`` clause are rendered by the Mojo core.
"""
from sql import (
    Expression, Flavor, Literal, Window, _C, _NONE, _list, _make, _node,
    _normalize_expressions)

_EXPORTED_NAMES = (
    'Avg', 'BitAnd', 'BitOr', 'BoolAnd', 'BoolOr', 'Count', 'Every',
    'Max', 'Min', 'Stddev', 'Sum', 'Variance',
)
__all__ = list(_EXPORTED_NAMES)

OP_AGGREGATE = _C['OP_AGGREGATE']
OP_STAR = _C['OP_STAR']


class Aggregate(Expression):
    __slots__ = ('_expression', '_distinct', '_order_by', '_within',
        '_filter', '_window')
    _sql = ''

    def __init__(self, expression, distinct=False, order_by=None, within=None,
            filter_=None, window=None):
        super().__init__()
        self.expression = expression
        self.distinct = distinct
        self.order_by = order_by
        self.within = within
        self.filter_ = filter_
        self.window = window

    @property
    def expression(self):
        return self._expression

    @expression.setter
    def expression(self, value):
        if not isinstance(value, Expression):
            raise ValueError("invalid expression: %r" % value)
        self._expression = value

    @property
    def distinct(self):
        return self._distinct

    @distinct.setter
    def distinct(self, value):
        if not isinstance(value, bool):
            raise ValueError("invalid distinct: %r" % value)
        self._distinct = value

    @property
    def order_by(self):
        return self._order_by

    @order_by.setter
    def order_by(self, value):
        self._order_by = _normalize_expressions(value, 'order by')

    @property
    def within(self):
        return self._within

    @within.setter
    def within(self, value):
        self._within = _normalize_expressions(value, 'within')

    @property
    def filter_(self):
        return self._filter

    @filter_.setter
    def filter_(self, value):
        from sql.operators import And, Or
        if value is not None:
            if not isinstance(value, (Expression, And, Or)):
                raise ValueError("invalid filter: %r" % value)
        self._filter = value

    @property
    def window(self):
        return self._window

    @window.setter
    def window(self, value):
        if value:
            if not isinstance(value, Window):
                raise ValueError("invalid window: %r" % value)
        self._window = value

    def over(self, window):
        if not isinstance(window, Window):
            raise ValueError("invalid window: %r" % (window,))
        self._window = window
        return self

    def _expression_handle(self):
        """Handle of the aggregated expression, in argument position."""
        return _node(self._expression)

    def _handle(self):
        slots = [_NONE] * _C['AGGREGATE_SLOTS']
        slots[_C['AGGREGATE_EXPRESSION']] = self._expression_handle()
        slots[_C['AGGREGATE_ORDER']] = _list(self._order_by)
        slots[_C['AGGREGATE_WITHIN']] = _list(self._within)
        slots[_C['AGGREGATE_FILTER']] = (
            _node(self._filter) if self._filter else _NONE)
        slots[_C['AGGREGATE_WINDOW']] = (
            _node(self._window) if self._window else _NONE)
        flags = _C['AGGREGATE_FLAG_DISTINCT'] if self._distinct else 0
        return _make(OP_AGGREGATE, tuple(slots), flags, 0, self._sql)

def _define_aggregates(definitions):
    for name, sql_name in definitions:
        aggregate_type = type(name, (Aggregate,), {
            '__module__': __name__,
            '__slots__': (),
            '_sql': sql_name,
        })
        globals()[name] = aggregate_type


_define_aggregates((
    ('Avg', 'AVG'), ('BitAnd', 'BIT_AND'), ('BitOr', 'BIT_OR'),
    ('BoolAnd', 'BOOL_AND'), ('BoolOr', 'BOOL_OR'),
))


class _Star(Expression):
    __slots__ = ('_node_handle',)

    def __init__(self):
        super().__init__()
        self._node_handle = _make(OP_STAR)


class Count(Aggregate):
    __slots__ = ()
    _sql = 'COUNT'

    def __init__(self, expression=_Star(), **kwargs):
        super().__init__(expression, **kwargs)

    def _expression_handle(self):
        # A filtered COUNT lowered to a CASE counts 1 instead of the star; the
        # core does that for a star node, so keep testing Literal('*') for
        # backward compatibility and hand it over as one.
        if (self._filter and not Flavor.get().filter_
                and isinstance(self._expression, Literal)
                and self._expression.value == '*'):
            return _make(OP_STAR)
        return super()._expression_handle()


_define_aggregates((
    ('Every', 'EVERY'), ('Max', 'MAX'), ('Min', 'MIN'),
    ('Stddev', 'Stddev'), ('Sum', 'SUM'), ('Variance', 'VARIANCE'),
))
