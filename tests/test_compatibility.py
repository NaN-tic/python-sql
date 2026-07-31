import inspect
import unittest

import sql
from sql import (
    As, Asc, Cast, Collate, FromItem, Grouping, Literal, Matched,
    MatchedUpdate, Merge, NotMatchedInsert, Query, Rollup, Select, Table,
    Values, Window, WithQuery,
)
from sql.conditionals import Case


class CompatibilityTestCase(unittest.TestCase):

    def setUp(self):
        self.table = Table('test')

    def test_public_metadata(self):
        self.assertEqual(sql.__version__, '1.8.1')
        self.assertEqual(
            sql.__all__,
            [
                'Flavor', 'Table', 'Values', 'Literal', 'Column', 'Grouping',
                'Conflict', 'Matched', 'MatchedUpdate', 'MatchedDelete',
                'NotMatched', 'NotMatchedInsert', 'Rollup', 'Cube',
                'Excluded', 'Join', 'Asc', 'Desc', 'NullsFirst', 'NullsLast',
                'format2numeric',
            ],
        )

    def test_public_signatures(self):
        expected = {
            Select: (
                '(columns, from_=None, where=None, group_by=None, '
                'having=None, for_=None, distinct=False, distinct_on=None, '
                'windows=None, **kwargs)'
            ),
            Values: '(iterable=(), /)',
            Window: (
                '(partition, order_by=None, frame=None, start=None, end=0, '
                'exclude=None)'
            ),
            Merge: '(target, source, condition, *whens, **kwargs)',
            MatchedUpdate: '(columns, values, **kwargs)',
            NotMatchedInsert: '(columns, values, **kwargs)',
        }
        for value, signature in expected.items():
            with self.subTest(value=value):
                self.assertEqual(str(inspect.signature(value)), signature)

    def test_public_inheritance(self):
        self.assertTrue(issubclass(Values, list))
        self.assertTrue(issubclass(Values, Query))
        self.assertTrue(issubclass(Values, FromItem))
        self.assertTrue(issubclass(Select, FromItem))
        self.assertTrue(issubclass(Select, WithQuery))
        self.assertFalse(issubclass(Window, sql.Expression))

    def test_values_preserves_list_contract(self):
        values = Values([[1]])
        values.append([2])
        values[0][0] = 3

        self.assertEqual(list(values), [[3], [2]])
        self.assertEqual(values[:1], [[3]])
        self.assertEqual(str(values), 'VALUES (%s), (%s)')
        self.assertEqual(values.params, (3, 2))

    def test_literal_value_is_read_only(self):
        literal = Literal(1)

        with self.assertRaises(AttributeError):
            literal.value = 2

    def test_mutable_expression_wrappers_rebuild_native_nodes(self):
        collate = Collate(self.table.a, 'first')
        order = Asc(self.table.a)
        cast = Cast(self.table.a, 'INTEGER')

        str(collate)
        str(order)
        str(cast)
        collate.expression = self.table.b
        collate.collation = 'second'
        order.expression = self.table.b
        cast.expression = self.table.b
        cast.typename = 'TEXT'

        self.assertEqual(str(collate), '"b" COLLATE "second"')
        self.assertEqual(str(order), '"b" ASC')
        self.assertEqual(str(cast), 'CAST("b" AS TEXT)')

    def test_mutable_grouping_nodes_rebuild_native_nodes(self):
        grouping = Grouping((self.table.a,))
        rollup = Rollup(self.table.a)

        str(grouping)
        str(rollup)
        grouping.sets = ((self.table.b,),)
        rollup.expressions = (self.table.b,)

        self.assertEqual(str(grouping), 'GROUPING SETS (("b"))')
        self.assertEqual(str(rollup), 'ROLLUP ("b")')

    def test_cached_query_observes_wrapper_mutations(self):
        alias = As(self.table.a, 'first')
        case = Case((self.table.a == 1, 'one'), else_='other')
        query = self.table.select(alias, case)
        tuple(query)
        tuple(query)

        alias.expression = self.table.b
        alias.output_name = 'second'
        case.whens = ((self.table.b == 2, 'two'),)
        case.else_ = 'fallback'

        self.assertEqual(
            str(query),
            'SELECT "a"."b" AS "second", '
            'CASE WHEN "a"."b" = %s THEN %s ELSE %s END '
            'FROM "test" AS "a"',
        )
        self.assertEqual(query.params, (2, 'two', 'fallback'))

    def test_simple_matched_condition_omits_parentheses_like_original(self):
        matched = Matched(self.table.a == 1)

        self.assertEqual(
            str(matched),
            'WHEN MATCHED AND "a" = %s THEN DO NOTHING',
        )
        self.assertEqual(matched.params, (1,))


if __name__ == '__main__':
    unittest.main()
