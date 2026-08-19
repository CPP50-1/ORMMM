# ORMMM
Lightweight ORM exercise for CPP50



Internal Engineering Spec
TECHNICAL SPECIFICATION
Mini-ORM: Building a Lightweight Object-Relational Mapper

Team size	2-3 engineers per group
Target stack	Python 3.12, PostgreSQL, psycopg2, pytest
Deliverable	A working mini-ORM library with test coverage, meeting the acceptance criteria in Section 7

1. Purpose
Build a lightweight Object-Relational Mapper (ORM) from scratch: a library that lets a developer declare a Python class with typed fields, and get automatic table creation, CRUD operations, relationship handling, and a chainable query API on top of a real PostgreSQL database, without hand-writing SQL for common operations.
This is the same category of problem as any production ORM (SQLAlchemy, Django ORM, Odoo's ORM…): fields behave as descriptors, models are collected into a central registry, and query results are returned as lazy, chainable collections rather than eagerly-fetched lists.
2. Scope
2.1 In scope
    • Field declaration via descriptors (Char, Integer, Boolean at minimum)
    • A metaclass-based model registry
    • Schema generation (CREATE TABLE) and execution against PostgreSQL
    • CRUD operations: create, write (update), search (select), unlink (delete)
    • Relationships: Many2one, One2many, Many2many
    • A chainable, lazy query API returning recordset-like objects
    • Detection and resolution of an N+1 query pattern
    • At least one computed field
    • Test coverage (pytest) of the above, proportionate to time available
2.2 Out of scope
    • A general-purpose SQL dialect or multi-database support
    • Schema migrations
    • Query plan optimization beyond the N+1 case explicitly required
    • Authentication, authorization, or multi-tenant concerns
    • A formal CI pipeline, tests should pass locally against a real PostgreSQL instance; CI wiring is not required
3. Suggested Order of Work
Build in whatever order works for your group but the dependency chain between pieces makes some orders far smoother than others. The order below is a suggestion, not a requirement:
    1. Foundation first: one working Field descriptor, the metaclass registry, and CREATE TABLE generation for a single simple model. Nothing else can be built before this is solid, every relation type extends it directly.
    2. Many2one before One2many: One2many is a reverse lookup that depends on a working Many2one existing on the other side. Build the forward relation first.
    3. Many2many after both of the above: it reuses the same lazy-resolution idea as Many2one/One2many, plus a generated association table, easier once that pattern is already familiar.
    4. Query API (lazy, chainable RecordSet) once at least one relation type exists: laziness is easiest to reason about once there's a real relation to defer loading on. Building the query counter/instrumentation here also sets up the next step.
    5. N+1 detection and fix last: it requires the query counter, at least one relation type, and the RecordSet from steps above. This is the natural culmination of everything built before it.
    6. Computed field: genuinely independent of the rest, safe to slot in wherever there's spare time, including as a final stretch item if the group is ahead of schedule.
Groups can build together on the foundation, then split sub-tasks within the group for a given step (e.g. one person on the descriptor while another wires up the schema generator for the same relation,but avoid starting a later step before the one it depends on is working end-to-end.
4. Team Structure
For a group of 2-3, strict per-person ownership of a whole relationship type for the entire project adds more coordination overhead than it saves. Instead, here is a suggestion to organize your work:
    • Build the foundation (Section 3, step 1) together, it's the shared base everything else extends.
    • From there, rotate who drives each step rather than assigning permanent ownership of a subsystem, e.g. one person drives Many2one, another drives One2many, then swap for Many2many.
    • Within a 3-person group, sub-split inside a single step is fine (e.g. one person on the descriptor, another on schema generation for the same relation), avoid two people owning entirely separate subsystems in parallel without a working foundation.
    • Short internal review before moving to the next step: don't build Many2many on top of a Many2one that hasn't been tested.
5. System Requirements
Requirements are tagged MUST (required for acceptance) or SHOULD (expected, but negotiable in scope/time).
5.1 Field Descriptors
MUST	A base Field class implementing the descriptor protocol (__get__, __set__, __set_name__), storing values per-instance (not on the class).
MUST	At least CharField, IntegerField, BooleanField subclasses, each mapping to an appropriate PostgreSQL column type.
SHOULD	Basic validation on assignment (type coercion or a clear error on mismatch).

class Field:
    def __set_name__(self, owner, name): ...
    def __get__(self, instance, owner): ...
    def __set__(self, instance, value): ...
 
class CharField(Field):
    sql_type = "VARCHAR"
5.2 Model Registry (Metaclass)
MUST	A metaclass that, on class creation, collects all declared Field instances on a model and registers the model in a global registry keyed by model name.
MUST	Registered models are discoverable at runtime (e.g. registry.get('product')).
SHOULD	Table name derivation from the class name or an explicit _table attribute.
5.3 Schema Generation & CRUD
MUST	Generate a valid CREATE TABLE statement from a model's declared fields and execute it against PostgreSQL.
MUST	Implement create() (INSERT), write() (UPDATE), search() (SELECT), and unlink() (DELETE) as methods usable from application code.
SHOULD	Parameterized queries throughout - no string-formatted SQL with user-supplied values.
5.4 Relations
MUST	Many2one: a descriptor-backed field that stores a foreign key column and, on access, lazily loads and returns the related record (not just the raw id).
MUST	One2many: a reverse accessor that, given a record, returns the set of related records pointing to it via a Many2one on the other model.
MUST	Many2many: a generated association (junction) table, with an accessor returning the related recordset in both directions.
SHOULD	Relation descriptors should not issue a query until the related data is accessed (lazy by default).
5.5 Query API
MUST	Model.search(domain) returns a RecordSet-like object, not a plain list.
MUST	The returned object supports chaining, e.g. Model.search([...]).filtered(lambda r: ...).
MUST	Iteration, len(), and bool() on a RecordSet only trigger the underlying query at the point they're evaluated (lazy evaluation), not at search() call time.
SHOULD	Support combining or narrowing an existing recordset without re-querying from scratch where reasonably possible.
5.6 N+1 Detection & Resolution
MUST	Construct a scenario where iterating over a recordset and accessing a Many2one (or One2many/Many2many) field per record issues one query per record (the N+1 pattern).
MUST	Instrument query execution (a counter or logger) so the N+1 pattern is measurable, not just asserted.
MUST	Implement a fix (batch/prefetch loading) and show the measured query count drop for the same scenario.
5.7 Computed Fields
MUST	At least one field whose value is derived from other fields via a method rather than stored directly.
SHOULD	A caching or invalidation strategy so the computed value isn't silently stale after a dependency changes.
5.8 Testing
MUST	A small pytest suite covering, at minimum: the field descriptors, the model registry, and the N+1 detection/fix - the three pieces the acceptance criteria check.
SHOULD	Additional coverage of relation types (Many2one/One2many/Many2many) as time allows.
SHOULD	Tests run against a real (local) PostgreSQL instance rather than being fully mocked.
6. Working Agreement
    • Keep the group working against one shared registry/schema layer, not parallel private versions of it.
    • A quick informal review before moving to the next step in the suggested order (Section 3) is enough, no formal PR process is required for a group this size.
7. Acceptance Criteria
Criterion	Tag	Verified via
Foundation (descriptor + registry + CREATE TABLE) works end-to-end for a simple model	MUST	Manual demo + basic test
Many2one, One2many, and Many2many all resolve correctly with working joins	MUST	Manual demo, tests where time allows
N+1 pattern is demonstrated AND fixed, with a measured query-count before/after	MUST	Test + query log output
search().filtered(...) chains correctly and evaluates lazily	MUST	Manual demo or test
Computed field returns a correct, non-stale value	SHOULD	Manual demo or test
pytest suite covers at least the Section 5.8 MUST items and passes locally against PostgreSQL	MUST	Local test run

Mini-ORM Project — Technical Specification
