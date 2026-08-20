# Mini-ORM - which architectures are possible?

The technical spec fixes the **public API** and the acceptance criteria.
It does **not** fix the internal architecture. This document describes four
coherent directions and what each one costs.

Read this before coding, then decide as a group in 30 minutes max. The choice should be
written down (see "Architecture decision" at the end).

---

## 1. The two real questions

The name of the architecture doesn't matter much. Everything follows from two decisions:

**Q1 - Where do field values live?**
On the Python instance (`self._values['name']`), or in a central cache indexed by
`(model, id, field)`?

**Q2 - What does a query return?**
Full Python objects (one instance = one row), or a lightweight object that only holds
ids and fetches columns on demand?

Everything else - laziness, prefetch, N+1, record identity - is a consequence of these
two answers. If the group only agrees on one thing, make it these.

---

## 2. The four directions

### A - Classic Active Record (Django-style)

One Python instance = one row. Values are stored in a `dict` carried by the instance,
written by `Field.__set__`. `Model.search(domain)` returns a `RecordSet` that keeps the
domain and only materializes instances on iteration.

A `Many2one` stores the raw id; its `__get__` does a `Related.browse(id)`, so **one
query per access** - N+1 appears naturally, without having to engineer it. The fix is an
explicit `recordset.prefetch('customer')` that does one `WHERE id IN (...)` and fills a
cache carried by the recordset.

_Why pick this:_ it's the shortest mental model. The descriptor protocol is obvious here
(value per instance, not on the class - exactly what §5.1 asks for). Dirty-tracking to
only write modified columns is trivial (a `set` of dirty fields).

_What it costs:_ two `browse(1)` calls produce two distinct objects that can diverge (no
identity map). The prefetch cache lives on the recordset, so a record that "escapes" its
recordset loses the benefit. Acceptable here, but worth being able to explain.

**Risk: low.** The default direction for a group unsure of its pace.

---

### B - Recordset + central cache (Odoo-style)

A record is just a pair `(model, ids)` plus a reference to an environment. **Nothing**
is stored on the instance. Values live in a central cache
`{(model, id, field): value}`.

The key point: when `Field.__get__` doesn't find `(order, 42, 'customer')` in the cache,
it doesn't load the value just for record 42 - it loads it **for every id in the current
recordset**, in one query. N+1 doesn't disappear via a fix: it never exists, it's
absorbed by the architecture.

`filtered()` returns a new recordset over a subset of ids, with no query at all - the
§5.5 SHOULD ("narrowing without re-query") falls out for free.

_Why pick this:_ it's literally the mechanism they'll find again at Odoo (recordset,
`env`, cache, prefetch set). Transfer to the internship is maximal. And the OOP module
gains real weight: `__iter__`, `__len__`, `__bool__`, `__getitem__`,
`__eq__`/`__hash__` on `(model, ids)` become structural, not decorative.

_What it costs:_ to **demonstrate** N+1 (§5.6 MUST), you need a flag that disables
prefetch - an excellent exercise, but it has to be planned from the start, not
discovered on day 4. The idea that "the value lives neither on the class nor the
instance" is confusing at first and needs to be verbalized.

**Risk: medium to high.** For a solid group that has digested descriptors + metaclasses.

---

### C - Data Mapper + Unit of Work (SQLAlchemy-style)

Business classes stay (mostly) ignorant of persistence. A `Session` carries an identity
map `{(Model, pk): object}` and a list of pending changes; `session.add()`, then
`session.flush()` translates state into INSERT/UPDATE/DELETE in dependency order.
Descriptors no longer store a value: they _register a change_ against the instance's
state.

_Why pick this:_ it's the other major ORM pattern, the one they'll meet outside Odoo.
The separation is clean, the identity map solves A's identity problem, and flush
ordering is a real engineering lesson.

_What it costs:_ a lot of machinery for four days. The spec's verbs (an explicit
`write()`) sit awkwardly with an implicit flush. The real risk is ending up with a
beautiful Session and none of the three relation types.

**Risk: high.** Reserve for a group clearly ahead of schedule - or treat as
reading/comparison rather than implementation.

---

### D - Pragmatic hybrid _(default recommendation)_

Public API in Active Record style with the Odoo verbs (`create` / `write` / `search` /
`unlink` / `browse`), plus two borrowings from B:

- a **shared value cache** indexed by `(model, id, field)`, without going all the way to
  a full environment or an automatic prefetch set;
- a **connection wrapper** that counts and logs every query, written on day one.

Prefetch stays **explicit and deliberate** (`recs.prefetch('customer')`), which keeps the
before/after measurement clean and the N+1 exercise readable.

_Why this is the default:_ it keeps A's simplicity where it costs nothing, and borrows
from B the one idea that matters pedagogically - the shared cache that makes
batch-loading possible. It's also the direction that leaves the most room to shift
toward B on day 3 if the group is moving fast: the cache is already there, all that's
left is making prefetch automatic.

**Risk: low to medium.**

---

## 3. Comparison

|                    | A - Active Record     | B - Recordset/cache                     | C - Data Mapper          | D - Hybrid                  |
| ------------------ | --------------------- | --------------------------------------- | ------------------------ | --------------------------- |
| Values stored      | on the instance       | central cache                           | instance state + session | central cache               |
| `search()` returns | lazy recordset        | recordset of ids                        | `Query`                  | lazy recordset              |
| N+1                | natural, explicit fix | absorbed, must be _disabled_ to show it | `selectinload`           | natural, explicit fix       |
| Record identity    | not guaranteed        | guaranteed by `(model, id)`             | identity map             | guaranteed by `(model, id)` |
| Closeness to Odoo  | medium                | **maximal**                             | low                      | good                        |
| Conceptual load    | low                   | high                                    | **very high**            | medium                      |
| Feasible in 4 days | yes                   | yes, if group is solid                  | risky                    | yes                         |

---

## 4. Cross-cutting decisions to make explicit

Regardless of A/B/C/D, these five points must be decided at the beginning of the project
and written down.

1. **Filter format.** Odoo-style domain `[('city', '=', 'Liege')]`, kwargs
   `filter(city='Liege')`, or expression objects (operator overloading on fields,
   `Customer.city == 'Liege'`). The spec requires the domain; the third option is an
   excellent stretch goal if everything else is green.
2. **Where SQL is generated.** Each field produces its own SQL, or a central
   `SqlBuilder` where fields only expose `sql_type`. The central builder is strongly
   recommended: one place to secure against injection, one place to review.
3. **The query counter is a foundation, not a finishing touch.** §5.6 requires
   _measuring_. A cursor wrapper that increments a counter and logs SQL costs fifteen
   lines on day 1 and makes everything else observable. Written on day 4, it forces
   reopening all the execution code.
4. **Where laziness stops.** Which call triggers the query: `__iter__`, `__len__`,
   `__bool__`, `__getitem__`? Write the list down explicitly, or half the group will
   assume `search()` already queried and the other half won't.
5. **Equality and identity.** Does `browse(1) == browse(1)` return `True`? If so,
   `__eq__` **and** `__hash__` on `(model, id)` - otherwise records can't be used in a
   `set` or as dict keys, and the prefetch cache breaks. (This is exactly the day-1
   exercise from the OOP module, applied for real.)

---

## 5. One arbitration point worth knowing

§5.5 requires that `search()` trigger **no** query and that it fire on evaluation
(`len()`, `bool()`, iteration). That's a Django QuerySet's semantics.

This is **not** how Odoo behaves: there, `search()` executes a query immediately and
returns ids; what's lazy is reading the _columns_.

Both are defensible and both teach laziness. But if a group goes with architecture B
"like Odoo," they still need to defer id resolution to satisfy the test - either by
storing the domain and resolving it on first access, or by accepting the gap and
justifying it in review.

---

## 6. Deliverable for architecture

A written **architecture decision**, versioned in the repo (`ADR.md`):

- direction chosen (A / B / C / D or an explicit hybrid) and the reason in three lines;
- answers to the five cross-cutting decisions in §4;
- what the group is knowingly giving up (e.g. "no identity map, we accept that two
  `browse` calls give two objects - we document the limitation");
- the exact signature of the five public verbs.

This document is revisited as-is in the final code review: the question won't be "was
this the right architecture?" but "did you hold to yours, and can you say what it cost
you?"
