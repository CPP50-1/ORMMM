from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar, Self

from .db import DB
from .fields import Field, IntegerField
from .sql import build_delete, build_insert, build_search, build_update

registry = {}

# Shared value cache indexed by (model_class, id) as per ADR
_record_cache = {}


def clear_cache() -> None:
    """Clear the shared record cache. Called between tests to prevent leaks."""
    _record_cache.clear()


class RecordSet:
    def __init__(self, model_class: type, domain: list, records: list | None = None):
        self.model_class = model_class
        self.domain = domain
        # If records is provided (ex: after a filter), the cache is preemptively filled
        self._cache: list | None = records

    def filtered(self, predicate_lambda) -> RecordSet:
        """[MUST 5.5] Allows chain-searching without executing raw SQL multiple times"""
        # Evaluate the current RecordSet to obtain instantiated memory items
        records = self._evaluate()
        # Apply the user's filter
        filtered_records = [r for r in records if predicate_lambda(r)]
        # Returns a new RecordSet with the cache already populated
        return RecordSet(self.model_class, self.domain, records=filtered_records)

    def _evaluate(self) -> list:
        """Internal method executing the SQL request as late as possible"""
        if self._cache is not None:
            return self._cache

        if self.model_class._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")

        # 1. Hand over the request generation to sql.py
        query, params = build_search(self.model_class, self.domain)

        # 2. Execute the request via global connection [MUST 5.2]
        cursor = self.model_class._db.execute(query, params)
        rows = cursor.fetchall()

        # 3. Extract columns to instanciate models
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        self._cache = []
        for row in rows:
            if isinstance(row, tuple):
                row_data = dict(zip(col_names, row, strict=True))
            else:
                row_data = row

            record = self.model_class(**row_data)
            # Cache the record
            _record_cache[(self.model_class, record.id)] = record
            self._cache.append(record)

        return self._cache

    # --- [MUST 5.5] Late/lazy evaluation triggers ---
    def __len__(self) -> int:
        return len(self._evaluate())

    def __bool__(self) -> bool:
        return bool(self._evaluate())

    def __iter__(self) -> Iterator:
        return iter(self._evaluate())

    def __repr__(self) -> str:
        # For debugging
        return f"<RecordSet {self.model_class.__name__} (cached={self._cache is not None})>"

    def __getitem__(self, index: int | slice) -> Any:
        """
        Allows record access via brackets (ex: records[0]).
        Triggers SQL request evaluation if it hasn't already happened.
        """
        return self._evaluate()[index]


class ModelMeta(type):
    def __new__(mcs, name: str, bases: tuple, attrs: dict[str, Any]):
        # 1. Collect fields from parent classes
        fields: dict[str, Field] = {}
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # 2. Add fields from current class
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, Field):
                attr_value.__set_name__(None, attr_name)
                fields[attr_name] = attr_value

        # 3. Auto-add id field if not present and not base Model
        if name != "Model" and "id" not in fields:
            id_field = IntegerField(required=True)
            id_field.__set_name__(None, "id")
            fields["id"] = id_field

        # 4. Store fields on the class
        attrs["_fields"] = fields

        # 5. Create the class
        cls = super().__new__(mcs, name, bases, attrs)

        # 6. Register in registry (except base class) - lowercase key
        if name != "Model":
            registry[name.lower()] = cls

        return cls


class Model(metaclass=ModelMeta):
    _fields: ClassVar[dict[str, Field]] = {}
    _db: ClassVar[DB | None] = None

    @classmethod
    def set_db(cls, db: DB) -> None:
        """Designate the shared connection wrapper; every model issues SQL through it."""
        Model._db = db

    def __init__(self, **kwargs):
        # Access _fields through class to avoid type checker issues with ClassVar
        for field_name, field in self.__class__._fields.items():
            value = kwargs.get(field_name, getattr(field, "default", None))
            setattr(self, field_name, value)

    def __eq__(self, other: object) -> bool:
        """Identity based on (model class, id) as per ADR §5."""
        if not isinstance(other, Model):
            return NotImplemented
        return type(self) is type(other) and self.id == other.id

    def __hash__(self) -> int:
        """Hash based on (model class, id) as per ADR §5."""
        return hash((type(self), self.id))

    @classmethod
    def create(cls, values: dict) -> Self:
        instance = cls(**values)
        instance.save()
        # Cache the created instance
        _record_cache[(cls, instance.id)] = instance
        return instance

    def save(self):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")
        # Use __dict__ directly to bypass descriptors (especially Many2one which returns records, not IDs)
        # Access _fields through class to avoid type checker issues with ClassVar
        values = {name: self.__dict__.get(name) for name in self.__class__._fields if name != "id"}
        if self.id is None:
            row = Model._db.execute(*build_insert(type(self), values)).fetchone()
            if row is None:
                raise RuntimeError(f"INSERT ... RETURNING id returned no row for {type(self).__name__}")
            self.id = row[0]
        else:
            raise NotImplementedError("UPDATE not implemented yet")

    @classmethod
    def search(cls, domain: list | None = None) -> RecordSet:
        """
        [MUST 5.5] No SQL trigger upon call.
        Returns a lazy RecordSet object.
        """
        if domain is None:
            domain = []
        return RecordSet(model_class=cls, domain=domain)

    @classmethod
    def browse(cls, record_id) -> Self:
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")

        # Check cache first as per ADR
        cache_key = (cls, record_id)
        if cache_key in _record_cache:
            return _record_cache[cache_key]

        query, params = build_search(cls, [("id", "=", record_id)])
        cursor = Model._db.execute(query, params)

        # Walrus assignment
        if (row := cursor.fetchone()) is None:
            raise LookupError(f"{cls.__name__} with id={record_id} not found")

        if (description := cursor.description) is None:
            raise LookupError(f"{cls.__name__} with id={record_id}: query returned no description")

        col_names = [d[0] for d in description]
        record = cls(**dict(zip(col_names, row, strict=True)))

        # Store in cache
        _record_cache[cache_key] = record
        return record

    def write(self, values: dict):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")

        query, params = build_update(self.__class__, values)
        params.append(self.id)
        Model._db.execute(query, params)
        # Update in-memory attributes
        # Access _fields through class to avoid type checker issues with ClassVar
        for key, value in values.items():
            if key in self.__class__._fields and key != "id":
                # Use direct __dict__ assignment to bypass descriptors
                # This ensures Many2one fields store IDs, not records
                self.__dict__[key] = value

    def unlink(self):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")
        if self.id is not None:
            Model._db.execute(*build_delete(type(self), self.id))
            self.id = None
