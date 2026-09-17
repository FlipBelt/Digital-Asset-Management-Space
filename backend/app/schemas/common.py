# ruff: noqa: UP046

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class ListResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination
