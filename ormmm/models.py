from typing import Any, ClassVar

from .db import DB
from .fields import Field, IntegerField
from .sql import build_insert

registry = {}


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
        for field_name, field in self._fields.items():
            value = kwargs.get(field_name, getattr(field, "default", None))
            setattr(self, field_name, value)

    @classmethod
    def create(cls, values: dict):
        instance = cls(**values)
        instance.save()
        return instance

    def save(self):
        if Model._db is None:
            raise RuntimeError("no database set: call Model.set_db() first")
        values = {name: getattr(self, name) for name in self._fields if name != "id"}
        if self.id is None:
            row = Model._db.execute(*build_insert(type(self), values)).fetchone()
            if row is None:
                raise RuntimeError(f"INSERT ... RETURNING id returned no row for {type(self).__name__}")
            self.id = row[0]
        else:
            raise NotImplementedError("UPDATE not implemented yet")

    @classmethod
    def search(cls, domain: list):
        return []

    @classmethod
    def browse(cls, id):
        return cls()

    def write(self, values: dict):
        for key, value in values.items():
            setattr(self, key, value)

    def unlink(self):
        pass
