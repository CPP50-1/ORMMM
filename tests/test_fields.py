"""Unit tests for ormmm.fields: QueryExpression, the Field base, and scalar field types."""

import pytest

from ormmm.fields import (
    BigIntField,
    BooleanField,
    CharField,
    DecimalField,
    Field,
    IntegerField,
    QueryExpression,
    SmallIntField,
    TextField,
)


class Host:
    """Plain descriptor host — binds field names without any database."""

    amount = IntegerField()
    label = CharField(max_length=10)
    mandatory = CharField(required=True)
    free = CharField()


class TestQueryExpression:
    def test_to_sql_returns_pair(self):
        expr = QueryExpression("city", "=", "Liege")
        assert expr.to_sql() == ("city = %s", "Liege")

    def test_field_comparison_produces_expression(self):
        expr = Host.amount == 5
        assert isinstance(expr, QueryExpression)
        assert (expr.field_name, expr.operator, expr.value) == ("amount", "=", 5)

    @pytest.mark.parametrize(
        ("dunder", "op"),
        [("__lt__", "<"), ("__gt__", ">"), ("__le__", "<="), ("__ge__", ">="), ("__ne__", "!=")],
    )
    def test_ordering_dunders(self, dunder, op):
        expr = getattr(Host.amount, dunder)(10)
        assert (expr.field_name, expr.operator, expr.value) == ("amount", op, 10)

    def test_in_converts_to_tuple(self):
        expr = Host.amount.in_([1, 2, 3])
        assert expr.operator == "in"
        assert expr.value == (1, 2, 3)

    def test_unbound_field_has_no_name(self):
        loose = CharField()
        expr = loose == 1
        assert expr.field_name is None

    def test_field_is_hashable(self):
        _ = {Host.amount, Host.label}
        assert hash(Field("INTEGER")) is not None


class TestDescriptorSemantics:
    def test_required_rejects_none(self):
        host = Host()
        with pytest.raises(ValueError, match="mandatory"):
            host.mandatory = None

    def test_optional_accepts_none(self):
        host = Host()
        host.free = None
        assert host.free is None

    def test_value_roundtrip_through_dict(self):
        host = Host()
        host.label = "Ada"
        assert host.__dict__["label"] == "Ada"
        assert host.label == "Ada"

    def test_class_access_returns_descriptor(self):
        assert isinstance(Host.amount, IntegerField)


class TestScalarSqlTypes:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            (CharField(), "VARCHAR(50)"),
            (CharField(max_length=120), "VARCHAR(120)"),
            (TextField(), "TEXT"),
            (BooleanField(), "BOOLEAN"),
            (IntegerField(), "INTEGER"),
            (SmallIntField(), "SMALLINT"),
            (BigIntField(), "BIGINT"),
            (DecimalField((8, 3)), "DECIMAL(8,3)"),
            (DecimalField("6,2"), "DECIMAL(6,2)"),
        ],
    )
    def test_sql_type(self, field, expected):
        assert field.sql_type == expected

    def test_kwargs_flow_to_base(self):
        assert BooleanField(required=True).required is True


class TestDecimalFieldValidation:
    def test_string_with_wrong_arity_raises(self):
        with pytest.raises(ValueError, match="amount of values"):
            DecimalField("6")

    def test_non_numeric_parts_raise(self):
        with pytest.raises(TypeError, match="argument types"):
            DecimalField("a,b")

    def test_precision_below_one_raises(self):
        with pytest.raises(ValueError, match="incorrect value"):
            DecimalField("0,2")

    def test_precision_below_scale_raises(self):
        with pytest.raises(ValueError, match="incorrect value"):
            DecimalField("2,4")
