"""Fixtures for the mini-ORM acceptance suite. Do not edit - fill in orm_adapter.py."""

import pytest
from orm_adapter import Adapter


def pytest_configure(config):
    config.addinivalue_line("markers", "must: required for acceptance (spec MUST)")
    config.addinivalue_line("markers", "should: expected but negotiable (spec SHOULD)")
    for level in range(1, 8):
        config.addinivalue_line("markers", f"l{level}: level {level}")


@pytest.fixture(scope="session")
def adapter():
    a = Adapter()
    a.setup()
    yield a
    a.teardown()


@pytest.fixture
def orm(adapter):
    """Clean database + clean caches before each test."""
    adapter.reset_data()
    adapter.reset_queries()
    return adapter


@pytest.fixture
def models(orm):
    return orm.models


@pytest.fixture
def dataset(orm, models):
    """5 customers, 50 orders spread over them, 3 tags on the first 10 orders.

    Fixed shape so query counts are comparable between groups.
    """
    customers = [
        models.Customer.create(
            {"name": f"Customer {i}", "city": "Liege", "vip": i == 0}
        )
        for i in range(5)
    ]
    tags = [models.Tag.create({"name": f"tag-{i}"}) for i in range(3)]
    orders = []
    for i in range(50):
        order = models.Order.create(
            {
                "reference": f"SO{i:03d}",
                "amount": 100 + i,
                "customer": customers[i % 5],
            }
        )
        if i < 10:
            order.write({"tags": tags})
        orders.append(order)
    orm.reset_queries()
    return type("Dataset", (), {"customers": customers, "orders": orders, "tags": tags})
