"""Unit tests for Many2oneField semantics (steps 1-4: required, typing, string targets, lazy fetch)."""

import pytest

from orm_adapter import Customer
from ormmm import cache
from ormmm.fields import CharField, Many2oneField
from ormmm.models import Model


class StrictOrder(Model):
    """Order variant with a mandatory customer link."""

    reference = CharField()
    customer = Many2oneField(Customer, required=True)


class Cart:
    """Plain descriptor host — no DB needed for __set__ semantics."""

    required_link = Many2oneField(Customer, required=True)
    optional_link = Many2oneField(Customer)


def ada() -> Customer:
    return Customer(id=7, name="Ada")


class TestRequiredMany2one:
    def test_required_field_rejects_none(self):
        cart = Cart()
        with pytest.raises(ValueError, match="mandatory"):
            cart.required_link = None

    def test_optional_field_accepts_none(self):
        cart = Cart()
        cart.optional_link = None
        assert cart.optional_link is None

    def test_required_field_still_accepts_records(self):
        cart = Cart()
        cart.required_link = ada()
        # Read the raw slot: the get path still browses eagerly until step 4
        assert cart.__dict__["required_link"] == 7

    def test_create_without_mandatory_link_raises(self, orm):
        with pytest.raises(ValueError, match="mandatory"):
            StrictOrder.create({"reference": "SO001"})


class Tagged(Model):
    """Wrong-type donor for assignment validation."""

    name = CharField()


class TestTypedAssignment:
    def test_record_of_wrong_model_rejected(self):
        cart = Cart()
        with pytest.raises(TypeError, match="expects a Customer"):
            cart.optional_link = Tagged(id=1)

    def test_unsaved_record_rejected(self):
        cart = Cart()
        with pytest.raises(TypeError, match="unsaved"):
            cart.optional_link = Customer(name="Ada")

    def test_bool_rejected_as_id(self):
        cart = Cart()
        with pytest.raises(TypeError, match="int id"):
            cart.optional_link = True

    def test_non_int_scalar_rejected(self):
        cart = Cart()
        with pytest.raises(TypeError, match="int id"):
            cart.optional_link = "7"

    def test_valid_record_stores_its_id(self):
        cart = Cart()
        cart.optional_link = ada()
        assert cart.__dict__["optional_link"] == 7

    def test_raw_int_id_accepted(self):
        cart = Cart()
        cart.optional_link = 42
        assert cart.__dict__["optional_link"] == 42


class TestLazyLoading:
    """Deferred-fetch semantics (browse returns a placeholder, fields load on read)."""

    def test_browse_and_id_are_free(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        orm.reset_queries()
        placeholder = models.Customer.browse(customer.id)
        assert placeholder.id == customer.id
        assert orm.query_count() == 0

    def test_first_read_queries_once_then_instance_stays_loaded(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        placeholder = models.Customer.browse(customer.id)
        orm.reset_queries()
        assert placeholder.name == "Ada"
        assert orm.query_count() == 1
        assert placeholder.vip is True
        assert orm.query_count() == 1

    def test_separate_placeholders_load_independently(self, orm, models):
        """No cross-instance caching: each unloaded handle pays its own query (L6)."""
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        first = models.Customer.browse(customer.id)
        second = models.Customer.browse(customer.id)
        orm.reset_queries()
        _ = first.name
        _ = second.name
        assert orm.query_count() == 2

    def test_lazy_parent_loads_before_following_the_link(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        order = models.Order.create({"reference": "SO001", "amount": 100, "customer": customer})
        orm.reset_queries()
        lazy_order = models.Order.browse(order.id)
        related = lazy_order.customer
        assert orm.query_count() == 1, "loading the parent row should be the only query"
        assert related.id == customer.id
        assert orm.query_count() == 1, "reading the FK id must not trigger another query"

    def test_prefetched_row_loads_without_sql(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        placeholder = models.Customer.browse(customer.id)
        cache.put(
            models.Customer,
            customer.id,
            {"id": customer.id, "name": "Ada", "city": "Liege", "vip": True},
        )
        orm.reset_queries()
        assert placeholder.name == "Ada"
        assert orm.query_count() == 0

    def test_missing_row_raises_on_field_read_not_on_browse(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        orm.db.raw_execute("DELETE FROM customer WHERE id = %s", (customer.id,))
        orm.reset_queries()
        placeholder = models.Customer.browse(customer.id)
        with pytest.raises(LookupError):
            _ = placeholder.name
