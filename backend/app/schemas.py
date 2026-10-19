"""API response shapes."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.rules.conditions import Group

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
    particulars_masked: str | None  # what Jev would see
    debit: Decimal
    credit: Decimal
    balance: Decimal | None
    extra: dict[str, Any]
    category: str | None
    category_source: Literal["laya", "jev", "rule", "manual"] | None
    category_rule_id: int | None  # the rule that set it, when the source is "rule"
    category_confidence: float | None


class CategoryUpdate(BaseModel):
    category: str


class BulkCategoryUpdate(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    category: str


class TransactionSearchRow(TransactionOut):
    statement_id: int
    bank: str | None
    account_last4: str | None


class TransactionSearch(BaseModel):
    total: int  # all matches; `transactions` holds at most `limit` of them
    transactions: list[TransactionSearchRow]


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


# ---------------------------------------------------------------- rules (app/rules)

RuleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class RuleDraft(BaseModel):
    """A rule being edited: enough to preview it."""

    conditions: Group
    category: str


class RuleIn(RuleDraft):
    name: RuleName


class RuleOut(RuleIn):
    id: int
    position: int  # rules are checked in this order; the first match wins
    applied_count: int  # transactions this rule categorised


class RuleApplied(BaseModel):
    set: int  # transactions the rule(s) now categorise
    cleared: int  # transactions a rule had categorised that went back to uncategorised


class RuleInvalidOut(BaseModel):
    message: str
    condition: int | None  # 1-based, in reading order


class RulePreview(BaseModel):
    total: int  # transactions the conditions match
    will_set: int  # of those, the ones the rule would categorise
    manual: int  # set by hand: kept
    wrong_direction: int  # money in for a money out category, or the other way round: left alone
    other_rule: int  # held by a rule checked before this one
    transactions: list[TransactionSearchRow]  # the newest matches, at most PREVIEW_ROWS


class RuleOperatorOut(BaseModel):
    id: str
    label: str
    hint: str | None


class RuleTypeOut(BaseModel):
    input: str  # the kind of value box: "text" or "number"
    operators: list[RuleOperatorOut]


class RuleFieldOut(BaseModel):
    id: str
    label: str
    type: str  # a key of RuleConfig.types


class RuleConnectorOut(BaseModel):
    id: str
    label: str


class RuleLimitsOut(BaseModel):
    max_conditions: int
    max_value_length: int
    max_depth: int


class RuleConfig(BaseModel):
    """Everything the rule builder offers; the UI hard-codes none of it."""

    fields: list[RuleFieldOut]
    types: dict[str, RuleTypeOut]
    connectors: list[RuleConnectorOut]
    categories: Categories
    limits: RuleLimitsOut
