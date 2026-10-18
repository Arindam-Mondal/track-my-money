"""Background categorising jobs: one statement at a time, saved as answers arrive.

Jobs only start when the user asks (POST /statements/{id}/categorise), with Laya (local) or Jev
(cloud, masked text only)."""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from typesafe_sdk import TypeSafeError

from app.categorising.categories import direction_of
from app.categorising.jev import jev_category_classifier
from app.categorising.laya import CategoryClassifier, TxInput, laya_classifier
from app.config import settings
from app.db import SessionLocal
from app.models import Transaction

logger = logging.getLogger(__name__)

COMMIT_EVERY = 25

Categoriser = Literal["laya", "jev"]


def make_classifier(categoriser: Categoriser, api_key: str | None) -> AbstractContextManager[CategoryClassifier]:
    if categoriser == "jev":
        if not api_key:
            raise ValueError("Jev needs an API key")
        return jev_category_classifier(api_key)
    return laya_classifier()


# Replaced in tests, so jobs use the test database and a fake classifier.
session_factory: Callable[[], Session] = SessionLocal
classifier_factory: Callable[[Categoriser, str | None], AbstractContextManager[CategoryClassifier]] = make_classifier

_running: set[int] = set()
_lock = threading.Lock()


def is_running(statement_id: int) -> bool:
    with _lock:
        return statement_id in _running


def claim(statement_id: int) -> bool:
    """Mark a statement as being categorised; False if a job for it is already running."""
    with _lock:
        if statement_id in _running:
            return False
        _running.add(statement_id)
        return True


def run(statement_id: int, redo: bool = False, categoriser: Categoriser = "laya", api_key: str | None = None) -> None:
    """Categorise a claimed statement, then release it. Errors are logged, not raised.

    The Jev key lives only in this call: it is never stored or logged."""
    try:
        with classifier_factory(categoriser, api_key) as classify:
            done = categorise_statement(statement_id, classify, redo=redo, source=categoriser)
        logger.info("Categorised %d transaction(s) of statement %d with %s", done, statement_id, categoriser)
    except Exception:
        logger.exception("Categorising statement %d failed", statement_id)
    finally:
        with _lock:
            _running.discard(statement_id)


def categorise_statement(
    statement_id: int, classify: CategoryClassifier, *, redo: bool = False, source: Categoriser = "laya"
) -> int:
    """Categorise a statement's transactions; manual categories are never touched.

    Without `redo`, only uncategorised transactions are asked about; with it, earlier Laya and Jev
    answers are redone too. Returns how many were saved. If the model fails, what was saved so far stays.
    """
    with session_factory() as session:
        query = select(Transaction).where(Transaction.statement_id == statement_id)
        if redo:
            query = query.where(or_(Transaction.category_source.is_(None), Transaction.category_source.in_(("laya", "jev"))))
        else:
            query = query.where(Transaction.category.is_(None))
        work = [
            (t.id, TxInput(t.particulars, direction_of(t.debit), t.debit or t.credit, t.extra, t.particulars_masked))
            for t in session.scalars(query.order_by(Transaction.row_index))
        ]

    saved = 0
    with session_factory() as session, ThreadPoolExecutor(settings.categorise_workers) as pool:
        futures = {pool.submit(classify, tx): tx_id for tx_id, tx in work}
        try:
            for future in as_completed(futures):
                answer = future.result()
                session.execute(
                    update(Transaction)
                    .where(Transaction.id == futures[future], Transaction.category_source.is_distinct_from("manual"))
                    .values(
                        category=answer.category,
                        category_source=source,
                        category_confidence=answer.confidence,
                        categorised_at=datetime.now(UTC),
                    )
                )
                saved += 1
                if saved % COMMIT_EVERY == 0:
                    session.commit()
        except TypeSafeError as error:
            for future in futures:
                future.cancel()
            logger.warning("%s unavailable after %d of %d transaction(s): %s", source, saved, len(work), error)
        session.commit()
    return saved
