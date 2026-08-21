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
