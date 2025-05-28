from typing import Optional

from pydantic import BaseModel

from statistic.api.models import Graph


class ManagerPaymentsOutput(BaseModel):
    graph: Graph
    total_sum_of_sells: Optional[int]
    total_vtorprice_earnings: Optional[int]


class TotalForMonth(BaseModel):
    total: int
