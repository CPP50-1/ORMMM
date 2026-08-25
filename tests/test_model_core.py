"""Unit tests for ormmm.models core: ModelMeta, Model identity and verb guards, RecordSet."""

import pytest

from orm_adapter import Customer, Order, Tag
from ormmm import cache
from ormmm.models import Model, clear_cache, registry


class PremiumCustomer(Customer):
    """Inherits Customer fields; never mapped to a table of its own."""


@pytest.mark.usefixtures("orm")
class TestModelMeta:
    def test_subclass_inherits_parent_fields(self):
        for name in ("name", "city", "vip", "id"):
            assert name in PremiumCustomer._fields

    def test_base_model_has_no_id_field(self):
        assert "id" not in Model._fields
        assert "id" in Customer._fields

    def test_registry_keys_are_lowercase(self):
        assert registry["customer"] is Customer
        assert registry["order"] is Order
        assert registry["tag"] is Tag

    def test_unknown_registry_key_is_absent(self):
        assert registry.get("ghost") is None


@pytest.mark.usefixtures("orm")
class TestIdentity:
    def test_two_browses_of_same_id_are_equal(self):
        customer = Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        cid = customer.id
        assert cid is not None
        assert Customer.browse(cid) == Customer.browse(cid)

    def test_equal_records_deduplicate_in_a_set(self):
        customer = Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        cid = customer.id
        assert cid is not None
        assert len({Customer.browse(cid), Customer.browse(cid)}) == 1

    def test_different_models_are_never_equal(self):
        customer = Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        tag = Tag.create({"name": "urgent"})
        cid, tid = customer.id, tag.id
        assert cid is not None and tid is not None
        assert Customer.browse(cid) != Tag.browse(tid)

    def test_comparison_with_non_model_returns_not_implemented(self):
        customer = Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        cid = customer.id
        assert cid is not None
        assert Customer.browse(cid).__eq__("not a record") is NotImplemented


@pytest.mark.usefixtures("orm")
class TestVerbGuards:
    def test_save_on_persisted_record_is_not_supported_yet(self):
        customer = Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        with pytest.raises(NotImplementedError, match="UPDATE"):
            customer.save()

    def test_write_on_unsaved_record_is_a_silent_noop(self, orm):
        draft = Customer(name="Ada", city="Liege", vip=True)
        orm.reset_queries()
        draft.write({"name": "Grace"})
        assert orm.query_count() == 0
        assert draft.name == "Ada"

    def test_unlink_on_unsaved_record_is_a_noop(self, orm):
        draft = Customer(name="Ada", city="Liege", vip=True)
        orm.reset_queries()
        draft.unlink()
        assert orm.query_count() == 0
        assert draft.id is None

    def test_clear_cache_alias_empties_the_value_cache(self):
        cache.put(Customer, 1, {"name": "Ada"})
        clear_cache()
        assert cache.get(Customer, 1) is None


@pytest.mark.usefixtures("orm")
class TestRecordSet:
    def test_getitem_evaluates_exactly_once(self, orm):
        Order.create({"reference": "SO001", "amount": 100})
        orm.reset_queries()
        rs = Order.search([])
        first = rs[0]
        assert orm.query_count() == 1
        assert isinstance(first, Order)
        assert orm.query_count() == 1

    def test_slice_returns_plain_list(self):
        rs = Order.search([])
        top_two = rs[0:2]
        assert isinstance(top_two, list)
        assert len(top_two) <= 2

    def test_repr_reflects_evaluation_state(self):
        rs = Order.search([])
        assert "cached=False" in repr(rs)
        len(rs)
        assert "cached=True" in repr(rs)

    def test_bool_on_empty_result_costs_one_query(self, orm):
        rs = Order.search([("amount", ">", 10**9)])
        assert not rs
        assert orm.query_count() == 1
