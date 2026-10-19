"""A rule's conditions: a tree of groups ("and"/"or") and conditions (field, operator, value),
checked against app/rules/config.py and turned into one SQL condition.

`A and B or C` from the UI is stored as or(and(A, B), and(C)): AND binds tighter, as in SQL.
"""

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ColumnElement, and_, literal, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.rules.config import CONNECTORS, FIELDS, LIMITS, REGEX_OPERATORS, TYPES
from app.rules.operators import BUILDERS


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: str
    value: str  # parsed by the field's type


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: str  # a connector id: "and" or "or"
    items: list["Condition | Group"]


Group.model_rebuild()


class RuleInvalid(ValueError):
    """A rule that can't be saved; `condition` is its 1-based number in reading order, if one is at fault."""

    def __init__(self, message: str, condition: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.condition = condition


def conditions_of(group: Group) -> Iterator[Condition]:
    """The conditions in reading order (depth first), as the UI numbers them."""
    for item in group.items:
        if isinstance(item, Group):
            yield from conditions_of(item)
        else:
            yield item


def depth_of(group: Group) -> int:
    return 1 + max((depth_of(item) for item in group.items if isinstance(item, Group)), default=0)


def check_groups(group: Group) -> None:
    connectors = {c.id for c in CONNECTORS}
    if group.match not in connectors:
        raise RuleInvalid(f"Unknown connector {group.match!r}")
    if not group.items:
        raise RuleInvalid("Add at least one condition")
    for item in group.items:
        if isinstance(item, Group):
            check_groups(item)


def regex_error(session: Session, pattern: str) -> str | None:
    """Postgres's message if it can't compile the pattern; checked in a savepoint, so nothing else is undone."""
    try:
        with session.begin_nested():
            session.execute(select(literal("").regexp_match(pattern, flags="i")))
    except DBAPIError as error:
        diag = getattr(error.orig, "diag", None)
        message = getattr(diag, "message_primary", None) or str(error.orig).splitlines()[0]
        return f"Not a valid regular expression: {message}"
    return None


def validate(group: Group, session: Session) -> None:
    """Raise RuleInvalid unless every part of the tree is in the config and every value parses."""
    check_groups(group)
    if depth_of(group) > LIMITS.max_depth:
        raise RuleInvalid(f"Groups can be at most {LIMITS.max_depth} levels deep")
    conditions = list(conditions_of(group))
    if len(conditions) > LIMITS.max_conditions:
        raise RuleInvalid(f"A rule can have at most {LIMITS.max_conditions} conditions")
    for number, condition in enumerate(conditions, start=1):
        field = FIELDS.get(condition.field)
        if field is None:
            raise RuleInvalid(f"Unknown column {condition.field!r}", number)
        field_type = TYPES[field.type]
        if condition.operator not in {o.id for o in field_type.operators}:
            raise RuleInvalid(f"{field.label} can't use the operator {condition.operator!r}", number)
        if len(condition.value) > LIMITS.max_value_length:
            raise RuleInvalid(f"Values can be at most {LIMITS.max_value_length} characters", number)
        try:
            value = field_type.parse(condition.value)
        except ValueError as error:
            raise RuleInvalid(str(error), number) from None
        if condition.operator in REGEX_OPERATORS and (message := regex_error(session, value)):
            raise RuleInvalid(message, number)


def compile_condition(condition: Condition) -> ColumnElement[bool]:
    field = FIELDS[condition.field]
    value: Any = TYPES[field.type].parse(condition.value)
    return BUILDERS[field.type][condition.operator](field.expression, value)


def compile_group(group: Group) -> ColumnElement[bool]:
    """One SQL condition for a validated tree."""
    parts = [compile_group(item) if isinstance(item, Group) else compile_condition(item) for item in group.items]
    return and_(*parts) if group.match == "and" else or_(*parts)
