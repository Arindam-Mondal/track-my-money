"""SQL for each operator in app/rules/config.py: (column, parsed value) -> condition.

Text operators ignore case, and take the user's text literally (`%`, `_` and `\\` are escaped);
only the regex operators read a pattern, with Postgres's case-insensitive `~*`.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, not_

from app.rules.config import TYPES

Builder = Callable[[SQLColumnExpression[Any], Any], ColumnElement[bool]]


def literal_like(text: str) -> str:
    """Escape LIKE's wildcards, so the text matches only itself (with ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like(pattern: str) -> Builder:
    """`pattern` with {} where the escaped value goes, e.g. "%{}%" for contains."""
    return lambda column, value: column.ilike(pattern.format(literal_like(value)), escape="\\")


def regex(column: SQLColumnExpression[Any], value: str) -> ColumnElement[bool]:
    return column.regexp_match(value, flags="i")


BUILDERS: dict[str, dict[str, Builder]] = {
    "string": {
        "contains": like("%{}%"),
        "not_contains": lambda column, value: not_(like("%{}%")(column, value)),
        "equals": like("{}"),
        "not_equals": lambda column, value: not_(like("{}")(column, value)),
        "starts_with": like("{}%"),
        "ends_with": like("%{}"),
        "regex": regex,
        "not_regex": lambda column, value: not_(regex(column, value)),
    },
    "number": {
        "eq": lambda column, value: column == value,
        "ne": lambda column, value: column != value,
        "gt": lambda column, value: column > value,
        "lt": lambda column, value: column < value,
        "ge": lambda column, value: column >= value,
        "le": lambda column, value: column <= value,
    },
}


def check_builders() -> None:
    """Every operator in the config needs SQL here; fail at import rather than on the first rule."""
    missing = [
        f"{type_id}.{operator.id}"
        for type_id, field_type in TYPES.items()
        for operator in field_type.operators
        if operator.id not in BUILDERS.get(type_id, {})
    ]
    if missing:
        raise RuntimeError(f"Rule operators without SQL in app/rules/operators.py: {', '.join(missing)}")


check_builders()
