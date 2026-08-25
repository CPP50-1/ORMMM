"""Unit tests for ormmm.sql builders — SQL text is rendered, never executed."""

import pytest

from orm_adapter import Customer, Order
from ormmm.fields import QueryExpression
from ormmm.sql import (
    build_create_table,
    build_delete,
    build_insert,
    build_search,
    build_search_by_ids,
    build_update,
    build_where_clause,
)


def render(composed, adapter) -> str:
    """Materialize a psycopg composed SQL object to plain text."""
    return composed.as_string(adapter.db.conn)


@pytest.mark.usefixtures("orm")
class TestBuildWhereClause:
    def test_empty_domain_gives_no_clause(self):
        assert build_where_clause([]) == (None, [])

    def test_expression_and_tuple_forms_agree(self, adapter):
        from_expr = build_where_clause([Customer.city == "Liege"])
        from_tuple = build_where_clause([("city", "=", "Liege")])
        assert render(from_expr[0], adapter) == render(from_tuple[0], adapter)
        assert from_expr[1] == from_tuple[1] == ["Liege"]

    def test_quoted_identifier_and_placeholder(self, adapter):
        clause, params = build_where_clause([("city", "=", "Liege")])
        assert '"city" = %s' in render(clause, adapter)
        assert params == ["Liege"]

    def test_in_operator_uses_any_with_list_param(self, adapter):
        clause, params = build_where_clause([("id", "in", [1, 2, 3])])
        assert "= ANY" in render(clause, adapter)
        assert params == [[1, 2, 3]]

    @pytest.mark.parametrize(("op", "keyword"), [("like", "LIKE"), ("ilike", "ILIKE"), ("<=", "<="), ("!=", "!=")])
    def test_operator_mapping(self, adapter, op, keyword):
        clause, _ = build_where_clause([("name", op, "x")])
        assert keyword in render(clause, adapter)

    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="unsupported operator"):
            build_where_clause([("city", "eq", "Liege")])

    def test_malformed_domain_element_raises(self):
        with pytest.raises(TypeError, match="Unsupported domain element"):
            build_where_clause(["city"])

    def test_expression_without_field_name_raises(self):
        with pytest.raises(ValueError, match="field_name"):
            build_where_clause([QueryExpression(None, "=", 1)])


class TestBuildCreateTable:
    def test_serial_primary_key_and_lowercase_table(self, adapter):
        text = render(build_create_table(Customer), adapter)
        assert text.startswith('CREATE TABLE IF NOT EXISTS "customer"')
        assert "id SERIAL PRIMARY KEY" in text

    def test_columns_follow_declaration_order(self, adapter):
        text = render(build_create_table(Customer), adapter)
        assert text.index('"name" VARCHAR(50)') < text.index('"city"') < text.index('"vip" BOOLEAN')

    def test_many2one_renders_foreign_key(self, adapter):
        text = render(build_create_table(Order), adapter)
        assert '"customer" INTEGER REFERENCES "customer" (id)' in text


class TestBuildInsert:
    def test_inserts_only_declared_fields_and_returns_id(self, adapter):
        query, params = build_insert(Order, {"reference": "SO001", "amount": 5})
        text = render(query, adapter)
        assert 'INSERT INTO "order" ("reference", "amount")' in text
        assert "RETURNING id" in text
        assert params == ["SO001", 5]

    def test_undeclared_keys_are_dropped(self, adapter):
        query, params = build_insert(Order, {"reference": "SO001", "bogus": "x"})
        assert "bogus" not in render(query, adapter)
        assert params == ["SO001"]

    def test_empty_values_raise(self):
        with pytest.raises(ValueError, match="no column values to insert"):
            build_insert(Order, {})


class TestBuildUpdate:
    def test_set_only_provided_fields(self, adapter):
        query, params = build_update(Order, {"amount": 42})
        text = render(query, adapter)
        assert '"amount" = %s' in text
        assert '"reference"' not in text
        assert params == [42]

    def test_id_is_not_part_of_the_set_clause(self, adapter):
        text = render(build_update(Order, {"amount": 1})[0], adapter)
        assert "SET" in text and '"id" =' not in text

    def test_empty_values_raise(self):
        with pytest.raises(ValueError, match="no column values to update"):
            build_update(Order, {})


class TestBuildDeleteAndSearch:
    def test_delete_targets_single_id(self, adapter):
        query, params = build_delete(Order, 7)
        assert render(query, adapter) == 'DELETE FROM "order" WHERE id = %s'
        assert params == [7]

    def test_search_without_domain_is_naked_select(self, adapter):
        query, params = build_search(Order, [])
        assert render(query, adapter) == 'SELECT * FROM "order"'
        assert params == []

    def test_search_with_domain_appends_where(self, adapter):
        query, params = build_search(Order, [("amount", ">", 100)])
        text = render(query, adapter)
        assert text.startswith('SELECT * FROM "order" WHERE')
        assert params == [100]

    def test_search_by_ids_keeps_order_and_list_param(self, adapter):
        query, params = build_search_by_ids(Customer, [3, 1, 2])
        assert "= ANY(%s)" in render(query, adapter)
        assert params == [[3, 1, 2]]
