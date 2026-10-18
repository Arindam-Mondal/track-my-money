"""Ask Laya, the open-source Jev-compatible model running locally, for each transaction's category.

Laya serves the same API as Jev (POST /v1/systemone), so this uses the TypeSafe SDK with
`base_url` pointed at the local container. Narrations are sent unmasked: they never leave
this machine.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal

from typesafe_sdk import Choice, Content, RetryPolicy, TypeSafeClient, TypeSafeError

from app.categorising.categories import CATEGORIES, Direction, is_valid
from app.config import settings


@dataclass(frozen=True)
class TxInput:
    narration: str
    direction: Direction
    amount: Decimal
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CategoryAnswer:
    category: str
    confidence: float  # Laya's; over-confident as shipped, so shown but not used as a threshold


# A category classifier: one transaction in, its category out. Tests pass in a fake.
CategoryClassifier = Callable[[TxInput], CategoryAnswer]

DIRECTION_TEXT: dict[Direction, str] = {"out": "money out of the account", "in": "money into the account"}


def build_state(tx: TxInput) -> Content:
    return {
        "narration": tx.narration,
        "direction": DIRECTION_TEXT[tx.direction],
        "amount": f"{tx.amount:.2f}",
        "other_columns": dict(tx.extra),
    }


def build_question(direction: Direction) -> Choice:
    """Category names only: Laya fits the question and all options into 192 tokens, so with
    23 options each one is cut to ~7 tokens and descriptions would only add noise. Training
    data is built with this same function, so the model is asked exactly what it learned."""
    kind = "spending" if direction == "out" else "income"
    return Choice(
        instructions=f"Which {kind} category does this bank transaction belong to?",
        criteria={name: None for name in CATEGORIES[direction]},
    )


@contextmanager
def laya_classifier(model: str | None = None) -> Iterator[CategoryClassifier]:
    """A classifier asking the local Laya server; its HTTP client is closed afterwards.

    `model` picks a checkpoint the server has loaded (e.g. "laya-finance"); default: LAYA_MODEL.
    """
    client = TypeSafeClient(
        api_key=settings.laya_api_key,
        base_url=settings.laya_base_url,
        model=model or settings.laya_model or None,
        retry=RetryPolicy(max_retries=1),
        timeout=60.0,
        compression=False,  # the SDK zstd-compresses bodies over 1 KB; Laya reads only plain JSON
    )

    def classify(tx: TxInput) -> CategoryAnswer:
        result = client.system_one(build_state(tx), {"category": build_question(tx.direction)})
        answer = result.choices["category"]
        if not is_valid(answer.choice, tx.direction):
            raise TypeSafeError(f"Laya answered an unknown category: {answer.choice!r}")
        return CategoryAnswer(answer.choice, answer.confidence)

    with client:
        yield classify
