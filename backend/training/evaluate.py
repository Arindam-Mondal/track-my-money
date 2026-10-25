"""Compare categorisers on the same transactions, locally: nothing here leaves the machine.

Candidates:
  laya-english   the base Laya checkpoint (no fine-tuning)
  laya-finance   our fine-tuned checkpoint (models/laya-finance)
  tfidf          a tiny baseline: character n-gram TF-IDF + logistic regression, trained in
                 seconds on the same synthetic data. Shows whether fine-tuning a 0.4B model pays off.
  jev-masked     Jev (cloud) on the MASKED narrations only. Opt-in (add it to --models): it sends
                 the masked text of your labelled transactions to TypeSafe. Needs JEV_API_KEY.

Test sets:
  handwritten    18 typical narrations with known categories
  real           your own transactions that you categorised by hand in the app (category_source='manual')

Usage (from backend/, with Laya running both checkpoints):
    LAYA_MODELS=english,laya-finance docker compose up -d laya
    uv run python training/evaluate.py --round 1
"""

import argparse
import json
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

from app.categorising.categories import direction_of  # noqa: E402
from app.categorising.jev import jev_category_classifier  # noqa: E402
from app.categorising.laya import TxInput, laya_classifier  # noqa: E402
from app.masking import mask  # noqa: E402
from app.config import settings  # noqa: E402
from app.jev import jev_key  # noqa: E402
from app.models import Transaction  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"

HANDWRITTEN = [
    ("UPI/412345678/SWIGGY/swiggy@icici", "out", "450", "Food & Dining"),
    ("UPI/523456789/ZOMATO LTD/zomato@hdfcbank", "out", "620", "Food & Dining"),
    ("ATM WDL/NFS/CASH WITHDRAWAL/S1ANMU12", "out", "5000", "ATM Withdrawal"),
    ("NACH-MUT-DR/BSE STAR MF/SIP 4567", "out", "10000", "Mutual Fund / SIP"),
    ("UPI/98765/RENT OCT/landlord@okhdfc", "out", "25000", "House Rent"),
    ("UPI/33445566/BIGBASKET/bigbasket@axis", "out", "1890", "Groceries"),
    ("UPI/22113344/AMAZON PAY/amazon@apl", "out", "2499", "Shopping"),
    ("BIL/ONL/000123/JIO PREPAID RECHARGE", "out", "299", "Mobile & Internet"),
    ("UPI/77889900/IRCTC/irctc@sbi", "out", "1460", "Travel"),
    ("UPI/66554433/APOLLO PHARMACY/apollo@ybl", "out", "740", "Health & Medical"),
    ("CC PAYMENT/HDFC CREDIT CARD/XX1234", "out", "18500", "Credit Card Payment"),
    ("EMI/HOME LOAN/HDFC LTD/0045", "out", "32000", "EMI & Loan Repayment"),
    ("Consolidated Charges for A/c", "out", "118", "Bank Charges & Fees"),
    ("UPI/11223344/RAHUL SHARMA/rahul@okaxis/Payment", "out", "2000", "Transfer to Others"),
    ("NEFT/ACME TECHNOLOGIES PVT LTD/SALARY OCT", "in", "120000", "Salary"),
    ("Int.Pd:01-04-2026 to 30-06-2026", "in", "812", "Interest"),
    ("UPI/99887766/PRIYA/priya@okicici/dinner split", "in", "650", "Transfer from Others"),
    ("REFUND/AMAZON/ORDER 403-123", "in", "999", "Refund & Cashback"),
]

Case = tuple[TxInput, str]


def handwritten() -> list[Case]:
    return [(TxInput(n, d, Decimal(a), masked_narration=mask(n)), expected)  # type: ignore[arg-type]
            for n, d, a, expected in HANDWRITTEN]


def real_labelled() -> list[Case]:
    """Transactions you categorised by hand in the app; read locally from Postgres."""
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            select(Transaction.particulars, Transaction.debit, Transaction.credit, Transaction.extra,
                   Transaction.particulars_masked, Transaction.category)
            .where(Transaction.category_source == "manual")
        ).all()
    return [(TxInput(p, direction_of(debit), debit or credit, extra, masked), category)
            for p, debit, credit, extra, masked, category in rows]


def tfidf_classifier(round_: int):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    rows = [json.loads(line) for line in (DATA_DIR / f"round-{round_}" / "train.jsonl").read_text(encoding="utf-8").splitlines()]

    def text(narration: str, direction: str) -> str:
        return f"{'OUT' if direction.startswith('money out') or direction == 'out' else 'IN'} {narration}"

    model = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), lowercase=True, min_df=2),
                          LogisticRegression(max_iter=2000, C=5))
    model.fit([text(r["state"]["narration"], r["state"]["direction"]) for r in rows], [r["expected"]["category"] for r in rows])
    return lambda tx: model.predict([text(tx.narration, tx.direction)])[0]


def run(name: str, predict, cases: list[Case]) -> None:
    if not cases:
        print(f"  {name:<14} (no cases)")
        return
    started = time.perf_counter()
    try:
        results = [(predict(tx), expected, tx) for tx, expected in cases]
    except TypeSafeError as error:
        print(f"  {name:<14} unavailable: {str(error)[:100]}")
        return
    seconds = (time.perf_counter() - started) / len(cases)
    right = sum(got == expected for got, expected, _ in results)
    print(f"  {name:<14} {right:>4}/{len(cases):<4} {right / len(cases):6.1%}   {seconds:.2f}s per transaction")
    confusions = Counter((expected, got) for got, expected, _ in results if got != expected)
    for (expected, got), count in confusions.most_common(4):
        print(f"      {count:>3} x  {expected}  ->  {got}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", type=int, default=1, help="which round's training data the TF-IDF baseline learns from")
    parser.add_argument("--models", default="laya-english,laya-finance,tfidf")
    args = parser.parse_args()

    sets = {"handwritten (18)": handwritten(), "your labelled transactions": real_labelled()}
    names = [m.strip() for m in args.models.split(",") if m.strip()]
    predictors = {}
    for name in names:
        if name == "tfidf":
            predictors[name] = tfidf_classifier(args.round)
        else:
            predictors[name] = name  # opened per test set below

    for title, cases in sets.items():
        print(f"\n{title}: {len(cases)} transactions")
        for name in names:
            if name == "tfidf":
                run(name, predictors[name], cases)
            elif name == "jev-masked":
                api_key = jev_key()
                if api_key is None:
                    print(f"  {name:<14} skipped: set JEV_API_KEY (e.g. uv run --env-file ../playground/.env ...)")
                    continue
                with jev_category_classifier(api_key) as classify:
                    run(name, lambda tx, c=classify: c(tx).category, cases)
            else:
                with laya_classifier(model=name) as classify:
                    run(name, lambda tx, c=classify: c(tx).category, cases)
    print("\nDecision rule: use laya-finance only if it reaches >= 85% on your labelled transactions"
          " and clearly beats laya-english.")


if __name__ == "__main__":
    main()
