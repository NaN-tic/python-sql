"""SQL operators built as native nodes.

Operator precedence and parenthesising, the ``IS NULL`` folding of ``=`` and
``!=``, the ``ILIKE`` fallback to ``UPPER(...) LIKE UPPER(...)``, the ``ESCAPE``
clause of the ``LIKE`` family and the paramstyle escaping of ``%`` all live in
``sql/sqlcore``.  A class here only validates its arguments, keeps its operands
as public attributes and builds one handle in :meth:`_handle`.

The operands stay mutable after construction, so every class computes its
handle on demand instead of storing one.
"""
import warnings
from array import array

from sql import Expression, Null, _C, _list, _make, _node, _param, _NONE

__all__ = ['And', 'Or', 'Not', 'Less', 'Greater', 'LessEqual', 'GreaterEqual',
    'Equal', 'NotEqual', 'Between', 'NotBetween', 'IsDistinct',
    'IsNotDistinct', 'Is', 'IsNot', 'Add', 'Sub', 'Mul', 'Div', 'FloorDiv',
    'Mod', 'Pow', 'SquareRoot', 'CubeRoot', 'Factorial', 'Abs', 'BAnd', 'BOr',
    'BXor', 'BNot', 'LShift', 'RShift', 'Concat', 'Like', 'NotLike', 'ILike',
    'NotILike', 'In', 'NotIn', 'Exists', 'Any', 'Some', 'All']

_OP_BINARY = _C['OP_BINARY']
_OP_UNARY = _C['OP_UNARY']
_OP_NARY = _C['OP_NARY']
_OP_BETWEEN = _C['OP_BETWEEN']
_OP_IS = _C['OP_IS']
_OP_LIKE = _C['OP_LIKE']

_BETWEEN_OPERAND = _C['BETWEEN_OPERAND']
_BETWEEN_LEFT = _C['BETWEEN_LEFT']
_BETWEEN_RIGHT = _C['BETWEEN_RIGHT']
_BETWEEN_SLOTS = _C['BETWEEN_SLOTS']

_LIKE_LEFT = _C['LIKE_LEFT']
_LIKE_RIGHT = _C['LIKE_RIGHT']
_LIKE_ESCAPE = _C['LIKE_ESCAPE']
_LIKE_SLOTS = _C['LIKE_SLOTS']

_NULL = _make(_C['OP_NULL'])


def _operand(value):
    """Handle for a value in operand position.

    ``None`` is a parameter, not an absent slot, and a sequence is a
    parenthesised list; everything else follows :func:`sql._node`.
    """
    if value is None:
        return _param(None)
    if isinstance(value, (list, tuple, array)):
        return _list(value)
    return _node(value)


class Operator(Expression):
    __slots__ = ()

    @property
    def table(self):
        return ''

    @property
    def name(self):
        return ''

    @property
    def _operands(self):
        return ()

    def _handle(self):
        raise NotImplementedError

    def __and__(self, other):
        if isinstance(other, And):
            return And([self] + other)
        else:
            return And((self, other))

    def __or__(self, other):
        if isinstance(other, Or):
            return Or([self] + other)
        else:
            return Or((self, other))


class UnaryOperator(Operator):
    __slots__ = ('operand',)
    _operator = ''

    def __init__(self, operand):
        self.operand = operand

    @property
    def _operands(self):
        return (self.operand,)

    def _handle(self):
        return _make(
            _OP_UNARY, (_operand(self.operand),), 0, 0, self._operator)


class BinaryOperator(Operator):
    __slots__ = ('left', 'right')
    _operator = ''

    def __init__(self, left, right):
        self.left = left
        self.right = right

    @property
    def _operands(self):
        return (self.left, self.right)

    def _handle(self):
        left, right = self._operands
        return _make(
            _OP_BINARY, (_operand(left), _operand(right)), 0, 0,
            self._operator)

    def __invert__(self):
        return _INVERT[self.__class__](self.left, self.right)


class NaryOperator(list, Operator):
    __slots__ = ()
    _operator = ''

    @property
    def _operands(self):
        return self

    def _handle(self):
        return _make(
            _OP_NARY, tuple(_operand(o) for o in self), 0, 0, self._operator)


def _define_operator(name, base, operator):
    operator_type = type(name, (base,), {
        '__module__': __name__,
        '__slots__': (),
        '_operator': operator,
    })
    globals()[name] = operator_type
    return operator_type

And = _define_operator('And', NaryOperator, 'AND')
Or = _define_operator('Or', NaryOperator, 'OR')
Not = _define_operator('Not', UnaryOperator, 'NOT')
Neg = _define_operator('Neg', UnaryOperator, '-')
Pos = _define_operator('Pos', UnaryOperator, '+')


Less = _define_operator('Less', BinaryOperator, '<')
Greater = _define_operator('Greater', BinaryOperator, '>')
LessEqual = _define_operator('LessEqual', BinaryOperator, '<=')
GreaterEqual = _define_operator('GreaterEqual', BinaryOperator, '>=')


class Equal(BinaryOperator):
    __slots__ = ()
    _operator = '='

    @property
    def _operands(self):
        if self.left is Null:
            return (self.right,)
        elif self.right is Null:
            return (self.left,)
        return (self.left, self.right)

    def _handle(self):
        # A NULL side turns the comparison into IS [NOT] NULL in the core.
        left = _NULL if self.left is Null else _operand(self.left)
        right = _NULL if self.right is Null else _operand(self.right)
        return _make(_OP_BINARY, (left, right), 0, 0, self._operator)


NotEqual = _define_operator('NotEqual', Equal, '!=')


class Between(Operator):
    __slots__ = ('operand', 'left', 'right', 'symmetric')
    _operator = 'BETWEEN'

    def __init__(self, operand, left, right, symmetric=False):
        self.operand = operand
        self.left = left
        self.right = right
        self.symmetric = symmetric

    @property
    def _operands(self):
        return (self.operand, self.left, self.right)

    def _handle(self):
        operator = self._operator
        if self.symmetric:
            operator += ' SYMMETRIC'
        kids = [_NONE] * _BETWEEN_SLOTS
        kids[_BETWEEN_OPERAND] = _operand(self.operand)
        kids[_BETWEEN_LEFT] = _operand(self.left)
        kids[_BETWEEN_RIGHT] = _operand(self.right)
        return _make(_OP_BETWEEN, tuple(kids), 0, 0, operator)

    def __invert__(self):
        return _INVERT[self.__class__](
            self.operand, self.left, self.right, self.symmetric)


class NotBetween(Between):
    __slots__ = ()
    _operator = 'NOT BETWEEN'


IsDistinct = _define_operator('IsDistinct', BinaryOperator, 'IS DISTINCT FROM')
IsNotDistinct = _define_operator(
    'IsNotDistinct', IsDistinct, 'IS NOT DISTINCT FROM')


class Is(BinaryOperator):
    __slots__ = ()
    _operator = 'IS'

    def __init__(self, left, right):
        if right not in {None, True, False}:
            raise ValueError("invalid right: %r" % right)
        super(Is, self).__init__(left, right)

    @property
    def _operands(self):
        return (self.left,)

    def _handle(self):
        right = self.right
        if right is None:
            words = 'UNKNOWN'
        elif right is True:
            words = 'TRUE'
        elif right is False:
            words = 'FALSE'
        else:
            raise ValueError("invalid right: %r" % right)
        return _make(
            _OP_IS, (_operand(self.left),), 0, 0, self._operator, words)


IsNot = _define_operator('IsNot', Is, 'IS NOT')


Add = _define_operator('Add', BinaryOperator, '+')
Sub = _define_operator('Sub', BinaryOperator, '-')
Mul = _define_operator('Mul', BinaryOperator, '*')
Div = _define_operator('Div', BinaryOperator, '/')


# For backward compatibility
class FloorDiv(BinaryOperator):
    __slots__ = ()
    _operator = '/'

    def __init__(self, left, right):
        warnings.warn('FloorDiv operator is deprecated, use Div function',
            DeprecationWarning, stacklevel=2)
        super(FloorDiv, self).__init__(left, right)


Mod = _define_operator('Mod', BinaryOperator, '%')
Pow = _define_operator('Pow', BinaryOperator, '^')
SquareRoot = _define_operator('SquareRoot', UnaryOperator, '|/')
CubeRoot = _define_operator('CubeRoot', UnaryOperator, '||/')
Factorial = _define_operator('Factorial', UnaryOperator, '!!')
Abs = _define_operator('Abs', UnaryOperator, '@')
BAnd = _define_operator('BAnd', BinaryOperator, '&')
BOr = _define_operator('BOr', BinaryOperator, '|')
BXor = _define_operator('BXor', BinaryOperator, '#')
BNot = _define_operator('BNot', UnaryOperator, '~')
LShift = _define_operator('LShift', BinaryOperator, '<<')
RShift = _define_operator('RShift', BinaryOperator, '>>')
Concat = _define_operator('Concat', BinaryOperator, '||')


class Like(BinaryOperator):
    __slots__ = ('escape',)
    _operator = 'LIKE'

    def __init__(self, left, right, escape=None):
        super().__init__(left, right)
        if escape and len(escape) != 1:
            raise ValueError("invalid escape: %r" % escape)
        self.escape = escape

    def _handle(self):
        kids = [_NONE] * _LIKE_SLOTS
        kids[_LIKE_LEFT] = _operand(self.left)
        kids[_LIKE_RIGHT] = _operand(self.right)
        if self.escape:
            kids[_LIKE_ESCAPE] = _param(self.escape)
        return _make(_OP_LIKE, tuple(kids), 0, 0, self._operator)

    def __invert__(self):
        return _INVERT[self.__class__](self.left, self.right, self.escape)


NotLike = _define_operator('NotLike', Like, 'NOT LIKE')
# The core falls back to UPPER(...) LIKE UPPER(...) without Flavor.ilike.
ILike = _define_operator('ILike', Like, 'ILIKE')
NotILike = _define_operator('NotILike', ILike, 'NOT ILIKE')

# TODO SIMILAR


In = _define_operator('In', BinaryOperator, 'IN')
NotIn = _define_operator('NotIn', BinaryOperator, 'NOT IN')
Exists = _define_operator('Exists', UnaryOperator, 'EXISTS')

class _ArrayOperator(UnaryOperator):
    __slots__ = ()

    def _handle(self):
        operand = self.operand
        if isinstance(operand, (list, tuple, array)):
            # The whole sequence is a single parameter, not a value list.
            return _make(
                _OP_UNARY, (_param(list(operand)),), 0, 0, self._operator)
        return super()._handle()


Any = _define_operator('Any', _ArrayOperator, 'ANY')
Some = Any
All = _define_operator('All', _ArrayOperator, 'ALL')


_INVERT = {
    Less: GreaterEqual,
    Greater: LessEqual,
    LessEqual: Greater,
    GreaterEqual: Less,
    Equal: NotEqual,
    NotEqual: Equal,
    Between: NotBetween,
    NotBetween: Between,
    IsDistinct: IsNotDistinct,
    IsNotDistinct: IsDistinct,
    Is: IsNot,
    IsNot: Is,
    Like: NotLike,
    NotLike: Like,
    ILike: NotILike,
    NotILike: ILike,
    In: NotIn,
    NotIn: In,
    }
