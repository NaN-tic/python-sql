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


class And(NaryOperator):
    __slots__ = ()
    _operator = 'AND'


class Or(NaryOperator):
    __slots__ = ()
    _operator = 'OR'


class Not(UnaryOperator):
    __slots__ = ()
    _operator = 'NOT'


class Neg(UnaryOperator):
    __slots__ = ()
    _operator = '-'


class Pos(UnaryOperator):
    __slots__ = ()
    _operator = '+'


class Less(BinaryOperator):
    __slots__ = ()
    _operator = '<'


class Greater(BinaryOperator):
    __slots__ = ()
    _operator = '>'


class LessEqual(BinaryOperator):
    __slots__ = ()
    _operator = '<='


class GreaterEqual(BinaryOperator):
    __slots__ = ()
    _operator = '>='


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


class NotEqual(Equal):
    __slots__ = ()
    _operator = '!='


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


class IsDistinct(BinaryOperator):
    __slots__ = ()
    _operator = 'IS DISTINCT FROM'


class IsNotDistinct(IsDistinct):
    __slots__ = ()
    _operator = 'IS NOT DISTINCT FROM'


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


class IsNot(Is):
    __slots__ = ()
    _operator = 'IS NOT'


class Add(BinaryOperator):
    __slots__ = ()
    _operator = '+'


class Sub(BinaryOperator):
    __slots__ = ()
    _operator = '-'


class Mul(BinaryOperator):
    __slots__ = ()
    _operator = '*'


class Div(BinaryOperator):
    __slots__ = ()
    _operator = '/'


# For backward compatibility
class FloorDiv(BinaryOperator):
    __slots__ = ()
    _operator = '/'

    def __init__(self, left, right):
        warnings.warn('FloorDiv operator is deprecated, use Div function',
            DeprecationWarning, stacklevel=2)
        super(FloorDiv, self).__init__(left, right)


class Mod(BinaryOperator):
    __slots__ = ()
    # The doubling required by the format paramstyle happens in the core.
    _operator = '%'


class Pow(BinaryOperator):
    __slots__ = ()
    _operator = '^'


class SquareRoot(UnaryOperator):
    __slots__ = ()
    _operator = '|/'


class CubeRoot(UnaryOperator):
    __slots__ = ()
    _operator = '||/'


class Factorial(UnaryOperator):
    __slots__ = ()
    _operator = '!!'


class Abs(UnaryOperator):
    __slots__ = ()
    _operator = '@'


class BAnd(BinaryOperator):
    __slots__ = ()
    _operator = '&'


class BOr(BinaryOperator):
    __slots__ = ()
    _operator = '|'


class BXor(BinaryOperator):
    __slots__ = ()
    _operator = '#'


class BNot(UnaryOperator):
    __slots__ = ()
    _operator = '~'


class LShift(BinaryOperator):
    __slots__ = ()
    _operator = '<<'


class RShift(BinaryOperator):
    __slots__ = ()
    _operator = '>>'


class Concat(BinaryOperator):
    __slots__ = ()
    _operator = '||'


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


class NotLike(Like):
    __slots__ = ()
    _operator = 'NOT LIKE'


class ILike(Like):
    __slots__ = ()
    # The core falls back to UPPER(...) LIKE UPPER(...) without Flavor.ilike.
    _operator = 'ILIKE'


class NotILike(ILike):
    __slots__ = ()
    _operator = 'NOT ILIKE'

# TODO SIMILAR


class In(BinaryOperator):
    __slots__ = ()
    _operator = 'IN'


class NotIn(BinaryOperator):
    __slots__ = ()
    _operator = 'NOT IN'


class Exists(UnaryOperator):
    __slots__ = ()
    _operator = 'EXISTS'


class _ArrayOperator(UnaryOperator):
    __slots__ = ()

    def _handle(self):
        operand = self.operand
        if isinstance(operand, (list, tuple, array)):
            # The whole sequence is a single parameter, not a value list.
            return _make(
                _OP_UNARY, (_param(list(operand)),), 0, 0, self._operator)
        return super()._handle()


class Any(_ArrayOperator):
    __slots__ = ()
    _operator = 'ANY'


Some = Any


class All(_ArrayOperator):
    __slots__ = ()
    _operator = 'ALL'


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
