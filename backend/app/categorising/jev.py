"""Ask Jev (TypeSafe's hosted model) for each transaction's category, using masked text only.

Jev runs in the cloud, so it never receives the original narration: only the stored masked text
(app/masking), the direction, and the amount as a range. A transaction without masked text is
refused rather than sent unmasked.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from typesafe_sdk import Content, TypeSafeError

from app.categorising.categories import is_valid
from app.categorising.laya import DIRECTION_TEXT, CategoryAnswer, CategoryClassifier, TxInput, build_question
from app.jev import jev_client

# Upper bounds (exclusive) and labels; the exact amount stays on this machine.
_RANGES: list[tuple[Decimal, str]] = [
    (Decimal(500), "under ₹500"),
    (Decimal(2_000), "₹500–2k"),
    (Decimal(10_000), "₹2k–10k"),
    (Decimal(50_000), "₹10k–50k"),
    (Decimal(200_000), "₹50k–2L"),
]


def amount_range(amount: Decimal) -> str:
    return next((label for bound, label in _RANGES if amount < bound), "over ₹2L")


def build_jev_state(tx: TxInput) -> Content:
    if not tx.masked_narration:
        raise TypeSafeError("Not sent to Jev: this transaction has no masked narration yet (run the masking backfill)")
    return {
        "narration": tx.masked_narration,
        "direction": DIRECTION_TEXT[tx.direction],
        "amount": amount_range(tx.amount),
    }


@contextmanager
def jev_category_classifier(api_key: str) -> Iterator[CategoryClassifier]:
    """A classifier asking Jev with this key; its HTTP client is closed afterwards."""
    client = jev_client(api_key)

    def classify(tx: TxInput) -> CategoryAnswer:
        result = client.system_one(build_jev_state(tx), {"category": build_question(tx.direction, with_descriptions=True)})
        answer = result.choices["category"]
        if not is_valid(answer.choice, tx.direction):
            raise TypeSafeError(f"Jev answered an unknown category: {answer.choice!r}")
        return CategoryAnswer(answer.choice, answer.confidence)

    with client:
        yield classify
