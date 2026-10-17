"""API tests on the trackmymoney_test database. Parsing is stubbed where the PDF content doesn't matter."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.parsing import statement_parser
from app.parsing.statement_parser import Statement as ParsedStatement
from app.parsing.statement_parser import Transaction as ParsedTransaction

FAKE_PDF = b"%PDF-1.7 a statement"


def parsed_statement() -> ParsedStatement:
    return ParsedStatement(
        metadata={
            "Bank": "Axis Bank",
            "Account Number": "923010012345678",
            "Statement Period": "01-04-2024 to 30-04-2024",
            "Header Mapping": "jev",
            "Opening Balance": Decimal("12750.00"),
        },
        transactions=[
            ParsedTransaction(date(2024, 4, 1), "UPI/412345/SWIGGY", Decimal("450.00"), Decimal(0), Decimal("12300.00")),
            ParsedTransaction(
                date(2024, 4, 2), "NEFT/ACME SALARY", Decimal(0), Decimal("85000.00"), Decimal("97300.00"), {"Chq No": "123"}
            ),
        ],
    )


@pytest.fixture
def fake_parse(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace the parser; returns a list recording each call's password and classifier."""
    calls: list[dict] = []

    def parse(source, password=None, classify=None):
        calls.append({"password": password, "classify": classify})
        return parsed_statement()

    monkeypatch.setattr(statement_parser, "parse", parse)
    return calls


def upload(client: TestClient, content: bytes, *, name="statement.pdf", password=None, key=None):
    return client.post(
        "/api/statements",
        files={"file": (name, content, "application/pdf")},
        data={"password": password} if password else {},
        headers={"X-TypeSafe-Key": key} if key else {},
    )


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"database": "ok", "server_jev_key": False}


def test_upload_list_read_delete(client: TestClient, fake_parse):
    response = upload(client, FAKE_PDF)
    assert response.status_code == 201
    created = response.json()
    assert created["bank"] == "Axis Bank"
    assert created["transaction_count"] == 2
    assert created["balance_check"] == "OK (oldest first)"

    assert [s["id"] for s in client.get("/api/statements").json()] == [created["id"]]

    transactions = client.get(f"/api/statements/{created['id']}/transactions").json()
    assert [t["particulars"] for t in transactions] == ["UPI/412345/SWIGGY", "NEFT/ACME SALARY"]
    assert transactions[0]["debit"] == "450.00"
    assert transactions[1]["extra"] == {"Chq No": "123"}

    assert client.delete(f"/api/statements/{created['id']}").status_code == 204
    assert client.get("/api/statements").json() == []
    assert client.get(f"/api/statements/{created['id']}/transactions").status_code == 404


def test_same_file_twice_is_a_duplicate(client: TestClient, fake_parse):
    assert upload(client, FAKE_PDF).status_code == 201
    response = upload(client, FAKE_PDF, name="renamed.pdf")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "duplicate"


def test_not_a_pdf(client: TestClient):
    response = upload(client, b"hello", name="notes.txt")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_a_pdf"


def test_locked_pdf_asks_for_password(client: TestClient, locked_pdf: bytes):
    def code(response):
        return response.json()["detail"]["code"]

    assert code(upload(client, locked_pdf)) == "password_required"
    assert code(upload(client, locked_pdf, password="nope")) == "wrong_password"
    # The right password opens it; this generated PDF is only an image, so parsing stops there.
    assert code(upload(client, locked_pdf, password="secret")) == "no_text_layer"
    assert client.get("/api/statements").json() == []  # nothing stored on failure


def test_no_transactions_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(statement_parser, "parse", lambda *args: ParsedStatement({}, []))
    response = upload(client, FAKE_PDF)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_transactions"


def test_jev_key_comes_from_the_request(client: TestClient, fake_parse):
    upload(client, FAKE_PDF, key="ts-test-key")
    assert fake_parse[-1]["classify"] is not None
    client.delete("/api/statements/1")

    upload(client, FAKE_PDF)  # no UI key and no server key: keyword rules only
    assert fake_parse[-1]["classify"] is None


def test_metadata_amounts_are_stored_as_text(client: TestClient, fake_parse, engine):
    from sqlalchemy import text

    upload(client, FAKE_PDF)
    with engine.connect() as connection:
        stored = connection.execute(text("select metadata from statements")).scalar_one()
    assert stored["Opening Balance"] == "12750.00"
