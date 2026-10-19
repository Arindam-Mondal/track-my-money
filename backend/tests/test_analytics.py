"""Money-flow analytics on a small known set of transactions."""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import Statement, Transaction

# (date, debit, credit, category)
ROWS = [
    ("2026-01-05", "0", "100000.00", "Salary"),
    ("2026-01-10", "25000.00", "0", "House Rent"),
    ("2026-01-12", "450.00", "0", "Food & Dining"),
    ("2026-01-20", "10000.00", "0", "Transfer to Self"),
    ("2026-03-02", "0", "100000.00", "Salary"),
    ("2026-03-03", "550.00", "0", "Food & Dining"),
    ("2026-03-04", "999.00", "0", None),
    ("2026-03-05", "0", "10000.00", "Transfer from Self"),
]


@pytest.fixture
def data(client: TestClient, sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(
            Statement(
                filename="test.pdf",
                file_sha256="test",
                balance_check="OK",
                metadata_={},
                transactions=[
                    Transaction(
                        row_index=i,
                        date=dt.date.fromisoformat(day),
                        particulars=f"row {i}",
                        debit=Decimal(debit),
                        credit=Decimal(credit),
                        balance=None,
                        extra={},
                        category=category,
                        category_source="laya" if category else None,
                    )
                    for i, (day, debit, credit, category) in enumerate(ROWS)
                ],
            )
        )
        session.commit()


def test_monthly_fills_gaps_and_leaves_out_self_transfers(client: TestClient, data):
    assert client.get("/api/analytics/monthly").json() == [
        {"month": "2026-01", "money_in": "100000.00", "money_out": "25450.00", "net": "74550.00"},
        {"month": "2026-02", "money_in": "0.00", "money_out": "0.00", "net": "0.00"},
        {"month": "2026-03", "money_in": "100000.00", "money_out": "1549.00", "net": "98451.00"},
    ]


def test_monthly_can_include_self_transfers_and_filter_by_period(client: TestClient, data):
    flows = client.get("/api/analytics/monthly?exclude_self=false&from=2026-03&to=2026-03").json()
    assert flows == [{"month": "2026-03", "money_in": "110000.00", "money_out": "1549.00", "net": "108451.00"}]


def test_spending_by_category_largest_first(client: TestClient, data):
    totals = client.get("/api/analytics/categories?direction=out").json()
    assert [(t["category"], t["total"], t["count"]) for t in totals] == [
        ("House Rent", "25000.00", 1),
        ("Food & Dining", "1000.00", 2),
        ("Uncategorised", "999.00", 1),
    ]


def test_income_by_category(client: TestClient, data):
    totals = client.get("/api/analytics/categories?direction=in&exclude_self=false").json()
    assert [(t["category"], t["total"]) for t in totals] == [("Salary", "200000.00"), ("Transfer from Self", "10000.00")]


def test_category_trend(client: TestClient, data):
    assert client.get("/api/analytics/trend", params={"category": "Food & Dining"}).json() == [
        {"month": "2026-01", "total": "450.00"},
        {"month": "2026-02", "total": "0.00"},
        {"month": "2026-03", "total": "550.00"},
    ]
    assert client.get("/api/analytics/trend", params={"category": "Nonsense"}).status_code == 422


def test_bad_month_is_rejected(client: TestClient):
    assert client.get("/api/analytics/monthly?from=2026-13").status_code == 422


@pytest.fixture
def with_pass_through(data, sessions: sessionmaker[Session]) -> None:
    """Rent collected for someone (in) and passed on (out), both in March."""
    with sessions() as session:
        statement = session.query(Statement).one()
        for i, (debit, credit) in enumerate([("0", "26000.00"), ("26000.00", "0")]):
            statement.transactions.append(Transaction(
                row_index=100 + i, date=dt.date(2026, 3, 10 + i), particulars=f"pass {i}", debit=Decimal(debit),
                credit=Decimal(credit), balance=None, extra={}, category="Pass-through", category_source="manual",
            ))
        session.commit()


@pytest.mark.parametrize("exclude_self", ["true", "false"])
def test_pass_through_is_never_counted(client: TestClient, with_pass_through, exclude_self):
    march = client.get(f"/api/analytics/monthly?from=2026-03&to=2026-03&exclude_self={exclude_self}").json()[0]
    expected_in = "100000.00" if exclude_self == "true" else "110000.00"  # the only change is the self transfer
    assert (march["money_in"], march["money_out"]) == (expected_in, "1549.00")
    for direction in ("in", "out"):
        totals = client.get(f"/api/analytics/categories?direction={direction}&exclude_self={exclude_self}").json()
        assert "Pass-through" not in {t["category"] for t in totals}
    assert client.get("/api/analytics/trend", params={"category": "Pass-through"}).status_code == 422
