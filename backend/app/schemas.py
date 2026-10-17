"""API response shapes."""

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_index: int
    date: dt.date
    particulars: str
    debit: Decimal
    credit: Decimal
    balance: Decimal | None
    extra: dict[str, Any]
