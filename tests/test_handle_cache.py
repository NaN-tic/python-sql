import unittest

from sql import From, Table


class HandleCacheTestCase(unittest.TestCase):

    def setUp(self):
        self.table = Table('test')

    def test_reuses_native_tree(self):
        query = self.table.select(self.table.id)

        tuple(query)
        tuple(query)
        first = query._node_handle
        tuple(query)

        self.assertIs(query._node_handle, first)

    def test_query_setter_invalidates_parent(self):
        query = self.table.select(self.table.id)
        self.assertEqual(tuple(query)[1], ())
        self.assertEqual(tuple(query)[1], ())

        query.where = self.table.id == 1

        self.assertEqual(tuple(query)[1], (1,))

    def test_expression_mutation_invalidates_parent(self):
        condition = self.table.id == 1
        query = self.table.select(self.table.id, where=condition)
        self.assertEqual(tuple(query)[1], (1,))
        self.assertEqual(tuple(query)[1], (1,))

        condition.right = 2

        self.assertEqual(tuple(query)[1], (2,))

    def test_subquery_mutation_invalidates_outer_query(self):
        inner = self.table.select(self.table.id)
        outer = inner.select(inner.id)
        self.assertEqual(tuple(outer)[1], ())
        self.assertEqual(tuple(outer)[1], ())

        inner.where = self.table.id == 3

        self.assertEqual(tuple(outer)[1], (3,))

    def test_nary_list_mutation_invalidates_parent(self):
        condition = (self.table.id == 1) & (self.table.id == 2)
        query = self.table.select(self.table.id, where=condition)
        self.assertEqual(tuple(query)[1], (1, 2))
        self.assertEqual(tuple(query)[1], (1, 2))

        condition.append(self.table.id == 3)

        self.assertEqual(tuple(query)[1], (1, 2, 3))

    def test_from_list_mutation_invalidates_query(self):
        from_ = From([self.table])
        query = from_.select(self.table.id)
        self.assertNotIn('"other"', tuple(query)[0])
        self.assertNotIn('"other"', tuple(query)[0])

        query.from_.append(Table('other'))

        self.assertIn('"other"', tuple(query)[0])

    def test_external_operand_list_keeps_identity_and_invalidates(self):
        values = [1, 2]
        condition = self.table.id.in_(values)
        query = self.table.select(self.table.id, where=condition)
        self.assertIs(condition.right, values)
        self.assertEqual(tuple(query)[1], (1, 2))
        self.assertEqual(tuple(query)[1], (1, 2))

        values.append(3)

        self.assertEqual(tuple(query)[1], (1, 2, 3))

    def test_large_container_uses_uncached_fallback(self):
        values = list(range(65))
        query = self.table.select(
            self.table.id, where=self.table.id.in_(values))
        self.assertEqual(tuple(query)[1], tuple(values))
        self.assertEqual(tuple(query)[1], tuple(values))

        values.append(65)

        self.assertEqual(tuple(query)[1], tuple(values))


if __name__ == '__main__':
    unittest.main()
