"""Tests for header classification: masking, Jev answers, fallbacks and the header-image path.

Jev is replaced by fakes, so these run offline: uv run pytest
"""

from types import SimpleNamespace

import pytest
from typesafe_sdk import ChoiceAnswer, Image, TypeSafeError

import header_classifier
from header_classifier import IMAGES_HEADER, build_state, classify_with_jev, mask_cell, to_label
from statement_parser import Statement, build_transactions, check_balances, detect_header

HEADER = ["Txn Date", "Narration", "Transaction Type", "Amount", "Balance"]
ROWS = [
    ["01-04-2024", "UPI/412345/SWIGGY", "Dr", "450.00", "12,300.00"],
    ["02-04-2024", "NEFT/ACME SALARY", "Cr", "85,000.00", "97,300.00"],
]
JEV_LABELS = ("date", "particulars", "drcr", "amount", "balance")


@pytest.fixture(autouse=True)
def empty_cache():
    header_classifier._cache.clear()


def answer(choice, confidence):
    return ChoiceAnswer(choice=choice, confidence=confidence, probabilities={choice: confidence})


def never_called(*args):
    raise AssertionError("Jev should not have been called")


# ---------------------------------------------------------------- masking and labels

@pytest.mark.parametrize("text, masked", [
    ("UPI/412345/SWIGGY", "UPI/999999/XXXXXX"),
    ("1,234.50 Dr", "9,999.99 Dr"),
    ("01-Jan-2024", "99-Jan-9999"),
    ("Rahul Sharma", "Xxxxx Xxxxxx"),
    ("NEFT-HDFC0001234-ACME CORP", "NEFT-XXXX9999999-XXXX XX"),
    ("राहुल", "xxxxx"),
    ("", ""),
])
def test_mask_cell_keeps_shape_and_hides_content(text, masked):
    assert mask_cell(text) == masked


def test_to_label():
    assert to_label(answer("debit", 0.9)) == "debit"
    assert to_label(answer("other", 0.9)) == "other"
    assert to_label(answer("debit", 0.47)) is None  # unsure -> column dropped
    assert to_label(answer("nonsense", 0.9)) is None


# ---------------------------------------------------------------- talking to Jev

class FakeClient:
    """Stands in for TypeSafeClient: records each request and answers every column with `labels`."""

    def __init__(self, labels):
        self.labels = labels
        self.requests = []

    def system_one(self, state, questions, extra_headers=None):
        self.requests.append((state, questions, extra_headers))
        return SimpleNamespace(choices={f"col_{i}": answer(label, 0.99) for i, label in enumerate(self.labels)})


def test_state_holds_masked_samples_and_optional_images():
    state = build_state(HEADER, ROWS)
    assert state["columns"][1] == {"header": "Narration", "samples": ["UPI/999999/XXXXXX", "NEFT/XXXX XXXXXX"]}
    assert "header_image" not in state["columns"][0]

    with_images = build_state(HEADER, ROWS, [b"png"] * len(HEADER))
    assert isinstance(with_images["columns"][0]["header_image"], Image)


def test_classify_caches_per_header_and_sends_image_header_only_with_images():
    client = FakeClient(JEV_LABELS)
    assert classify_with_jev(HEADER, ROWS, client) == JEV_LABELS
    classify_with_jev(HEADER, ROWS, client)
    assert len(client.requests) == 1  # same header -> cached
    assert client.requests[0][2] is None

    classify_with_jev(HEADER, ROWS, client, [b"a"] * len(HEADER))
    classify_with_jev(HEADER, ROWS, client, [b"b"] * len(HEADER))
    assert len(client.requests) == 3  # different images -> different header
    assert client.requests[1][2] == IMAGES_HEADER


# ---------------------------------------------------------------- detect_header

def test_uses_jev_labels_the_rules_dont_know():
    header, source = detect_header(HEADER, ROWS, lambda cells, samples, images: JEV_LABELS)
    assert source == "jev"
    assert header is not None and header.columns["drcr"] == 2


def test_falls_back_to_rules_when_jev_fails():
    def down(cells, samples, images):
        raise TypeSafeError("no network")

    header, source = detect_header(HEADER, ROWS, down)
    assert source == "rules (fallback)"
    assert header is not None and "drcr" not in header.columns  # rules don't know "Transaction Type"


def test_falls_back_to_rules_when_jev_labels_are_unusable():
    _, source = detect_header(HEADER, ROWS, lambda cells, samples, images: (None,) * len(HEADER))
    assert source == "rules (fallback)"


def test_rules_only_never_calls_jev():
    _, source = detect_header(HEADER, ROWS, None)
    assert source == "rules"


def test_data_rows_and_text_blocks_never_reach_jev():
    assert detect_header(ROWS[0], ROWS[1:], never_called) == (None, "rules")
    disclaimer = ["Unless the", "constituent notifies the", "bank immediately", "of any discrepancy"]
    assert detect_header(disclaimer, [["found by him/her", "in this", "statement", ""]], never_called) == (None, "rules")


def test_images_only_for_unreadable_headers():
    images_seen = []

    def jev(cells, samples, images):
        images_seen.append(images)
        return ("other", "date", "particulars", "other", "debit", "credit", "balance")

    unreadable = ["", "", "", "", "", "", "Balance"]
    data = [["01/04/2026", "01/04/2026", "DEP TFR", "-", "-", "1,00,000.00", "5,41,076.85"]]
    header, source = detect_header(unreadable, data, jev, lambda: [b"png"] * 7)
    assert source == "jev (image)"
    assert header is not None and header.columns == {"date": 1, "particulars": 2, "debit": 4, "credit": 5, "balance": 6}
    assert images_seen == [[b"png"] * 7]

    # A readable header is classified from its text; the renderer is never called.
    _, source = detect_header(HEADER, ROWS, lambda cells, samples, images: JEV_LABELS, never_called)
    assert source == "jev"


# ---------------------------------------------------------------- end to end

def test_statement_with_unreadable_header_parses_from_images():
    header = ["", "", "", "", "", "", "Balance"]
    rows = [
        ["01/04/2026", "01/04/2026", "DEP TFR", "-", "-", "1,00,000.00", "5,41,076.85"],
        ["02/04/2026", "02/04/2026", "ATM WDL", "-", "1,000.00", "-", "5,40,076.85"],
        ["03/04/2026", "03/04/2026", "UPI/412345/SWIGGY", "412345", "-", "500.00", "5,40,576.85"],
    ]

    def jev(cells, samples, images):
        assert images is not None, "an unreadable header needs its images"
        return ("other", "date", "particulars", "other", "debit", "credit", "balance")

    metadata = {}
    transactions = build_transactions(
        [(header, lambda: [b"png"] * 7)] + [(row, None) for row in rows], metadata, jev
    )
    assert metadata["Header Mapping"] == "jev (image)"
    assert [str(t.debit) for t in transactions] == ["0", "1000.00", "0"]
    assert [str(t.credit) for t in transactions] == ["100000.00", "0", "500.00"]
    assert transactions[0].metadata == {"Column 1": "01/04/2026", "Column 4": "-"}
    assert check_balances(Statement(metadata, transactions)) == "OK (oldest first)"


def test_no_transactions_is_not_ok():
    assert check_balances(Statement({}, [])).startswith("no transactions found")
