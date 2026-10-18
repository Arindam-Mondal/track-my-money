"""Categorising with Laya (faked here), manual corrections, and the categories API."""

import urllib.request
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.categorising import jobs
from app.categorising.categories import CATEGORIES
from app.categorising.laya import TxInput, build_question, build_state
from app.config import settings
from app.parsing import statement_parser
from tests.conftest import FakeLaya
from tests.test_api import FAKE_PDF, parsed_statement, upload


@pytest.fixture
def uploaded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> int:
    """One uploaded statement (a debit and a credit), not categorised."""
    monkeypatch.setattr(statement_parser, "parse", lambda *args: parsed_statement())
    response = upload(client, FAKE_PDF)
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def imported(client: TestClient, uploaded: int) -> int:
    """The uploaded statement, categorised by the fake Laya on request."""
    assert client.post(f"/api/statements/{uploaded}/categorise").status_code == 202
    return uploaded


def transactions(client: TestClient, statement_id: int) -> list[dict]:
    return client.get(f"/api/statements/{statement_id}/transactions").json()


def test_each_direction_gets_its_own_categories():
    out = build_question("out")
    assert list(out.criteria) == list(CATEGORIES["out"])
    assert list(build_question("in").criteria) == list(CATEGORIES["in"])


def test_laya_sees_the_full_narration():
    state = build_state(TxInput("UPI/412345/SWIGGY/rahul@okaxis", "out", Decimal("450")))
    assert state == {
        "narration": "UPI/412345/SWIGGY/rahul@okaxis",  # unmasked: Laya runs locally
        "direction": "money out of the account",
        "amount": "450.00",
        "other_columns": {},
    }


def test_upload_never_categorises(client: TestClient, uploaded: int, laya: FakeLaya):
    assert laya.calls == []
    assert [t["category"] for t in transactions(client, uploaded)] == [None, None]
    statement = client.get("/api/statements").json()[0]
    assert (statement["categorised_count"], statement["categorising"]) == (0, False)


def test_categorise_on_request(client: TestClient, imported: int, laya: FakeLaya):
    rows = transactions(client, imported)
    assert [(t["category"], t["category_source"]) for t in rows] == [
        ("Other Expense", "laya"),
        ("Other Income", "laya"),
    ]
    assert [tx.direction for tx in sorted(laya.calls, key=lambda tx: tx.direction)] == ["in", "out"]
    statement = client.get("/api/statements").json()[0]
    assert (statement["categorised_count"], statement["categorising"]) == (2, False)


def test_manual_category_is_never_overwritten(client: TestClient, imported: int, laya: FakeLaya):
    debit, credit = transactions(client, imported)
    response = client.patch(f"/api/transactions/{debit['id']}", json={"category": "Groceries"})
    assert response.json()["category_source"] == "manual"

    laya.answers = {"out": "Shopping", "in": "Salary"}
    assert client.post(f"/api/statements/{imported}/categorise?redo=true").status_code == 202
    debit, credit = transactions(client, imported)
    assert (debit["category"], debit["category_source"]) == ("Groceries", "manual")
    assert (credit["category"], credit["category_source"]) == ("Salary", "laya")  # redo changed Laya's answer


def test_without_redo_only_uncategorised_are_asked(client: TestClient, imported: int, laya: FakeLaya):
    laya.calls.clear()
    client.post(f"/api/statements/{imported}/categorise")
    assert laya.calls == []  # both already categorised


def test_laya_down_leaves_transactions_uncategorised(client: TestClient, uploaded: int, laya: FakeLaya):
    laya.fail = True
    client.post(f"/api/statements/{uploaded}/categorise")
    assert [t["category"] for t in transactions(client, uploaded)] == [None, None]
    assert not jobs.is_running(uploaded)  # released, so it can be retried


def test_category_must_match_the_direction(client: TestClient, imported: int):
    debit, _ = transactions(client, imported)
    response = client.patch(f"/api/transactions/{debit['id']}", json={"category": "Salary"})
    assert response.status_code == 422
    assert client.patch("/api/transactions/999", json={"category": "Groceries"}).status_code == 404


def test_categorise_endpoint_errors(client: TestClient, imported: int):
    assert client.post("/api/statements/999/categorise").status_code == 404
    assert jobs.claim(imported)  # pretend a job is running
    assert client.post(f"/api/statements/{imported}/categorise").status_code == 409


def test_categories_api(client: TestClient):
    categories = client.get("/api/categories").json()
    assert [c["name"] for c in categories["out"]] == list(CATEGORIES["out"])
    assert [c["name"] for c in categories["in"]] == list(CATEGORIES["in"])


# ---------------------------------------------------------------- the real Laya, when it's running

def laya_is_up() -> bool:
    try:
        urllib.request.urlopen(f"{settings.laya_base_url}/health", timeout=2)
        return True
    except OSError:
        return False


@pytest.mark.skipif(not laya_is_up(), reason="Laya is not running (docker compose up -d laya)")
def test_real_laya_answers_a_known_category():
    from app.categorising.laya import laya_classifier

    with laya_classifier() as classify:
        answer = classify(TxInput("ATM WDL/NFS/CASH WITHDRAWAL/S1ANMU12", "out", Decimal("5000")))
    assert answer.category == "ATM Withdrawal"
    assert 0 <= answer.confidence <= 1


# ---------------------------------------------------------------- masking and Jev

def test_upload_stores_masked_text(client: TestClient, uploaded: int):
    rows = transactions(client, uploaded)
    assert rows[0]["particulars_masked"] == "UPI/[REF]/SWIGGY"
    assert "412345" not in rows[0]["particulars_masked"]


def test_backfill_masks_rows_without_masked_text(client: TestClient, uploaded: int, sessions):
    from app.masking.backfill import backfill
    from app.models import Transaction

    with sessions() as session:
        for t in session.query(Transaction):
            t.particulars_masked, t.masking_version = None, None
        session.commit()
        assert backfill(session) == 2
    assert all(t["particulars_masked"] for t in transactions(client, uploaded))


def test_jev_needs_a_key(client: TestClient, uploaded: int, laya: FakeLaya):
    response = client.post(f"/api/statements/{uploaded}/categorise?categoriser=jev")
    assert response.status_code == 422
    assert laya.categorisers == []


def test_categorise_with_jev(client: TestClient, uploaded: int, laya: FakeLaya):
    response = client.post(f"/api/statements/{uploaded}/categorise?categoriser=jev", headers={"X-TypeSafe-Key": "ts-key"})
    assert response.status_code == 202
    assert laya.categorisers == [("jev", "ts-key")]
    assert {t["category_source"] for t in transactions(client, uploaded)} == {"jev"}
    assert all(tx.masked_narration for tx in laya.calls)  # every transaction had masked text to send


def test_jev_only_ever_sees_masked_text():
    from app.categorising.jev import amount_range, build_jev_state

    tx = TxInput("UPI/P2A/412345678901/RAHUL SHARMA/rahul@okaxis", "out", Decimal("25000"),
                 masked_narration="UPI/P2A/[REF]/[PERSON_7F3A]/[UPI_ID]@okaxis")
    state = build_jev_state(tx)
    assert state == {"narration": "UPI/P2A/[REF]/[PERSON_7F3A]/[UPI_ID]@okaxis",
                     "direction": "money out of the account", "amount": "₹10k–50k"}
    assert "RAHUL" not in str(state) and "25000" not in str(state)
    with pytest.raises(Exception, match="no masked narration"):
        build_jev_state(TxInput("raw text", "out", Decimal(1)))
    assert [amount_range(Decimal(v)) for v in (499, 500, 1999, 9999, 49999, 199999, 200000)] == [
        "under ₹500", "₹500–2k", "₹500–2k", "₹2k–10k", "₹10k–50k", "₹50k–2L", "over ₹2L"]


def test_redo_covers_laya_and_jev_but_not_manual(client: TestClient, imported: int, laya: FakeLaya):
    debit, credit = transactions(client, imported)
    client.patch(f"/api/transactions/{debit['id']}", json={"category": "Groceries"})
    laya.answers = {"out": "Shopping", "in": "Salary"}
    client.post(f"/api/statements/{imported}/categorise?categoriser=jev&redo=true", headers={"X-TypeSafe-Key": "k"})
    debit, credit = transactions(client, imported)
    assert (debit["category"], debit["category_source"]) == ("Groceries", "manual")
    assert (credit["category"], credit["category_source"]) == ("Salary", "jev")
