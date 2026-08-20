**Direction chosen**: D - Pragmatic Hybrid.

Public API in Active Record style with the Odoo verbs (`create` / `write` / `search` /
`unlink` / `browse`), plus two borrowings from B:

- a **shared value cache** indexed by `(model, id, field)`, without going all the way to
  a full environment or an automatic prefetch set;
- a **connection wrapper** that counts and logs every query, written on day one.

Prefetch stays **explicit and deliberate** (`recs.prefetch('customer')`), which keeps the
before/after measurement clean and the N+1 exercise readable.

*Why this is the default:* it keeps A's simplicity where it costs nothing, and borrows
from B the one idea that matters pedagogically - the shared cache that makes
batch-loading possible. It's also the direction that leaves the most room to shift
toward B on day 3 if the group is moving fast: the cache is already there, all that's
left is making prefetch automatic.

=> We chose this approach because, despite being a group of 3 apprentices, we were aimless at the start and didn't want to be overconfident when tackling the exercice.
However, because we are a group of 3, we also didn't want to settle for the "easiest" approach either, as we figured we could get enough work done once the foundations were laid down.

=============================================

1. **Filter format.** Odoo-style domain `[('city', '=', 'Liege')]`, kwargs
   `filter(city='Liege')`, or expression objects (operator overloading on fields,
   `Customer.city == 'Liege'`). The spec requires the domain; the third option is an
   excellent stretch goal if everything else is green.

=> We chose option 3 here (`Customer.city == 'Liege'`) as it looks to be the most "pythonic" syntax.

2. **Where SQL is generated.** Each field produces its own SQL, or a central
   `SqlBuilder` where fields only expose `sql_type`. The central builder is strongly
   recommended: one place to secure against injection, one place to review.

=> The safety and "centrality" of the recommended option convinced us.

3. **The query counter is a foundation, not a finishing touch.** §5.6 requires
   *measuring*. A cursor wrapper that increments a counter and logs SQL costs fifteen
   lines on day 1 and makes everything else observable. Written on day 4, it forces
   reopening all the execution code.

=> No choice to be made here.

4. **Where laziness stops.** Which call triggers the query: `__iter__`, `__len__`,
   `__bool__`, `__getitem__`? Write the list down explicitly, or half the group will
   assume `search()` already queried and the other half won't.

=> Because of the recommendation in the next chapter, targeting the check from §5.5, we had little choice but to make all four of the mentioned dunders trigger the SQL query.
The __init__ializer will have to take care of additional cases to compensate.

5. **Equality and identity.** Does `browse(1) == browse(1)` return `True`? If so,
   `__eq__` **and** `__hash__` on `(model, id)` - otherwise records can't be used in a
   `set` or as dict keys, and the prefetch cache breaks. (This is exactly the day-1
   exercise from the OOP module, applied for real.)

=> `browse(1) == browse(1)` **HAS** to return true for `__eq__` and `__hash__` to work, which is made mandatory by our choice of filter format.
The added benefit is that we get to use all the utilities from dictionaries and sets, like eliminating duplicates with a single line of code `set()`.

=============================================

What the group is knowingly giving up (e.g. "no identity map, we accept that two `browse` calls give two objects - we document the limitation")

=> At the start of the assignment, it is unclear what we are giving up, besides features from the choice of approach we made.

=============================================

The exact signature of the five public verbs.

=> TBA