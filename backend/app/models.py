"""Tables: one row per imported statement, one row per transaction in it, one row per category rule."""

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
    SmallInteger,
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
        CheckConstraint("category_source in ('laya', 'jev', 'rule', 'manual')", name="category_source_known"),
        Index("transactions_category_date_idx", "category", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("statements.id", ondelete="CASCADE"), index=True
    )
    row_index: Mapped[int]  # position in the statement, to keep the bank's order
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    particulars: Mapped[str] = mapped_column(Text)
    # The narration with everything identifying replaced (app/masking); the only text sent to Jev.
    particulars_masked: Mapped[str | None] = mapped_column(Text)
    masking_version: Mapped[int | None] = mapped_column(SmallInteger)
    debit: Mapped[Decimal] = mapped_column(Money)
    credit: Mapped[Decimal] = mapped_column(Money)
    balance: Mapped[Decimal | None] = mapped_column(Money)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    # Set by Laya or Jev, by a rule, or by the user ("manual"; never overwritten). Null until categorised.
    # Precedence: manual > rule > Laya/Jev.
    category: Mapped[str | None] = mapped_column(Text)
    category_source: Mapped[str | None] = mapped_column(Text)
    # The rule that set the category, when the source is "rule".
    category_rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="SET NULL"), index=True
    )
    category_confidence: Mapped[float | None] = mapped_column(REAL)  # Laya's; over-confident, shown only
    categorised_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    statement: Mapped[Statement] = relationship(back_populates="transactions")


class Rule(Base):
    """A user-defined rule: transactions matching `conditions` get `category` (app/rules)."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    position: Mapped[int]  # rules are checked in this order; the first match wins
    # A condition tree: {"match": "and" | "or", "items": [{"field", "operator", "value"} | group, ...]}
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    category: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
