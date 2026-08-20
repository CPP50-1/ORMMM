class Field:


    def __init__(self, field_type):
        self.field_type = field_type


    def __set_name__(self, owner, name):
        self.name = name


    def __get__(self, instance, owner = None):
        if instance is None:
            return self
        return instance.__dict__.__get__(self.name)


    def __set__(self, instance, value):

        #Added field type validation
        if not isinstance(value, self.field_type):
            raise TypeError(
                f"{self.name} must be of type {self.field_type.__name__}"
            )
        #End: field type validation

        instance.__dict__[self.name] = value        #A dictionary or other mapping object used to store an object's (writable) attributes.


    def __delete__(self, instance):
        pass

class Lightorm:
    pass
