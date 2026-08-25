"""Shared value cache indexed by (model, id, field), per ADR direction D.

Write policy (deliberate): only RecordSet.prefetch() writes rows here.
browse() consults it but never writes; create() and search() never touch it.
This keeps the naive N+1 pattern fully measurable while letting one explicit
batch-load collapse it to a single query.
"""

from typing import Any

# model class -> record id -> field name -> value
_values: dict[type, dict[int, dict[str, Any]]] = {}


def get(cls: type, record_id: int) -> dict[str, Any] | None:
    """Return the cached row of (model, id), or None when absent."""
    return _values.get(cls, {}).get(record_id)


def put(cls: type, record_id: int, values: dict[str, Any]) -> None:
    """Merge one row into the cache."""
    _values.setdefault(cls, {}).setdefault(record_id, {}).update(values)


def drop(cls: type, record_id: int) -> None:
    """Invalidate the cached row of a single record."""
    _values.get(cls, {}).pop(record_id, None)


def clear() -> None:
    """Empty the whole cache. Called between tests to prevent leaks."""
    _values.clear()
