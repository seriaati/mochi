from datetime import date

from pydantic import BaseModel

from app.income import Source
from app.models import Collection


class Ref(BaseModel):
    id: int
    name: str


class IncomeEntry(BaseModel):
    """Money received, as the Overview's earnings count it. NTD."""

    paid_on: date  # auto transfers: the month's due date
    amount: int
    source: Source
    client: Ref  # who paid
    project: Ref | None  # what for: the project, the addition's, or the retainer's if any
    addition: Ref | None
    collection: Collection | None  # retainers only
    days_late: int | None  # retainers only: days paid after the due date, 0 when on time
    late: bool | None  # retainers only: paid more than the grace days after the due date


class IncomeOut(BaseModel):
    today: date  # in the saved timezone
    entries: list[IncomeEntry]  # oldest first
