class Field:

    def __init__(self, sql_type: str, required: bool = False):
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
        instance.__dict__.[self.name] = value

    def __repr__(self):
        class_name = self.__class__.__name__
        attributes = []
        for key, value in sorted(self.__dict__.items()):
            attributes.append(f"{key}={value!r}")
        attr_string = ", ".join(attributes)
        return f"<{class_name} {attr_string}>"
