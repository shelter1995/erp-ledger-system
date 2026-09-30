"""Order-year filtering is independent of receipt/payment dates."""
from typing import Annotated
from fastapi import Query

OrderYear = Annotated[int | None, Query(ge=1900, le=2099)]


def apply_order_year(conditions, params, year, column='order_date'):
    if year is None:
        return
    conditions.extend([f'{column} >= :order_year_start', f'{column} < :order_year_end'])
    params.update(order_year_start=f'{year:04d}-01-01', order_year_end=f'{year + 1:04d}-01-01')
