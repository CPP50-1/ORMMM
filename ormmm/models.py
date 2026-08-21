from typing import Any, ClassVar

from .fields import Field, IntField

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
            id_field = IntField(required=True)
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
        pass

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
