"""Tables: one row per imported statement, one row per transaction in it."""

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(14, 2)


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text, unique=True)  # same file uploaded twice -> rejected
    bank: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(Text)
    header_mapping: Mapped[str | None] = mapped_column(Text)  # rules / jev / jev (image) / rules (fallback)
    balance_check: Mapped[str] = mapped_column(Text)
    # "metadata" is reserved on declarative classes, so the attribute has a trailing underscore.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="statement", order_by="Transaction.row_index", passive_deletes=True
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("debit >= 0", name="debit_nonnegative"),
        CheckConstraint("credit >= 0", name="credit_nonnegative"),
        CheckConstraint("category_source in ('laya', 'manual')", name="category_source_known"),
        Index("transactions_category_date_idx", "category", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("statements.id", ondelete="CASCADE"), index=True
    )
    row_index: Mapped[int]  # position in the statement, to keep the bank's order
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    particulars: Mapped[str] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(Money)
    credit: Mapped[Decimal] = mapped_column(Money)
    balance: Mapped[Decimal | None] = mapped_column(Money)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    # Set by Laya, or by the user ("manual"; never overwritten). Null until categorised.
    category: Mapped[str | None] = mapped_column(Text)
    category_source: Mapped[str | None] = mapped_column(Text)
    category_confidence: Mapped[float | None] = mapped_column(REAL)  # Laya's; over-confident, shown only
    categorised_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    statement: Mapped[Statement] = relationship(back_populates="transactions")
