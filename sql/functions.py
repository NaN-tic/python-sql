"""SQL functions as native nodes.

A class here validates its arguments, keeps them as public attributes and
builds one node handle.  The name of a function, its argument separators, the
keyword layout and the ``OVER`` clause are rendered by the Mojo core.
"""
from enum import Enum, auto

from sql import (
    _C, _NONE, Expression, Flavor, FromItem, Window, _list, _make,
    _MappedNode, _name_node, _node, _nodes)

__all__ = ['Abs', 'Cbrt', 'Ceil', 'Degrees', 'Div', 'Exp', 'Floor', 'Ln',
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
    'Lag', 'Lead', 'FirstValue', 'LastValue', 'NthValue']

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


class Abs(Function):
    __slots__ = ()
    _function = 'ABS'


class Cbrt(Function):
    __slots__ = ()
    _function = 'CBRT'


class Ceil(Function):
    __slots__ = ()
    _function = 'CEIL'


class Degrees(Function):
    __slots__ = ()
    _function = 'DEGREES'


class Div(Function):
    __slots__ = ()
    _function = 'DIV'


class Exp(Function):
    __slots__ = ()
    _function = 'EXP'


class Floor(Function):
    __slots__ = ()
    _function = 'FLOOR'


class Ln(Function):
    __slots__ = ()
    _function = 'LN'


class Log(Function):
    __slots__ = ()
    _function = 'LOG'


class Mod(Function):
    __slots__ = ()
    _function = 'MOD'


class Pi(Function):
    __slots__ = ()
    _function = 'PI'


class Power(Function):
    __slots__ = ()
    _function = 'POWER'


class Radians(Function):
    __slots__ = ()
    _function = 'RADIANS'


class Random(Function):
    __slots__ = ()
    _function = 'RANDOM'


class Round(Function):
    __slots__ = ()
    _function = 'ROUND'


class SetSeed(Function):
    __slots__ = ()
    _function = 'SETSEED'


class Sign(Function):
    __slots__ = ()
    _function = 'SIGN'


class Sqrt(Function):
    __slots__ = ()
    _function = 'SQRT'


class Trunc(Function):
    __slots__ = ()
    _function = 'TRUNC'


class WidthBucket(Function):
    __slots__ = ()
    _function = 'WIDTH_BUCKET'

# Trigonometric


class Acos(Function):
    __slots__ = ()
    _function = 'ACOS'


class Asin(Function):
    __slots__ = ()
    _function = 'ASIN'


class Atan(Function):
    __slots__ = ()
    _function = 'ATAN'


class Atan2(Function):
    __slots__ = ()
    _function = 'ATAN2'


class Cos(Function):
    __slots__ = ()
    _function = 'Cos'


class Cot(Function):
    __slots__ = ()
    _function = 'COT'


class Sin(Function):
    __slots__ = ()
    _function = 'SIN'


class Tan(Function):
    __slots__ = ()
    _function = 'TAN'

# String


class BitLength(Function):
    __slots__ = ()
    _function = 'BIT_LENGTH'


class CharLength(Function):
    __slots__ = ()
    _function = 'CHAR_LENGTH'


class Lower(Function):
    __slots__ = ()
    _function = 'LOWER'


class OctetLength(Function):
    __slots__ = ()
    _function = 'OCTET_LENGTH'


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


class Upper(Function):
    __slots__ = ()
    _function = 'UPPER'


class ToChar(Function):
    __slots__ = ()
    _function = 'TO_CHAR'


class ToDate(Function):
    __slots__ = ()
    _function = 'TO_DATE'


class ToNumber(Function):
    __slots__ = ()
    _function = 'TO_NUMBER'


class ToTimestamp(Function):
    __slots__ = ()
    _function = 'TO_TIMESTAMP'


class Age(Function):
    __slots__ = ()
    _function = 'AGE'


class ClockTimestamp(Function):
    __slots__ = ()
    _function = 'CLOCK_TIMESTAMP'


class CurrentDate(FunctionNotCallable):
    __slots__ = ()
    _function = 'CURRENT_DATE'


class CurrentTime(FunctionNotCallable):
    __slots__ = ()
    _function = 'CURRENT_TIME'


class CurrentTimestamp(FunctionNotCallable):
    __slots__ = ()
    _function = 'CURRENT_TIMESTAMP'


class DatePart(Function):
    __slots__ = ()
    _function = 'DATE_PART'


class DateTrunc(Function):
    __slots__ = ()
    _function = 'DATE_TRUNC'


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


class Isfinite(Function):
    __slots__ = ()
    _function = 'ISFINITE'


class JustifyDays(Function):
    __slots__ = ()
    _function = 'JUSTIFY_DAYS'


class JustifyHours(Function):
    __slots__ = ()
    _function = 'JUSTIFY_HOURS'


class JustifyInterval(Function):
    __slots__ = ()
    _function = 'JUSTIFY_INTERVAL'


class Localtime(FunctionNotCallable):
    __slots__ = ()
    _function = 'LOCALTIME'


class Localtimestamp(FunctionNotCallable):
    __slots__ = ()
    _function = 'LOCALTIMESTAMP'


class Now(Function):
    __slots__ = ()
    _function = 'NOW'


class StatementTimestamp(Function):
    __slots__ = ()
    _function = 'STATEMENT_TIMESTAMP'


class Timeofday(Function):
    __slots__ = ()
    _function = 'TIMEOFDAY'


class TransactionTimestamp(Function):
    __slots__ = ()
    _function = 'TRANSACTION_TIMESTAMP'


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


class RowNumber(WindowFunction):
    __slots__ = ()
    _function = 'ROW_NUMBER'


class Rank(WindowFunction):
    __slots__ = ()
    _function = 'RANK'


class DenseRank(WindowFunction):
    __slots__ = ()
    _function = 'DENSE_RANK'


class PercentRank(WindowFunction):
    __slots__ = ()
    _function = 'PERCENT_RANK'


class CumeDist(WindowFunction):
    __slots__ = ()
    _function = 'CUME_DIST'


class Ntile(WindowFunction):
    __slots__ = ()
    _function = 'NTILE'


class Lag(WindowFunction):
    __slots__ = ()
    _function = 'LAG'


class Lead(WindowFunction):
    __slots__ = ()
    _function = 'LEAD'


class FirstValue(WindowFunction):
    __slots__ = ()
    _function = 'FIRST_VALUE'


class LastValue(WindowFunction):
    __slots__ = ()
    _function = 'LAST_VALUE'


class NthValue(WindowFunction):
    __slots__ = ()
    _function = 'NTH_VALUE'
