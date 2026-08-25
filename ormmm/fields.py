from typing import Any


class QueryExpression:
    def __init__(self, field_name: str | None, operator: str, value: Any):
        self.field_name = field_name
        self.operator = operator
        self.value = value

    def to_sql(self) -> tuple[str, Any]:
        """Returns the parametered SQL piece and its associated value."""
        return f"{self.field_name} {self.operator} %s", self.value


class Field:
    def __init__(self, sql_type: str, *, required: bool = False, **kwargs):
        self.sql_type = sql_type
        self.required = required
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self

        # If the instance is lazy and this field has not been loaded from DB yet
        if self.name not in instance.__dict__ and getattr(instance, "_lazy", False):
            instance._load()

        # Read stored value from instance storage (__dict__)
        return instance.__dict__.get(self.name)

    def __set__(self, instance, value):
        if self.required and value is None:
            raise ValueError(f"{self.name} is mandatory.")
        instance.__dict__[self.name] = value

    def __repr__(self):
        class_name = self.__class__.__name__
        attributes = []
        for key, value in sorted(self.__dict__.items()):
            attributes.append(f"{key}={value!r}")
        attr_string = ", ".join(attributes)
        return f"<{class_name} {attr_string}>"

    def __eq__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, "=", other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __lt__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, "<", other)

    def __gt__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, ">", other)

    def __le__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, "<=", other)

    def __ge__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, ">=", other)

    def __ne__(self, other: Any) -> QueryExpression:
        return QueryExpression(self.name, "!=", other)

    def in_(self, values: Any) -> QueryExpression:
        """Special method to manage the membership operator IN (ex: Customer.id.in_([1, 2]))"""
        # Forced conversion into tuple because, in the psycopg language, a tuple becomes a SQL list(1, 2, 3)
        # while a list becomes an ARRAY[1, 2, 3]
        return QueryExpression(self.name, "in", tuple(values))


class CharField(Field):
    def __init__(self, max_length: int = 50, **kwargs):
        super().__init__(f"VARCHAR({max_length})", **kwargs)


class TextField(Field):
    def __init__(self, **kwargs):
        super().__init__("TEXT", **kwargs)


class BooleanField(Field):
    def __init__(self, **kwargs):
        super().__init__("BOOLEAN", **kwargs)


class IntegerField(Field):
    def __init__(self, **kwargs):
        super().__init__("INTEGER", **kwargs)


class SmallIntField(Field):
    def __init__(self, **kwargs):
        super().__init__("SMALLINT", **kwargs)


class BigIntField(Field):
    def __init__(self, **kwargs):
        super().__init__("BIGINT", **kwargs)


class DecimalField(Field):
    def __init__(self, values: tuple[int, int] | str = (6,2), /, **kwargs):
        if isinstance(values, tuple):
            precision, scale = values

        elif isinstance(values, str):
            v = values.split(",")
            if len(v) != 2:
                raise ValueError("incorrect amount of values given to DecimalField.")

            parts = [part.strip() for part in v]
            if not (parts[0].isdigit() and parts[1].isdigit()):
                raise TypeError("incorrect argument types given to DecimalField.")

            precision = int(parts[0])
            scale = int(parts[1])
            if precision < 1 or scale < 0 or precision < scale:
                raise ValueError("incorrect value(s) given to DecimalField.")

        super().__init__(f"DECIMAL({precision},{scale})", **kwargs)


class Many2oneField(Field):
    """Many2one relationship field. Stores the foreign key ID, returns the related record."""

    def __init__(self, target_model, **kwargs):
        self.target_model = target_model  # The related model class
        super().__init__("INTEGER", **kwargs)

    def __get__(self, instance, owner):
        if instance is None:
            return self

        # If parent instance is lazy and has not loaded its columns (including the FK) yet
        if self.name not in instance.__dict__ and getattr(instance, "_lazy", False):
            instance._load()

        # Retrieve integer ID stored in __dict__ (foreign key)
        id_value = instance.__dict__.get(self.name)

        if id_value is None:
            return None

        # Return a lazy instance of the target model without issuing SQL queries
        return self.target_model.browse(id_value)

    def __set__(self, instance, value):
        if value is None:
            instance.__dict__[self.name] = None
            return

        # Import Model here to avoid circular imports
        from .models import Model

        if isinstance(value, Model):
            # Store the ID of the related record
            instance.__dict__[self.name] = value.id
        else:
            # Assume it's already an ID (integer)
            instance.__dict__[self.name] = value

