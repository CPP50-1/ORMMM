import datetime

from orm_st.main import Field


class TestEntity:
    #name = Field() -> without type validation (deprecated)
    name = Field(str)
    last_name = Field(str)
    birth_date = Field(datetime.date)

    def __str__(self):
        return f"{self.name}, {self.last_name} {self.birth_date}"


test1 = TestEntity()
test1.name = "John"
test1.last_name = "Connor"
test1.birth_date = datetime.date(1985, 2, 28)

test2 = TestEntity()
test2.name = "Sarah"
test2.last_name = "Connor"
test2.birth_date = "1965-08-30"

try:
    print(test1)
    print(test2)
except TypeError:
    print ("TypeError")

