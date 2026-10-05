from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, StringConstraints

T = TypeVar("T")

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Short codes such as LOS, HR, EMP-0101: letters, digits, "-" and "_"; stored in upper case.
# (The pattern is checked before upper-casing, so it must accept lower case too.)
Code = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$"
    ),
]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
Phone = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=32, pattern=r"^\+?[0-9 ()-]{5,31}$")
]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1"),
        page_size: int = Query(50, ge=1, le=200, description="Rows per page (max 200)"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
