"""Money flow across all statements: monthly in vs out, totals by category, and a category's trend.

Months are "YYYY-MM". Own-account transfers (Transfer to/from Self) are left out by default, so
moving money between your own accounts doesn't count as income or spending.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from app.categorising.categories import CATEGORIES, SELF_TRANSFERS, UNCATEGORISED
from app.db import get_session
from app.models import Transaction
from app.schemas import CategoryTotal, MonthlyFlow, TrendPoint

router = APIRouter(prefix="/api/analytics")
SessionDep = Annotated[Session, Depends(get_session)]
Month = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")]

ZERO = Decimal("0.00")


def month_start(month: str) -> dt.date:
    year, number = map(int, month.split("-"))
    return dt.date(year, number, 1)


def next_month(day: dt.date) -> dt.date:
    return dt.date(day.year + day.month // 12, day.month % 12 + 1, 1)


def months_between(first: dt.date, last: dt.date) -> list[str]:
    months, day = [], first.replace(day=1)
    while day <= last:
        months.append(day.strftime("%Y-%m"))
        day = next_month(day)
    return months


def filtered[*Ts](query: Select[*Ts], start: str | None, end: str | None, exclude_self: bool) -> Select[*Ts]:
    if start:
        query = query.where(Transaction.date >= month_start(start))
    if end:
        query = query.where(Transaction.date < next_month(month_start(end)))
    if exclude_self:
        query = query.where(or_(Transaction.category.is_(None), Transaction.category.not_in(SELF_TRANSFERS)))
    return query


def month_of() -> ColumnElement[dt.datetime]:
    return func.date_trunc("month", Transaction.date)


def fill_months(totals: dict[str, Decimal], start: str | None, end: str | None) -> list[str]:
    """Every month in the period, including months without transactions."""
    if not totals and not (start and end):
        return []
    first = month_start(start) if start else month_start(min(totals))
    last = month_start(end) if end else month_start(max(totals))
    return months_between(first, last)


@router.get("/monthly")
def monthly(
    session: SessionDep,
    start: Annotated[Month, Query(alias="from")] = None,
    end: Annotated[Month, Query(alias="to")] = None,
    exclude_self: bool = True,
) -> list[MonthlyFlow]:
    month = month_of()
    query = filtered(
        select(month, func.sum(Transaction.credit), func.sum(Transaction.debit)).group_by(month),
        start,
        end,
        exclude_self,
    )
    rows = {m.strftime("%Y-%m"): (money_in, money_out) for m, money_in, money_out in session.execute(query)}
    flows = []
    for key in fill_months({k: ZERO for k in rows}, start, end):
        money_in, money_out = rows.get(key, (ZERO, ZERO))
        flows.append(MonthlyFlow(month=key, money_in=money_in, money_out=money_out, net=money_in - money_out))
    return flows


@router.get("/categories")
def by_category(
    session: SessionDep,
    direction: Literal["out", "in"] = "out",
    start: Annotated[Month, Query(alias="from")] = None,
    end: Annotated[Month, Query(alias="to")] = None,
    exclude_self: bool = True,
) -> list[CategoryTotal]:
    amount = Transaction.debit if direction == "out" else Transaction.credit
    category = func.coalesce(Transaction.category, UNCATEGORISED)
    query = filtered(
        select(category, func.sum(amount), func.count()).where(amount > 0).group_by(category),
        start,
        end,
        exclude_self,
    )
    totals = [CategoryTotal(category=name, total=total, count=count) for name, total, count in session.execute(query)]
    return sorted(totals, key=lambda t: t.total, reverse=True)


@router.get("/trend")
def trend(
    session: SessionDep,
    category: str,
    start: Annotated[Month, Query(alias="from")] = None,
    end: Annotated[Month, Query(alias="to")] = None,
) -> list[TrendPoint]:
    if category in CATEGORIES["out"]:
        amount = Transaction.debit
    elif category in CATEGORIES["in"]:
        amount = Transaction.credit
    else:
        raise HTTPException(422, f"Unknown category {category!r}")
    month = month_of()
    query = filtered(
        select(month, func.sum(amount)).where(Transaction.category == category).group_by(month),
        start,
        end,
        exclude_self=False,
    )
    totals = {m.strftime("%Y-%m"): total for m, total in session.execute(query)}
    return [TrendPoint(month=key, total=totals.get(key, ZERO)) for key in fill_months(totals, start, end)]
