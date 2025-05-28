from datetime import date
from typing import Optional

from pydantic import BaseModel


class RecyclingColTypeWithCount(BaseModel):
    name: str
    company_count: int
    activity_type: int
    color: str


class RecyclablesTotalWeightByCategory(BaseModel):
    recyclables: str
    total_weight_sum: float


class GraphPoint(BaseModel):
    value: Optional[int]
    date: Optional[date]


class Graph(BaseModel):
    points: list[GraphPoint]


class TotalResponse(BaseModel):
    graph: Graph
    total: int


class TotalCompanies(BaseModel):
    total: int
    recycling_count: list[RecyclingColTypeWithCount]


class TotalEmployees(BaseModel):
    total: int
    logists: int
    managers: int
    users: int
    admins: int


class ExchangeVolume(BaseModel):
    total: int
