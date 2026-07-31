"""SQL functions as native nodes.

A class here validates its arguments, keeps them as public attributes and
builds one node handle.  The name of a function, its argument separators, the
keyword layout and the ``OVER`` clause are rendered by the Mojo core.
"""
from enum import Enum, auto

from sql import (
    _C, _NONE, Expression, Flavor, FromItem, Window, _list, _make,
    _MappedNode, _name_node, _node, _nodes)

_EXPORTED_NAMES = (
    'Abs', 'Cbrt', 'Ceil', 'Degrees', 'Div', 'Exp', 'Floor', 'Ln',
    'Log', 'Mod', 'Pi', 'Power', 'Radians', 'Random', 'Round', 'SetSeed',
    'Sign', 'Sqrt', 'Trunc', 'WidthBucket',
    'Acos', 'Asin', 'Atan', 'Atan2', 'Cos', 'Cot', 'Sin', 'Tan',
    'BitLength', 'CharLength', 'Overlay', 'Position', 'Substring', 'Trim',
    'Upper',
    'ToChar', 'ToDate', 'ToNumber', 'ToTimestamp',
    'Age', 'ClockTimestamp', 'CurrentDate', 'CurrentTime', 'CurrentTimestamp',
    'DatePart', 'DateTrunc', 'Extract', 'Isfinite', 'JustifyDays',
    'JustifyHours', 'JustifyInterval', 'Localtime', 'Localtimestamp', 'Now',
    'StatementTimestamp', 'Timeofday', 'TransactionTimestamp',
    'AtTimeZone',
    'RowNumber', 'Rank', 'DenseRank', 'PercentRank', 'CumeDist', 'Ntile',
    'Lag', 'Lead', 'FirstValue', 'LastValue', 'NthValue',
)
__all__ = list(_EXPORTED_NAMES)

OP_AT_TIME_ZONE = _C['OP_AT_TIME_ZONE']
OP_EXTRACT = _C['OP_EXTRACT']
OP_FUNCTION = _C['OP_FUNCTION']
OP_FUNCTION_KEYWORD = _C['OP_FUNCTION_KEYWORD']
OP_FUNCTION_NOT_CALLABLE = _C['OP_FUNCTION_NOT_CALLABLE']
OP_TRIM = _C['OP_TRIM']
OP_WINDOW_FUNCTION = _C['OP_WINDOW_FUNCTION']

# Mathematical


class Function(_MappedNode, Expression, FromItem):
    __slots__ = ('args', '_columns_definitions')
    table = ''
    name = ''
    _function = ''

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.args = args
        self.columns_definitions = kwargs.get('columns_definitions', [])

    @property
    def columns_definitions(self):
        return ', '.join('"%s" %s' % (c, d)
            for c, d in self._columns_definitions)

    @columns_definitions.setter
    def columns_definitions(self, value):
        if not isinstance(value, list):
            raise ValueError("invalid columns definitions: %r" % value)
        self._columns_definitions = value

    def _mapped(self):
        """The instance this flavor substitutes for self, or None.

        The replacement carries its own name, keywords and parameters, so a
        mapped function simply renders as the replacement.
        """
        mapping = Flavor.get().function_mapping.get(type(self))
        if mapping is None:
            return None
        return mapping(*self.args)

    @staticmethod
    def _sql_name(function):
        return function._function or type(function).__name__.upper()

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        return _make(
            OP_FUNCTION, _nodes(self.args), 0, self._identity,
            self._sql_name(self), self.columns_definitions)


class FunctionKeyword(Function):
    __slots__ = ()
    _function = ''
    _keywords = ()

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        kids = []
        for keyword, value in zip(self._keywords, _nodes(self.args)):
            kids.append(_name_node(keyword))
            kids.append(value)
        return _make(
            OP_FUNCTION_KEYWORD, tuple(kids), 0, self._identity,
            self._sql_name(self), self.columns_definitions)


class FunctionNotCallable(Function):
    __slots__ = ()
    _function = ''

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        return _make(
            OP_FUNCTION_NOT_CALLABLE, (), 0, 0, self._sql_name(self))


def _define_functions(base, definitions):
    for name, sql_name in definitions:
        function_type = type(name, (base,), {
            '__module__': __name__,
            '__slots__': (),
            '_function': sql_name,
        })
        globals()[name] = function_type
_define_functions(Function, (
    # Mathematical
    ('Abs', 'ABS'), ('Cbrt', 'CBRT'), ('Ceil', 'CEIL'),
    ('Degrees', 'DEGREES'), ('Div', 'DIV'), ('Exp', 'EXP'),
    ('Floor', 'FLOOR'), ('Ln', 'LN'), ('Log', 'LOG'), ('Mod', 'MOD'),
    ('Pi', 'PI'), ('Power', 'POWER'), ('Radians', 'RADIANS'),
    ('Random', 'RANDOM'), ('Round', 'ROUND'), ('SetSeed', 'SETSEED'),
    ('Sign', 'SIGN'), ('Sqrt', 'SQRT'), ('Trunc', 'TRUNC'),
    ('WidthBucket', 'WIDTH_BUCKET'),
    # Trigonometric
    ('Acos', 'ACOS'), ('Asin', 'ASIN'), ('Atan', 'ATAN'),
    ('Atan2', 'ATAN2'), ('Cos', 'Cos'), ('Cot', 'COT'), ('Sin', 'SIN'),
    ('Tan', 'TAN'),
    # String
    ('BitLength', 'BIT_LENGTH'), ('CharLength', 'CHAR_LENGTH'),
    ('Lower', 'LOWER'), ('OctetLength', 'OCTET_LENGTH'),
))


# Trigonometric




class Overlay(FunctionKeyword):
    __slots__ = ()
    _function = 'OVERLAY'
    _keywords = ('', 'PLACING', 'FROM', 'FOR')


class Position(FunctionKeyword):
    __slots__ = ()
    _function = 'POSITION'
    _keywords = ('', 'IN')


class Substring(FunctionKeyword):
    __slots__ = ()
    _function = 'SUBSTRING'
    _keywords = ('', 'FROM', 'FOR')


class Trim(Function):
    __slots__ = ('position', 'characters', 'string')
    _function = 'TRIM'

    def __init__(self, string, position='BOTH', characters=' '):
        if position.upper() not in {'LEADING', 'TRAILING', 'BOTH'}:
            raise ValueError("invalid position: %r" % position)
        super().__init__()
        self.position = position.upper()
        self.characters = characters
        self.string = string

    def _mapped(self):
        mapping = Flavor.get().function_mapping.get(type(self))
        if mapping is None:
            return None
        return mapping(self.string, self.position, self.characters)

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        kids = [_NONE] * _C['TRIM_SLOTS']
        kids[_C['TRIM_EXPRESSION']] = _node(self.string)
        kids[_C['TRIM_CHARACTERS']] = _node(self.characters)
        return _make(
            OP_TRIM, tuple(kids), 0, 0, self._sql_name(self), self.position)


_define_functions(Function, (
    ('Upper', 'UPPER'),
    ('ToChar', 'TO_CHAR'), ('ToDate', 'TO_DATE'),
    ('ToNumber', 'TO_NUMBER'), ('ToTimestamp', 'TO_TIMESTAMP'),
    ('Age', 'AGE'), ('ClockTimestamp', 'CLOCK_TIMESTAMP'),
    ('DatePart', 'DATE_PART'), ('DateTrunc', 'DATE_TRUNC'),
))
_define_functions(FunctionNotCallable, (
    ('CurrentDate', 'CURRENT_DATE'), ('CurrentTime', 'CURRENT_TIME'),
    ('CurrentTimestamp', 'CURRENT_TIMESTAMP'),
))

class Extract(FunctionKeyword):
    __slots__ = ('_field',)
    _function = 'EXTRACT'

    class Fields(str, Enum):
        def _generate_next_value_(name, start, count, last_values):
            return name.upper()

        CENTURY = auto()
        DAY = auto()
        DECADE = auto()
        DOW = auto()
        DOY = auto()
        EPOCH = auto()
        HOUR = auto()
        ISODOW = auto()
        ISOYEAR = auto()
        JULIAN = auto()
        MICROSECONDS = auto()
        MILLENNIUM = auto()
        MILLISECONDS = auto()
        MINUTE = auto()
        MONTH = auto()
        QUARTER = auto()
        SECOND = auto()
        TIMEZONE = auto()
        TIMEZONE_HOUR = auto()
        TIMEZONE_MINUTE = auto()
        WEEK = auto()
        YEAR = auto()

    def __init__(self, field, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field = field

    @property
    def field(self):
        return self._field

    @field.setter
    def field(self, value):
        value = value.upper()
        if not hasattr(self.Fields, value):
            raise ValueError("invalid field: %r" % value)
        self._field = value

    @property
    def _keywords(self):
        return ('%s FROM' % self.field,)

    def _mapped(self):
        mapping = Flavor.get().function_mapping.get(type(self))
        if mapping is None:
            return None
        return mapping(self.field, *self.args)

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        # EXTRACT has exactly one operand; without it the node is incomplete
        # and the renderer rejects it.
        return _make(
            OP_EXTRACT, _nodes(self.args) or (_NONE,), 0, 0, self.field)


_define_functions(Function, (
    ('Isfinite', 'ISFINITE'),
    ('JustifyDays', 'JUSTIFY_DAYS'),
    ('JustifyHours', 'JUSTIFY_HOURS'),
    ('JustifyInterval', 'JUSTIFY_INTERVAL'),
    ('Now', 'NOW'), ('StatementTimestamp', 'STATEMENT_TIMESTAMP'),
    ('Timeofday', 'TIMEOFDAY'),
    ('TransactionTimestamp', 'TRANSACTION_TIMESTAMP'),
))
_define_functions(FunctionNotCallable, (
    ('Localtime', 'LOCALTIME'), ('Localtimestamp', 'LOCALTIMESTAMP'),
))


class AtTimeZone(Function):
    __slots__ = ('field', 'zone')

    def __init__(self, field, zone):
        super().__init__()
        self.field = field
        self.zone = zone

    def _mapped(self):
        mapping = Flavor.get().function_mapping.get(type(self))
        if mapping is None:
            return None
        return mapping(self.field, self.zone)

    def _handle(self):
        mapped = self._mapped()
        if mapped is not None:
            return mapped._handle()
        return _make(
            OP_AT_TIME_ZONE, (_node(self.field), _node(self.zone)))


class WindowFunction(Function):
    __slots__ = ('_filter', '_window')

    def __init__(self, *args, **kwargs):
        self.filter_ = kwargs.pop('filter_', None)
        self.window = kwargs['window']
        super(WindowFunction, self).__init__(*args, **kwargs)

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

    def _handle(self):
        mapped = self._mapped()
        slots = [_NONE] * _C['WINDOW_FUNCTION_SLOTS']
        slots[_C['WINDOW_FUNCTION_ARGS']] = _list(self.args)
        if self._filter is not None:
            slots[_C['WINDOW_FUNCTION_FILTER']] = self._filter._handle()
        if self._window is not None:
            slots[_C['WINDOW_FUNCTION_WINDOW']] = self._window._handle()
        return _make(
            OP_WINDOW_FUNCTION, tuple(slots), 0, 0,
            self._sql_name(self if mapped is None else mapped))


_define_functions(WindowFunction, (
    ('RowNumber', 'ROW_NUMBER'), ('Rank', 'RANK'),
    ('DenseRank', 'DENSE_RANK'), ('PercentRank', 'PERCENT_RANK'),
    ('CumeDist', 'CUME_DIST'), ('Ntile', 'NTILE'), ('Lag', 'LAG'),
    ('Lead', 'LEAD'), ('FirstValue', 'FIRST_VALUE'),
    ('LastValue', 'LAST_VALUE'), ('NthValue', 'NTH_VALUE'),
))
