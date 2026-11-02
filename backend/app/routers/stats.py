from datetime import date

from fastapi import APIRouter

from app import income
from app.clock import TodayDep
from app.db import SessionDep
from app.schemas.stats import IncomeEntry, IncomeOut, Ref

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _ref(record: object | None) -> Ref | None:
    return None if record is None else Ref.model_validate(record, from_attributes=True)


@router.get("/income")
def income_entries(session: SessionDep, today: TodayDep) -> IncomeOut:
    """All money received up to today, for the Stats page to slice."""
    received = sorted(
        income.received(session, date.min, today), key=lambda r: (r.paid_on, r.source)
    )
    return IncomeOut(
        today=today,
        entries=[
            IncomeEntry(
                paid_on=r.paid_on,
                amount=r.amount,
                source=r.source,
                client=Ref(id=r.client.id, name=r.client.name),
                project=_ref(r.project),
                addition=_ref(r.addition),
                collection=r.collection,
                days_late=r.days_late,
                late=r.late,
            )
            for r in received
        ],
    )
