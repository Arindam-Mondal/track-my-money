"""Mask stored narrations that have no masked text yet, or were masked by an older version of the rules.

Run from backend/ after the migration, and again whenever MASKING_VERSION changes:
    uv run python -m app.masking.backfill
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.masking import MASKING_VERSION, mask
from app.models import Transaction

BATCH = 500


def backfill(session: Session) -> int:
    """Re-mask outdated rows; returns how many were updated. Manual and model categories are untouched."""
    updated = 0
    while True:
        rows = session.scalars(
            select(Transaction)
            .where(or_(Transaction.masking_version.is_(None), Transaction.masking_version < MASKING_VERSION))
            .limit(BATCH)
        ).all()
        if not rows:
            return updated
        for row in rows:
            row.particulars_masked = mask(row.particulars)
            row.masking_version = MASKING_VERSION
        session.commit()
        updated += len(rows)


if __name__ == "__main__":
    with SessionLocal() as session:
        print(f"Masked {backfill(session)} transaction(s) with masking version {MASKING_VERSION}.")
