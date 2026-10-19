"""Apply rules to stored transactions, in SQL.

Precedence: manual > rule > Laya/Jev. Rules never touch manual rows and overwrite model answers;
among rules, the first in list order wins. A rule only categorises rows whose direction fits its
category (a money out category only debits); other rows are left for the next rule or the model.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, and_, false, func, or_, select, text, true, tuple_, update
from sqlalchemy.orm import Session

from app.categorising.categories import is_valid
from app.models import Rule, Transaction
from app.rules.conditions import Group, compile_group

MODEL_SOURCES = ("laya", "jev")
TIMEOUT = "5s"  # a slow regex can't hold the database for long


@dataclass(frozen=True)
class Applied:
    set: int  # rows the rule(s) now hold
    cleared: int  # rows a rule held before and that went back to uncategorised


def limit_time(session: Session) -> None:
    """Statement timeout for the rest of this transaction."""
    session.execute(text(f"SET LOCAL statement_timeout = '{TIMEOUT}'"))


def fits_direction(category: str) -> ColumnElement[bool]:
    out_ok, in_ok = is_valid(category, "out"), is_valid(category, "in")
    if out_ok and in_ok:
        return true()
    if out_ok:
        return Transaction.debit > 0
    if in_ok:
        return Transaction.debit == 0
    return false()


def matches(rule_conditions: dict) -> ColumnElement[bool]:
    return compile_group(Group.model_validate(rule_conditions))


def scope(statement_id: int | None) -> list[ColumnElement[bool]]:
    return [] if statement_id is None else [Transaction.statement_id == statement_id]


def ordered(session: Session) -> Sequence[Rule]:
    return session.scalars(select(Rule).order_by(Rule.position, Rule.id)).all()


def before(rule_position: int, rule_id: int) -> Select[int]:
    """Ids of the rules checked before this one."""
    return select(Rule.id).where(tuple_(Rule.position, Rule.id) < tuple_(rule_position, rule_id))


def held_by_rules(session: Session, where: list[ColumnElement[bool]]) -> dict[int, int | None]:
    """Transaction id -> rule id, for rows a rule set."""
    rows = session.execute(
        select(Transaction.id, Transaction.category_rule_id).where(Transaction.category_source == "rule", *where)
    )
    return {tx_id: rule_id for tx_id, rule_id in rows}


def clear(session: Session, *where: ColumnElement[bool]) -> None:
    session.execute(
        update(Transaction)
        .where(*where)
        .values(category=None, category_source=None, category_rule_id=None, category_confidence=None, categorised_at=None),
        execution_options={"synchronize_session": False},
    )


def claimable(earlier: Select[int]) -> ColumnElement[bool]:
    """Rows a rule may set: uncategorised, a model's answer, or held by a rule not in `earlier`
    (the rules checked before it). Never manual rows."""
    source, held_by = Transaction.category_source, Transaction.category_rule_id
    return or_(
        source.is_(None),
        source.in_(MODEL_SOURCES),
        and_(source == "rule", or_(held_by.is_(None), held_by.not_in(earlier))),
    )


def set_by(session: Session, rule: Rule, where: list[ColumnElement[bool]]) -> None:
    session.execute(
        update(Transaction)
        .where(
            matches(rule.conditions), fits_direction(rule.category), claimable(before(rule.position, rule.id)), *where
        )
        .values(
            category=rule.category,
            category_source="rule",
            category_rule_id=rule.id,
            category_confidence=None,
            categorised_at=func.now(),
        ),
        execution_options={"synchronize_session": False},
    )


def apply_rule(session: Session, rule: Rule, statement_id: int | None = None) -> Applied:
    """Run one rule again: its rows that no longer match are cleared, and it takes the rows it matches,
    except manual ones and those held by a rule checked before it. The caller commits."""
    where = scope(statement_id)
    limit_time(session)
    held_before = held_by_rules(session, where)
    clear(session, Transaction.category_rule_id == rule.id, *where)
    set_by(session, rule, where)
    held_after = held_by_rules(session, where)
    return Applied(
        set=sum(1 for rule_id in held_after.values() if rule_id == rule.id),
        cleared=sum(1 for tx_id in held_before if tx_id not in held_after),
    )


def apply_rules(session: Session, statement_id: int | None = None) -> Applied:
    """Run every rule in order on all transactions, or on one statement's. The caller commits."""
    where = scope(statement_id)
    limit_time(session)
    held_before = held_by_rules(session, where)
    clear(session, Transaction.category_source == "rule", *where)
    for rule in ordered(session):
        set_by(session, rule, where)
    held_after = held_by_rules(session, where)
    return Applied(set=len(held_after), cleared=sum(1 for tx_id in held_before if tx_id not in held_after))
