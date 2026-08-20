# Mini-ORM — measurable objective

> **The direction is the test suite.**
> The internal architecture is free (see `architectures.md`). What's fixed is the
> public API and the 34 tests below. The project is done when
> `pytest -m "must and not should"` is green.

---

## Files

| File                 | Role                                            |
| -------------------- | ----------------------------------------------- |
| `test_acceptance.py` | The acceptance suite, identical for every group |
| `conftest.py`        | Fixtures and the reference dataset              |
| `orm_adapter.py`     | The bridge between your ORM and the suite       |
| `architectures.md`   | Possible directions and their costs             |

The suite never imports your ORM directly: it goes through the adapter. That's what
lets four groups who made four different architecture choices be graded on exactly the
same tests.

## Run it

```bash
pip install pytest psycopg2-binary
createdb mini_orm_test               # local PostgreSQL, no mocking
pytest -q                            # all 34 tests
pytest -q -m "must and not should"   # the acceptance gate (28 tests)
pytest -q -m l3                      # one level at a time
pytest -q -m l6 -s                   # N+1, with query counters printed
```

## The 7 levels

| Level  | Content                                                                       | Tests | Blocking        |
| ------ | ----------------------------------------------------------------------------- | ----- | --------------- |
| **L1** | Field descriptors, metaclass registry, `CREATE TABLE`                         | 5     | MUST            |
| **L2** | `create` / `search` / `write` / `unlink`, parameterized queries               | 7     | MUST            |
| **L3** | `Many2one`: returns a record, not an id; lazy loading                         | 4     | MUST (1 SHOULD) |
| **L4** | `One2many` and `Many2many` (junction table, both directions)                  | 5     | MUST            |
| **L5** | `RecordSet`: lazy evaluation, chainable `filtered()`                          | 6     | MUST (1 SHOULD) |
| **L6** | N+1: demonstrated with a **measurement**, then fixed, with the delta measured | 4     | MUST (1 SHOULD) |
| **L7** | Computed field, not stored, not stale after a write                           | 3     | SHOULD          |

A level shouldn't start before the previous one is green. The dependency chain is real:
without a query counter (L2), L6 isn't measurable; without Many2one (L3), One2many has
nothing to reverse.

## The numbers that define "done"

These are the thresholds coded into the suite, on the reference dataset (5 customers,
50 orders, 3 tags):

| Measurement                                                  | Threshold                                   |
| ------------------------------------------------------------ | ------------------------------------------- |
| `search()` alone, before evaluation                          | **0 queries**                               |
| Naive iteration over 50 orders reading `order.customer.name` | **≥ 50 queries**                            |
| Same scenario after prefetch                                 | **≤ 3 queries**                             |
| Before/after ratio                                           | **≥ 10×**                                   |
| `filtered()` on an already-evaluated recordset               | **0 extra queries**                         |
| SQL injection in a `create()`                                | value stored as-is, **table still present** |
| Computed field after its dependency changes                  | value **recomputed**, not stale             |

A measured number beats a claim in code review. That's the whole point of spec §5.6: N+1
must be **observed**, not described.

## Milestones over 4 days

| End of    | Expected                                                                                     |
| --------- | -------------------------------------------------------------------------------------------- |
| **Day 1** | `ADR.md` written (§6 of `architectures.md`) + L1 green + connection wrapper counting queries |
| **Day 2** | L2 green                                                                                     |
| **Day 3** | L3 and L4 green                                                                              |
| **Day 4** | L5 and L6 green → **acceptance**. L7 and `should` tests are bonus                            |

If L1 isn't green by the end of day 1, that's not a pacing problem: it's a direction
problem. Go back to `architectures.md` §1 and cut scope.

## Deliverables

1. The ORM code + a filled-in `orm_adapter.py`.
2. `ADR.md` - the architecture decision.
3. The output of `pytest -q` pasted into the group's README.
4. Your own pytest suite (spec §5.8). The acceptance suite verifies the external
   contract; it doesn't replace your unit tests on your own internal components.

## What's important :

Green tests, and your ability to explain in review **why** your architecture
makes each test easy or hard.
