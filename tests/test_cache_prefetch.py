"""Unit tests for the shared value cache and explicit prefetch (ADR direction D).

Complements the acceptance suite by pinning the internal contract:
- only prefetch() writes the value cache,
- browse() reads it but never writes it,
- write()/unlink() invalidate it.
"""

import pytest

from ormmm import cache


class TestValueCache:
    """Pure in-memory tests of the (model, id, field) store."""

    def setup_method(self):
        cache.clear()

    def test_get_miss_returns_none(self):
        class A:
            pass

        assert cache.get(A, 1) is None

    def test_put_then_get_roundtrip(self):
        class A:
            pass

        cache.put(A, 1, {"name": "Ada", "vip": True})
        assert cache.get(A, 1) == {"name": "Ada", "vip": True}

    def test_keys_are_per_model_and_per_id(self):
        class A:
            pass

        class B:
            pass

        cache.put(A, 1, {"name": "Ada"})
        cache.put(B, 1, {"name": "Grace"})
        cache.put(A, 2, {"name": "Linus"})
        assert cache.get(B, 1) == {"name": "Grace"}
        assert cache.get(A, 2) == {"name": "Linus"}

    def test_put_merges_partial_rows(self):
        class A:
            pass

        cache.put(A, 1, {"name": "Ada"})
        cache.put(A, 1, {"vip": True})
        assert cache.get(A, 1) == {"name": "Ada", "vip": True}

    def test_drop_invalidates_one_record_only(self):
        class A:
            pass

        cache.put(A, 1, {"name": "Ada"})
        cache.put(A, 2, {"name": "Grace"})
        cache.drop(A, 1)
        assert cache.get(A, 1) is None
        assert cache.get(A, 2) is not None

    def test_clear_empties_everything(self):
        class A:
            pass

        cache.put(A, 1, {"name": "Ada"})
        cache.clear()
        assert cache.get(A, 1) is None


@pytest.mark.usefixtures("orm")
class TestBrowseAndPrefetchQueries:
    """DB-backed tests measuring queries through the adapter counter."""

    def test_create_does_not_warm_the_cache(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        assert cache.get(models.Customer, customer.id) is None

    def test_evaluate_does_not_warm_any_cache(self, orm, models):
        models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        models.Order.create({"reference": "SO001", "amount": 100})
        len(models.Order.search([]))
        assert orm.query_count() >= 1
        assert all(cache.get(models.Order, i) is None for i in range(1, 100))

    def test_browse_returns_placeholder_then_reads_lazily(self, orm, models):
        """browse() itself is free; the query fires when a field is read."""
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        orm.reset_queries()
        placeholder = models.Customer.browse(customer.id)
        assert orm.query_count() == 0
        assert placeholder.name == "Ada"
        assert orm.query_count() == 1

    def test_browse_hits_cache_after_prefetch(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        models.Order.create({"reference": "SO001", "amount": 100, "customer": customer})
        orders = models.Order.search([])
        len(orders)

        orm.reset_queries()
        orders.prefetch("customer")
        assert orm.query_count() == 1

        assert orders[0].customer.name == "Ada"
        assert orm.query_count() == 1

    def test_prefetch_is_idempotent_when_warm(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        models.Order.create({"reference": "SO001", "amount": 100, "customer": customer})
        orders = models.Order.search([])
        len(orders)
        orders.prefetch("customer")

        orm.reset_queries()
        orders.prefetch("customer")
        assert orm.query_count() == 0

    def test_prefetch_scalar_field_is_a_noop(self, orm, models):
        models.Order.create({"reference": "SO001", "amount": 100})
        orders = models.Order.search([])
        len(orders)
        orm.reset_queries()
        assert orders.prefetch("amount") is orders
        assert orm.query_count() == 0

    def test_prefetch_skips_null_links(self, orm, models):
        models.Order.create({"reference": "SO001", "amount": 100})
        orders = models.Order.search([])
        len(orders)
        orm.reset_queries()
        orders.prefetch("customer")
        assert orm.query_count() == 0

    def test_naive_loop_stays_n_plus_1(self, orm, models):
        """Regression guard: without explicit prefetch, every access queries,
        even for repeated targets (the L6 measurement depends on this)."""
        ada = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        grace = models.Customer.create({"name": "Grace", "city": "Namur", "vip": False})
        for i in range(6):
            models.Order.create({"reference": f"SO{i:03d}", "amount": 10 * i, "customer": [ada, grace][i % 2]})
        orders = models.Order.search([])

        orm.reset_queries()
        names = [o.customer.name for o in orders]
        assert len(names) == 6
        # 1 (orders SELECT on evaluation) + 6 (one browse per access)
        assert orm.query_count() >= 7

    def test_write_invalidates_the_cached_row(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        models.Order.create({"reference": "SO001", "amount": 100, "customer": customer})
        orders = models.Order.search([])
        len(orders)
        orders.prefetch("customer")

        customer.write({"name": "Renamed"})
        assert cache.get(models.Customer, customer.id) is None

        orm.reset_queries()
        assert orders[0].customer.name == "Renamed"
        assert orm.query_count() >= 1, "stale cache row served after write()"

    def test_unlink_invalidates_the_cached_row(self, orm, models):
        customer = models.Customer.create({"name": "Ada", "city": "Liege", "vip": True})
        models.Order.create({"reference": "SO001", "amount": 100, "customer": customer})
        orders = models.Order.search([])
        len(orders)
        orders.prefetch("customer")
        assert cache.get(models.Customer, customer.id) is not None

        customer.unlink()
        assert cache.get(models.Customer, customer.id) is None

    def test_prefetch_batch_loads_distinct_targets_in_one_query(self, orm, models):
        customers = [models.Customer.create({"name": f"C{i}", "city": "Liege", "vip": False}) for i in range(5)]
        for i, customer in enumerate(customers * 2):  # 10 orders over 5 distinct targets
            models.Order.create({"reference": f"SO{i:03d}", "amount": i, "customer": customer})
        orders = models.Order.search([])
        len(orders)

        orm.reset_queries()
        orders.prefetch("customer")
        assert orm.query_count() == 1
