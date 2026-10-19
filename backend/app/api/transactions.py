"""Search transactions across all statements, and set categories by hand (one or many at once).

Manual categories are never overwritten by rules, Laya or Jev.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.categorising.categories import UNCATEGORISED, direction_of, is_valid
from app.db import get_session
from app.models import Statement, Transaction
from app.parsing.statement_parser import parse_date
from app.schemas import BulkCategoryUpdate, CategoryUpdate, TransactionOut, TransactionSearch, TransactionSearchRow

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


def as_amount(text: str) -> Decimal | None:
    """'1,234.50' or '₹1234.5' -> Decimal; None if the text isn't a number."""
    cleaned = re.sub(r"[₹,\s]|^rs\.?", "", text.strip().lower())
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def matches(q: str):
    """One search box over every column: narration, masked text, category, bank, other columns,
    amounts (debit, credit or balance equal to a number) and dates (a day, or a YYYY-MM month)."""
    like = f"%{q}%"
    conditions: list[ColumnElement[bool]] = [
        Transaction.particulars.ilike(like),
        Transaction.particulars_masked.ilike(like),
        Transaction.category.ilike(like),
        Statement.bank.ilike(like),
        cast(Transaction.extra, Text).ilike(like),
    ]
    amount = as_amount(q)
    if amount is not None:
        conditions += [Transaction.debit == amount, Transaction.credit == amount, Transaction.balance == amount]
    if month := MONTH_RE.match(q.strip()):
        year, number = int(month[1]), int(month[2])
        if 1 <= number <= 12:
            first = date(year, number, 1)
            after = date(year + number // 12, number % 12 + 1, 1)
            conditions.append(and_(Transaction.date >= first, Transaction.date < after))
    elif (day := parse_date(q)) is not None:
        conditions.append(Transaction.date == day)
    return or_(*conditions)


@router.get("/transactions")
def search_transactions(
    session: SessionDep,
    q: str = "",
    direction: Literal["in", "out"] | None = None,
    category: str | None = Query(None, description=f"a category name, or {UNCATEGORISED!r}"),
    statement_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 2000,
) -> TransactionSearch:
    query = select(Transaction, Statement.bank, Statement.account_number).join(Statement)
    if q.strip():
        query = query.where(matches(q.strip()))
    if direction == "out":
        query = query.where(Transaction.debit > 0)
    elif direction == "in":
        query = query.where(Transaction.debit == 0)
    if category == UNCATEGORISED:
        query = query.where(Transaction.category.is_(None))
    elif category:
        query = query.where(Transaction.category == category)
    if statement_id is not None:
        query = query.where(Transaction.statement_id == statement_id)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Transaction.date.desc(), Transaction.statement_id, Transaction.row_index.desc()).limit(limit)
    ).all()
    return TransactionSearch(total=total, transactions=[search_row(t, bank, account) for t, bank, account in rows])


def search_row(transaction: Transaction, bank: str | None, account_number: str | None) -> TransactionSearchRow:
    return TransactionSearchRow(
        **TransactionOut.model_validate(transaction).model_dump(),
        statement_id=transaction.statement_id,
        bank=bank,
        account_last4=account_number[-4:] if account_number else None,
    )


def set_manual(transaction: Transaction, category: str) -> None:
    transaction.category = category
    transaction.category_source = "manual"
    transaction.category_rule_id = None
    transaction.category_confidence = None
    transaction.categorised_at = datetime.now(UTC)


# Declared before /transactions/{transaction_id} so "bulk" isn't read as an id.
@router.patch("/transactions/bulk")
def update_many(update: BulkCategoryUpdate, session: SessionDep) -> dict[str, int]:
    """Set one category on many transactions. All must be the same direction as the category
    (money out categories for debits, money in for credits); otherwise nothing is changed."""
    ids = set(update.ids)
    transactions = session.scalars(select(Transaction).where(Transaction.id.in_(ids))).all()
    if len(transactions) != len(ids):
        raise HTTPException(404, f"{len(ids) - len(transactions)} of the transactions were not found")
    wrong = [t for t in transactions if not is_valid(update.category, direction_of(t.debit))]
    if wrong:
        raise HTTPException(
            422,
            f"{update.category!r} doesn't fit {len(wrong)} of the {len(ids)} selected transactions "
            "(money in and money out have different categories). Select only one kind.",
        )
    for transaction in transactions:
        set_manual(transaction, update.category)
    session.commit()
    return {"updated": len(transactions)}


@router.patch("/transactions/{transaction_id}")
def update_transaction(transaction_id: int, update: CategoryUpdate, session: SessionDep) -> TransactionOut:
    """Set a category by hand; categorising again never overwrites it."""
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    direction = direction_of(transaction.debit)
    if not is_valid(update.category, direction):
        kind = "money out" if direction == "out" else "money in"
        raise HTTPException(422, f"{update.category!r} is not a {kind} category")
    set_manual(transaction, update.category)
    session.commit()
    return TransactionOut.model_validate(transaction)
