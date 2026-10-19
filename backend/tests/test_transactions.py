"""Searching transactions across statements and setting categories in bulk."""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import Statement, Transaction

# (statement, date, narration, debit, credit, category)
ROWS = [
    (1, "2026-04-05", "NACH-MUT-DR/SBIMF/SIP 1234", "5000", "0", None),
    (1, "2026-05-05", "NACH-MUT-DR/SBIMF/SIP 1234", "5000", "0", "Other Expense"),
    (1, "2026-05-07", "UPI/P2M/1/SWIGGY/swiggy@icici", "450", "0", "Food & Dining"),
    (2, "2026-05-09", "UPI/P2A/2/FRIEND/x@okaxis", "1,000", "0", None),
    (2, "2026-05-10", "IMPS/P2A/3/SOMEONE/REFUND", "0", "1000", None),
]


@pytest.fixture
def data(client: TestClient, sessions: sessionmaker[Session]) -> list[int]:
    with sessions() as session:
        statements = {
            n: Statement(filename=f"s{n}.pdf", file_sha256=f"s{n}", bank=bank, account_number=acct,
                         balance_check="OK", metadata_={})
            for n, bank, acct in ((1, "Axis Bank", "923010003869"), (2, "State Bank of India", "20123640410"))
        }
        for i, (n, day, text, debit, credit, category) in enumerate(ROWS):
            statements[n].transactions.append(Transaction(
                row_index=i, date=dt.date.fromisoformat(day), particulars=text, particulars_masked=text,
                debit=Decimal(debit.replace(",", "")), credit=Decimal(credit), balance=None, extra={},
                category=category, category_source="laya" if category else None,
            ))
        session.add_all(statements.values())
        session.commit()
        return [t.id for s in statements.values() for t in s.transactions]


def search(client: TestClient, **params) -> dict:
    return client.get("/api/transactions", params=params).json()


def test_text_search_across_statements(client: TestClient, data):
    result = search(client, q="sbimf")
    assert result["total"] == 2
    assert {t["bank"] for t in result["transactions"]} == {"Axis Bank"}
    assert result["transactions"][0]["account_last4"] == "3869"


def test_amount_search_matches_debits_and_credits(client: TestClient, data):
    assert search(client, q="1,000")["total"] == 2
    assert search(client, q="1000", direction="out")["total"] == 1


def test_date_and_month_search(client: TestClient, data):
    assert search(client, q="2026-05")["total"] == 4
    assert search(client, q="05-04-2026")["total"] == 1


def test_filters(client: TestClient, data):
    assert search(client, category="Uncategorised")["total"] == 3
    assert search(client, category="Food & Dining")["total"] == 1
    assert search(client, q="state bank")["total"] == 2  # bank name


def test_bulk_update_sets_manual(client: TestClient, data):
    ids = [t["id"] for t in search(client, q="SBIMF")["transactions"]]
    response = client.patch("/api/transactions/bulk", json={"ids": ids, "category": "Mutual Fund / SIP"})
    assert response.json() == {"updated": 2}
    rows = search(client, q="SBIMF")["transactions"]
    assert {(t["category"], t["category_source"]) for t in rows} == {("Mutual Fund / SIP", "manual")}


def test_bulk_update_rejects_mixed_directions(client: TestClient, data):
    ids = [t["id"] for t in search(client, q="1,000")["transactions"]]  # one debit, one credit
    response = client.patch("/api/transactions/bulk", json={"ids": ids, "category": "Transfer to Others"})
    assert response.status_code == 422
    assert search(client, category="Uncategorised")["total"] == 3  # nothing changed


def test_bulk_update_unknown_id(client: TestClient, data):
    assert client.patch("/api/transactions/bulk", json={"ids": [999999], "category": "Shopping"}).status_code == 404


def test_single_update_still_works(client: TestClient, data):
    response = client.patch(f"/api/transactions/{data[3]}", json={"category": "Transfer to Others"})
    assert response.json()["category_source"] == "manual"


def test_pass_through_can_be_set_on_money_in_and_out_together(client: TestClient, data):
    ids = [t["id"] for t in search(client, q="1,000")["transactions"]]  # one debit, one credit
    response = client.patch("/api/transactions/bulk", json={"ids": ids, "category": "Pass-through"})
    assert response.json() == {"updated": 2}
