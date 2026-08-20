"""
Mini-ORM — Adapter (ONE FILE TO FILL IN PER GROUP)
===================================================

The acceptance suite (`test_acceptance.py`) is identical for every group.
It never imports your ORM directly: it goes through this adapter.

That is deliberate. The *public API verbs* are fixed by the spec (create /
write / search / unlink / browse, `record.field`, `recordset.filtered(...)`),
but the *internals* — Active Record vs Data Mapper, per-instance values vs
central cache, explicit vs automatic prefetch — are your architectural
decision. This file is where your decision meets the fixed contract.

Fill in every method below. Nothing else in the test suite should be edited.
If a test seems impossible to satisfy with your design, that is a signal
about the design — raise it in the review, do not patch the test.

--------------------------------------------------------------------------
FIXED CONTRACT (assumed by the suite — do not change)
--------------------------------------------------------------------------
Models to declare (exactly these names and fields):

    Customer:  name (Char), city (Char), vip (Boolean)
               orders  -> One2many of Order, reverse of Order.customer
    Order:     reference (Char), amount (Integer)
               customer -> Many2one to Customer
               tags     -> Many2many to Tag
               amount_ttc -> computed: amount * 121 // 100   (integer cents-free)
    Tag:       name (Char)
               orders  -> Many2many reverse of Order.tags

Registry keys: lowercase class name -> "customer", "order", "tag".

Domain format (Odoo-style list of 3-tuples), operators required:
    [('city', '=', 'Liege')]
    [('amount', '>', 100)]
    [('id', 'in', [1, 2, 3])]
    []                      # match all

API verbs:
    Model.create({...})          -> one record
    Model.search(domain)         -> RecordSet (lazy)
    Model.browse(id)             -> one record (or 1-length recordset)
    record.write({...})          -> updates the row
    record.unlink()              -> deletes the row
    record.<char/int/bool field> -> the python value
    record.<many2one>            -> a record (NOT an int id)
    record.<one2many/many2many>  -> a RecordSet
    recordset.filtered(fn)       -> RecordSet
    len(rs), bool(rs), iter(rs), rs[0]

Two conventions the suite relies on:
    - a many2one is assigned with a *record*:  Order.create({'customer': cust})
    - a many2many is assigned with a *list of records*: order.write({'tags': [t1, t2]})
"""

from contextlib import contextmanager


class Adapter:
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self):
        """Connect to PostgreSQL, declare the three models, create the tables.

        Called once per test session. Must leave the schema in a usable state.
        """
        raise NotImplementedError

    def teardown(self):
        """Drop the tables / close the connection. Called once at the end."""
        raise NotImplementedError

    def reset_data(self):
        """Empty all rows (TRUNCATE ... RESTART IDENTITY CASCADE) between tests.

        Also clear any in-memory cache / identity map / session your
        architecture keeps, otherwise tests will leak into each other.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def models(self):
        """Return SimpleNamespace(Customer=..., Order=..., Tag=...)."""
        raise NotImplementedError

    def registry_lookup(self, key):
        """Return the model class registered under `key` ("customer", ...).

        Return None if the key is unknown — do not raise.
        """
        raise NotImplementedError

    def table_name(self, model):
        """Return the PostgreSQL table name backing `model`."""
        raise NotImplementedError

    def m2m_table_name(self):
        """Return the junction table name generated for Order.tags."""
        raise NotImplementedError

    def raw_sql(self, sql, params=None):
        """Execute raw SQL out-of-band and return a list of tuples.

        Used by the suite only for schema introspection. It must NOT be
        counted by your query counter (or reset the counter afterwards).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Query instrumentation  (spec 5.6 — the counter is a MUST, build it early)
    # ------------------------------------------------------------------

    def reset_queries(self):
        """Reset the executed-query counter to zero."""
        raise NotImplementedError

    def query_count(self):
        """Return the number of SQL statements executed since the last reset."""
        raise NotImplementedError

    def query_log(self):
        """Return the list of SQL statements executed since the last reset.

        Only used for diagnostics in failure messages. Return [] if you have
        no log (the counter alone is enough to pass).
        """
        return []

    # ------------------------------------------------------------------
    # Prefetch strategy  (this is where architectures diverge the most)
    # ------------------------------------------------------------------

    def prefetch(self, recordset, field_name):
        """Batch-load `field_name` for every record of `recordset` in ONE query.

        - Explicit-prefetch architectures (A / D): call your public API here,
          e.g. `recordset.prefetch(field_name)` or `recordset.mapped(field_name)`.
        - Automatic-prefetch architectures (B, Odoo-style): this can be a no-op
          (`return recordset`) since access already batches.
        """
        raise NotImplementedError

    @contextmanager
    def without_prefetch(self):
        """Context manager that DISABLES any automatic batching.

        Inside this block, iterating a recordset and touching a Many2one must
        produce the naive one-query-per-record pattern. This is what makes the
        N+1 *measurable* rather than merely asserted.

        - Explicit-prefetch architectures: no-op (`yield`), the naive path is
          already the default.
        - Automatic-prefetch architectures: flip your prefetch flag off here
          and restore it on exit.
        """
        raise NotImplementedError
        yield  # noqa
