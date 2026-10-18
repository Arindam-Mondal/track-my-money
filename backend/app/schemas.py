"""API response shapes."""

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

UploadErrorCode = Literal[
    "password_required", "wrong_password", "not_a_pdf", "no_text_layer", "no_transactions", "duplicate", "too_large"
]


class UploadError(BaseModel):
    code: UploadErrorCode
    message: str


class Health(BaseModel):
    database: Literal["ok"]
    server_jev_key: bool  # whether uploads without a UI key can still use Jev


class StatementOut(BaseModel):
    id: int
    filename: str
    bank: str | None
    account_number: str | None
    period: str | None
    header_mapping: str | None
    balance_check: str
    uploaded_at: dt.datetime
    transaction_count: int
    categorised_count: int
    categorising: bool  # a categorising job is running now


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_index: int
    date: dt.date
    particulars: str
    debit: Decimal
    credit: Decimal
    balance: Decimal | None
    extra: dict[str, Any]
    category: str | None
    category_source: Literal["laya", "manual"] | None
    category_confidence: float | None


class CategoryUpdate(BaseModel):
    category: str


class Category(BaseModel):
    name: str
    description: str


class Categories(BaseModel):
    out: list[Category]  # money out (debits)
    in_: list[Category] = Field(serialization_alias="in")  # money in (credits)


class MonthlyFlow(BaseModel):
    month: str  # "2026-04"
    money_in: Decimal
    money_out: Decimal
    net: Decimal


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int


class TrendPoint(BaseModel):
    month: str
    total: Decimal
