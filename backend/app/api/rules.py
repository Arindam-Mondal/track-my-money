"""Category rules: the builder's config, create / edit / delete, preview, and apply to stored data.

Saving a rule changes no transactions; applying does (one rule or all), and so do uploads and
categorising, which run every rule first. Manual categories are never touched.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import ColumnElement, and_, func, not_, select, true
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.statements import list_categories
from app.api.transactions import search_row
from app.categorising.categories import is_valid
from app.db import get_session
from app.models import Rule, Statement, Transaction
from app.rules import config
from app.rules.conditions import RuleInvalid, compile_group, validate
from app.rules.engine import (
    Applied,
    apply_rule,
    apply_rules,
    before,
    claimable,
    clear,
    fits_direction,
    limit_time,
)
from app.schemas import (
    RuleApplied,
    RuleConfig,
    RuleConnectorOut,
    RuleDraft,
    RuleFieldOut,
    RuleIn,
    RuleInvalidOut,
    RuleLimitsOut,
    RuleOperatorOut,
    RuleOut,
    RulePreview,
    RuleTypeOut,
)

router = APIRouter(prefix="/api/rules")
SessionDep = Annotated[Session, Depends(get_session)]

PREVIEW_ROWS = 100


def invalid(message: str, condition: int | None = None) -> HTTPException:
    return HTTPException(422, detail=RuleInvalidOut(message=message, condition=condition).model_dump())


def check(draft: RuleDraft, session: Session, *, need_category: bool = True) -> None:
    if (need_category or draft.category) and not (is_valid(draft.category, "out") or is_valid(draft.category, "in")):
        raise invalid(f"Unknown category {draft.category!r}")
    try:
        validate(draft.conditions, session)
    except RuleInvalid as error:
        raise invalid(error.message, error.condition) from None


def too_slow(session: Session, error: DBAPIError) -> HTTPException:
    """A rule that hit the statement timeout (or another database error while running)."""
    session.rollback()
    return invalid(f"The rule couldn't run: {str(error.orig).splitlines()[0]}")


def to_out(rule: Rule, applied_count: int) -> RuleOut:
    return RuleOut.model_validate(
        {
            "id": rule.id,
            "name": rule.name,
            "position": rule.position,
            "conditions": rule.conditions,
            "category": rule.category,
            "applied_count": applied_count,
        }
    )


def applied_count(session: Session, rule_id: int) -> int:
    return session.scalar(select(func.count()).where(Transaction.category_rule_id == rule_id)) or 0


def name_taken(session: Session, name: str, rule_id: int | None = None) -> bool:
    query = select(Rule.id).where(func.lower(Rule.name) == name.lower())
    if rule_id is not None:
        query = query.where(Rule.id != rule_id)
    return session.scalar(query) is not None


def get_rule(session: Session, rule_id: int) -> Rule:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    return rule


def save(session: Session, rule: Rule) -> None:
    try:
        session.commit()
    except IntegrityError:  # the same name saved in parallel
        session.rollback()
        raise HTTPException(409, f"A rule called {rule.name!r} already exists") from None


@router.get("/config")
def rule_config() -> RuleConfig:
    return RuleConfig(
        fields=[RuleFieldOut(id=key, label=field.label, type=field.type) for key, field in config.FIELDS.items()],
        types={
            key: RuleTypeOut(
                input=field_type.input,
                operators=[RuleOperatorOut(id=o.id, label=o.label, hint=o.hint) for o in field_type.operators],
            )
            for key, field_type in config.TYPES.items()
        },
        connectors=[RuleConnectorOut(id=c.id, label=c.label) for c in config.CONNECTORS],
        categories=list_categories(),
        limits=RuleLimitsOut(
            max_conditions=config.LIMITS.max_conditions,
            max_value_length=config.LIMITS.max_value_length,
            max_depth=config.LIMITS.max_depth,
        ),
    )


@router.get("")
def list_rules(session: SessionDep) -> list[RuleOut]:
    counts = {
        rule_id: count
        for rule_id, count in session.execute(
            select(Transaction.category_rule_id, func.count())
            .where(Transaction.category_rule_id.is_not(None))
            .group_by(Transaction.category_rule_id)
        )
    }
    rules = session.scalars(select(Rule).order_by(Rule.position, Rule.id))
    return [to_out(rule, counts.get(rule.id, 0)) for rule in rules]


@router.post("", status_code=201)
def create_rule(rule_in: RuleIn, session: SessionDep) -> RuleOut:
    """Save a new rule at the end of the list. No transactions change until it's applied."""
    check(rule_in, session)
    if name_taken(session, rule_in.name):
        raise HTTPException(409, f"A rule called {rule_in.name!r} already exists")
    position = (session.scalar(select(func.max(Rule.position))) or 0) + 1
    rule = Rule(
        name=rule_in.name,
        position=position,
        conditions=rule_in.conditions.model_dump(),
        category=rule_in.category,
    )
    session.add(rule)
    save(session, rule)
    return to_out(rule, 0)


@router.put("/{rule_id}")
def update_rule(rule_id: int, rule_in: RuleIn, session: SessionDep) -> RuleOut:
    """Change a rule. Transactions it categorised keep their category until it's applied again."""
    rule = get_rule(session, rule_id)
    check(rule_in, session)
    if name_taken(session, rule_in.name, rule_id):
        raise HTTPException(409, f"A rule called {rule_in.name!r} already exists")
    rule.name = rule_in.name
    rule.conditions = rule_in.conditions.model_dump()
    rule.category = rule_in.category
    save(session, rule)
    return to_out(rule, applied_count(session, rule_id))


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: SessionDep) -> Response:
    """Delete a rule; the transactions it categorised go back to uncategorised."""
    rule = get_rule(session, rule_id)
    clear(session, Transaction.category_rule_id == rule_id)
    session.delete(rule)
    session.commit()
    return Response(status_code=204)


@router.post("/preview")
def preview_rule(draft: RuleDraft, session: SessionDep, rule_id: int | None = None) -> RulePreview:
    """What a rule would do, without changing anything. `rule_id`: the rule being edited, if any
    (rules before it keep their rows); a new rule goes last. Without a category yet, every
    direction fits."""
    check(draft, session, need_category=False)
    if rule_id is not None:
        rule = get_rule(session, rule_id)
        earlier = before(rule.position, rule.id)
    else:
        earlier = select(Rule.id)
    condition = compile_group(draft.conditions)
    fits = fits_direction(draft.category) if draft.category else true()
    source = Transaction.category_source
    held_earlier = and_(source == "rule", Transaction.category_rule_id.in_(earlier))

    def count(*where: ColumnElement[bool]) -> int:
        return session.scalar(select(func.count()).select_from(Transaction).where(condition, *where)) or 0

    try:
        limit_time(session)
        result = RulePreview(
            total=count(),
            will_set=count(fits, claimable(earlier)),
            manual=count(source == "manual"),
            wrong_direction=count(not_(fits), source.is_distinct_from("manual")),
            other_rule=count(fits, held_earlier),
            transactions=[
                search_row(t, bank, account)
                for t, bank, account in session.execute(
                    select(Transaction, Statement.bank, Statement.account_number)
                    .join(Statement)
                    .where(condition)
                    .order_by(Transaction.date.desc(), Transaction.statement_id, Transaction.row_index.desc())
                    .limit(PREVIEW_ROWS)
                )
            ],
        )
    except DBAPIError as error:
        raise too_slow(session, error) from None
    session.rollback()  # end the read-only transaction (and its timeout)
    return result


def applied(session: Session, run: Callable[[], Applied]) -> RuleApplied:
    try:
        result = run()
        session.commit()
    except DBAPIError as error:
        raise too_slow(session, error) from None
    return RuleApplied(set=result.set, cleared=result.cleared)


@router.post("/apply")
def apply_all_rules(session: SessionDep) -> RuleApplied:
    """Run every rule, in order, on all transactions."""
    return applied(session, lambda: apply_rules(session))


@router.post("/{rule_id}/apply")
def apply_one_rule(rule_id: int, session: SessionDep) -> RuleApplied:
    """Run one rule on all transactions."""
    rule = get_rule(session, rule_id)
    return applied(session, lambda: apply_rule(session, rule))
