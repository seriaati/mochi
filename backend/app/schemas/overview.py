from pydantic import BaseModel


class EarningsOut(BaseModel):
    """Money received in a calendar year, up to today. All NTD."""

    year: int
    months: list[int]  # received in each month, January first
    total: int
    previous_total: int  # the year before, from 1 January to the same date
    change_percent: int | None  # total vs previous_total; None when that is 0
