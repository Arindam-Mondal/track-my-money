"""What rule conditions can use. Edit this file to add columns, operators or types.

The UI builds its rule builder only from this (GET /api/rules/config), and rules are validated
against it, so the two can't disagree. A new column needs an entry in FIELDS; a new operator also
needs an SQL builder in app/rules/operators.py; a new type needs both, plus a value parser below.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import SQLColumnExpression, func, select

from app.models import Statement, Transaction


@dataclass(frozen=True)
class Operator:
    id: str
    label: str
    hint: str | None = None  # shown under the value box


@dataclass(frozen=True)
class FieldType:
    input: Literal["text", "number"]  # the kind of value box the UI shows
    operators: tuple[Operator, ...]
    parse: Callable[[str], Any]  # the stored value (always a string) -> what the SQL builder gets; ValueError if bad


@dataclass(frozen=True)
class Field:
    label: str
    type: str  # a key of TYPES
    expression: SQLColumnExpression[Any]


@dataclass(frozen=True)
class Connector:
    id: str
    label: str


@dataclass(frozen=True)
class Limits:
    max_conditions: int
    max_value_length: int
    max_depth: int  # groups inside groups; the UI writes 2 levels (OR of AND-blocks)


def parse_text(value: str) -> str:
    """Runs of spaces count as one space, as in the text the conditions are matched against."""
    text = " ".join(value.split())
    if not text:
        raise ValueError("Enter some text")
    return text


def parse_number(value: str) -> Decimal:
    try:
        number = Decimal(value.strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"{value!r} isn't a number") from None
    if not number.is_finite():
        raise ValueError(f"{value!r} isn't a number")
    return number


def collapsed(column: SQLColumnExpression[str | None]) -> SQLColumnExpression[str]:
    """The text with runs of whitespace as one space, and never null."""
    return func.regexp_replace(func.coalesce(column, ""), r"\s+", " ", "g")


REGEX_HINT = r"A regular expression, case-insensitive. E.g. UPI/P2A/\d+/MAMATA MONDAL matches any reference number."

TYPES: dict[str, FieldType] = {
    "string": FieldType(
        input="text",
        operators=(
            Operator("contains", "contains"),
            Operator("not_contains", "does not contain"),
            Operator("equals", "equals"),
            Operator("not_equals", "does not equal"),
            Operator("starts_with", "starts with"),
            Operator("ends_with", "ends with"),
            Operator("regex", "matches regex", REGEX_HINT),
            Operator("not_regex", "does not match regex", REGEX_HINT),
        ),
        parse=parse_text,
    ),
    "number": FieldType(
        input="number",
        operators=(
            Operator("eq", "="),
            Operator("ne", "≠"),
            Operator("gt", ">"),
            Operator("lt", "<"),
            Operator("ge", "≥"),
            Operator("le", "≤"),
        ),
        parse=parse_number,
    ),
}

FIELDS: dict[str, Field] = {
    # The original narration: rules run in this app's database and never leave the machine.
    "particulars": Field("Particulars", "string", collapsed(Transaction.particulars)),
    "debit": Field("Debit", "number", Transaction.debit),
    "credit": Field("Credit", "number", Transaction.credit),
    "bank": Field(
        "Bank",
        "string",
        collapsed(
            select(Statement.bank)
            .where(Statement.id == Transaction.statement_id)
            .correlate_except(Statement)
            .scalar_subquery()
        ),
    ),
}

CONNECTORS: tuple[Connector, ...] = (Connector("and", "AND"), Connector("or", "OR"))

LIMITS = Limits(max_conditions=20, max_value_length=300, max_depth=3)

REGEX_OPERATORS = frozenset({"regex", "not_regex"})  # values checked by Postgres when a rule is saved
