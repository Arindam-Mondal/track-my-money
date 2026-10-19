"""Category rules: config, validation, operators, precedence, and where they run (apply, upload, categorise)."""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import Statement, Transaction
from app.rules import config
from app.rules.operators import check_builders
from tests.test_api import FAKE_PDF, fake_parse, upload  # noqa: F401 (fake_parse is a fixture)
from tests.conftest import FakeLaya

RENT_TO_MOM = "UPI/P2A/412345678901/MAMATA  MONDAL /UPI/State Bank Of India"

# (particulars, debit, credit, category, source)
ROWS = [
    (RENT_TO_MOM, "26000.00", "0", None, None),
    ("UPI/P2A/998877665544/MAMATA MONDAL /UPI/State Bank Of India", "5000.00", "0", None, None),
    ("NEFT CR-RENT FROM TENANT", "0", "26000.00", None, None),
    ("UPI/SWIGGY/100%_OFF", "450.00", "0", None, None),
    ("ATM WDL", "2000.00", "0", "ATM Withdrawal", "manual"),
    ("SBIMF SIP", "1000.00", "0", "Other Expense", "laya"),
]


@pytest.fixture
def data(client: TestClient, sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(
            Statement(
                filename="test.pdf",
                file_sha256="test",
                bank="Axis Bank",
                balance_check="OK",
                metadata_={},
                transactions=[
                    Transaction(
                        row_index=i,
                        date=dt.date(2026, 3, 1 + i),
                        particulars=particulars,
                        debit=Decimal(debit),
                        credit=Decimal(credit),
                        balance=None,
                        extra={},
                        category=category,
                        category_source=source,
                        category_confidence=0.9 if source == "laya" else None,
                    )
                    for i, (particulars, debit, credit, category, source) in enumerate(ROWS)
                ],
            )
        )
        session.commit()


def cond(field: str, operator: str, value: str) -> dict:
    return {"field": field, "operator": operator, "value": value}


def all_of(*items: dict) -> dict:
    return {"match": "and", "items": list(items)}


def any_of(*items: dict) -> dict:
    return {"match": "or", "items": list(items)}


def rule(name: str, conditions: dict, category: str) -> dict:
    return {"name": name, "conditions": conditions, "category": category}


def create(client: TestClient, name: str, conditions: dict, category: str) -> dict:
    response = client.post("/api/rules", json=rule(name, conditions, category))
    assert response.status_code == 201, response.text
    return response.json()


def preview(client: TestClient, conditions: dict, category: str = "Pass-through", rule_id: int | None = None) -> dict:
    params = {"rule_id": rule_id} if rule_id is not None else {}
    response = client.post("/api/rules/preview", json={"conditions": conditions, "category": category}, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def by_particulars(sessions: sessionmaker[Session]) -> dict[str, Transaction]:
    with sessions() as session:
        return {t.particulars: t for t in session.query(Transaction)}


MOM = all_of(cond("particulars", "regex", r"UPI/P2A/\d+/MAMATA MONDAL"), cond("debit", "eq", "26000"))


# ---------------------------------------------------------------- config


def test_config_is_what_the_config_module_declares(client: TestClient):
    body = client.get("/api/rules/config").json()
    assert [(f["id"], f["label"], f["type"]) for f in body["fields"]] == [
        (key, f.label, f.type) for key, f in config.FIELDS.items()
    ]
    assert body["types"]["string"]["input"] == "text"
    assert body["types"]["number"]["input"] == "number"
    assert [o["id"] for o in body["types"]["number"]["operators"]] == ["eq", "ne", "gt", "lt", "ge", "le"]
    regex = next(o for o in body["types"]["string"]["operators"] if o["id"] == "regex")
    assert regex["label"] == "matches regex" and "case-insensitive" in regex["hint"]
    assert body["connectors"] == [{"id": "and", "label": "AND"}, {"id": "or", "label": "OR"}]
    assert {"Pass-through", "House Rent"} <= {c["name"] for c in body["categories"]["out"]}
    assert body["limits"] == {"max_conditions": 20, "max_value_length": 300, "max_depth": 3}


def test_an_operator_without_sql_is_caught(monkeypatch: pytest.MonkeyPatch):
    check_builders()  # the shipped config is complete
    extra = config.FieldType("number", (config.Operator("between", "between"),), config.parse_number)
    monkeypatch.setitem(config.TYPES, "range", extra)
    with pytest.raises(RuntimeError, match="range.between"):
        check_builders()


def test_a_column_added_to_the_config_works_without_other_changes(client: TestClient, data, monkeypatch):
    monkeypatch.setitem(config.FIELDS, "row", config.Field("Row", "number", Transaction.row_index))
    assert "row" in {f["id"] for f in client.get("/api/rules/config").json()["fields"]}
    assert preview(client, all_of(cond("row", "lt", "2")))["total"] == 2


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("conditions", "category", "message", "number"),
    [
        (all_of(cond("payee", "contains", "x")), "Pass-through", "Unknown column", 1),
        (all_of(cond("debit", "eq", "1"), cond("particulars", "gt", "x")), "Pass-through", "can't use the operator", 2),
        (all_of(cond("debit", "eq", "lots")), "Pass-through", "isn't a number", 1),
        (all_of(cond("particulars", "contains", "   ")), "Pass-through", "Enter some text", 1),
        (all_of(cond("particulars", "regex", "UPI/(P2A")), "Pass-through", "Not a valid regular expression", 1),
        (all_of(cond("particulars", "contains", "x" * 301)), "Pass-through", "at most 300", 1),
        ({"match": "xor", "items": [cond("debit", "eq", "1")]}, "Pass-through", "Unknown connector", None),
        ({"match": "and", "items": []}, "Pass-through", "at least one condition", None),
        (any_of(all_of(any_of(all_of(cond("debit", "eq", "1"))))), "Pass-through", "levels deep", None),
        (all_of(*[cond("debit", "eq", "1")] * 21), "Pass-through", "at most 20 conditions", None),
        (all_of(cond("debit", "eq", "1")), "Holidays", "Unknown category", None),
    ],
)
def test_invalid_rules_are_rejected(client: TestClient, conditions, category, message, number):
    response = client.post("/api/rules", json=rule("Bad", conditions, category))
    assert response.status_code == 422
    assert message in response.json()["detail"]["message"]
    assert response.json()["detail"]["condition"] == number
    assert client.get("/api/rules").json() == []


def test_names_are_unique_ignoring_case(client: TestClient):
    create(client, "Rent to Mom", MOM, "Pass-through")
    assert client.post("/api/rules", json=rule("rent to mom", MOM, "Pass-through")).status_code == 409
    other = create(client, "Other", MOM, "Pass-through")
    assert client.put(f"/api/rules/{other['id']}", json=rule("RENT TO MOM", MOM, "Pass-through")).status_code == 409


# ---------------------------------------------------------------- operators


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (cond("particulars", "contains", "mamata   mondal"), 2),  # case and whitespace
        (cond("particulars", "contains", "100%_off"), 1),
        (cond("particulars", "contains", "%"), 1),  # literal, not a wildcard
        (cond("particulars", "contains", "_"), 1),
        (cond("particulars", "not_contains", "upi"), 3),
        (cond("particulars", "equals", "atm wdl"), 1),
        (cond("particulars", "equals", "atm"), 0),
        (cond("particulars", "not_equals", "atm wdl"), 5),
        (cond("particulars", "starts_with", "upi/p2a"), 2),
        (cond("particulars", "ends_with", "of india"), 2),
        (cond("particulars", "regex", r"UPI/P2A/\d+/MAMATA MONDAL"), 2),
        (cond("particulars", "regex", r"^upi/p2a/4\d{11}/"), 1),
        (cond("particulars", "not_regex", r"MAMATA"), 4),
        (cond("bank", "contains", "axis"), 6),
        (cond("debit", "eq", "26000"), 1),
        (cond("debit", "ne", "26000"), 5),
        (cond("debit", "gt", "1000"), 3),
        (cond("debit", "lt", "1000"), 2),
        (cond("debit", "ge", "1,000"), 4),
        (cond("debit", "le", "450"), 2),
        (cond("credit", "eq", "26000.00"), 1),
    ],
)
def test_operators(client: TestClient, data, condition, expected):
    assert preview(client, all_of(condition))["total"] == expected


def test_and_binds_tighter_than_or(client: TestClient, data):
    # MAMATA and debit 26000, or credit 26000: the rent to mom and the rent from the tenant
    conditions = any_of(
        all_of(cond("particulars", "contains", "MAMATA"), cond("debit", "eq", "26000")),
        all_of(cond("credit", "eq", "26000")),
    )
    assert preview(client, conditions)["total"] == 2


# ---------------------------------------------------------------- applying


def test_apply_one_rule_sets_matches_and_keeps_manual(client: TestClient, data, sessions):
    mom = create(client, "Rent to Mom", MOM, "Pass-through")
    assert by_particulars(sessions)[RENT_TO_MOM].category is None  # saving changes nothing
    assert client.post(f"/api/rules/{mom['id']}/apply").json() == {"set": 1, "cleared": 0}

    row = by_particulars(sessions)[RENT_TO_MOM]
    assert (row.category, row.category_source, row.category_rule_id, row.category_confidence) == (
        "Pass-through", "rule", mom["id"], None
    )
    assert client.get("/api/rules").json()[0]["applied_count"] == 1

    atm = create(client, "ATM", all_of(cond("particulars", "contains", "ATM")), "Other Expense")
    assert client.post(f"/api/rules/{atm['id']}/apply").json() == {"set": 0, "cleared": 0}
    assert by_particulars(sessions)["ATM WDL"].category_source == "manual"


def test_rules_overwrite_model_answers(client: TestClient, data, sessions):
    sip = create(client, "SIP", all_of(cond("particulars", "starts_with", "SBIMF")), "Mutual Fund / SIP")
    assert preview(client, all_of(cond("particulars", "starts_with", "SBIMF")), "Mutual Fund / SIP")["will_set"] == 1
    client.post(f"/api/rules/{sip['id']}/apply")
    row = by_particulars(sessions)["SBIMF SIP"]
    assert (row.category, row.category_source) == ("Mutual Fund / SIP", "rule")


def test_first_rule_in_the_list_wins(client: TestClient, data, sessions):
    first = create(client, "Mom", all_of(cond("particulars", "contains", "MAMATA")), "Transfer to Others")
    second = create(client, "Mom's rent", MOM, "Pass-through")
    assert client.post("/api/rules/apply").json() == {"set": 2, "cleared": 0}
    assert by_particulars(sessions)[RENT_TO_MOM].category == "Transfer to Others"

    # The second rule alone can't take rows the first one holds.
    assert client.post(f"/api/rules/{second['id']}/apply").json() == {"set": 0, "cleared": 0}
    assert preview(client, MOM, rule_id=second["id"])["other_rule"] == 1
    assert [r["id"] for r in client.get("/api/rules").json()] == [first["id"], second["id"]]


def test_a_category_only_applies_to_its_direction(client: TestClient, data, sessions):
    everything = all_of(cond("bank", "contains", "axis"))
    result = preview(client, everything, "House Rent")
    assert (result["total"], result["manual"], result["wrong_direction"], result["will_set"]) == (6, 1, 1, 4)
    no_category_yet = preview(client, everything, "")  # the builder previews before a category is picked
    assert (no_category_yet["wrong_direction"], no_category_yet["will_set"]) == (0, 5)
    assert client.post("/api/rules", json=rule("No category", everything, "")).status_code == 422

    house = create(client, "Everything", everything, "House Rent")
    assert client.post(f"/api/rules/{house['id']}/apply").json() == {"set": 4, "cleared": 0}
    assert by_particulars(sessions)["NEFT CR-RENT FROM TENANT"].category is None


def test_edit_then_apply_clears_rows_that_no_longer_match(client: TestClient, data, sessions):
    mom = create(client, "Mom", all_of(cond("particulars", "contains", "MAMATA")), "Pass-through")
    assert client.post(f"/api/rules/{mom['id']}/apply").json() == {"set": 2, "cleared": 0}

    edited = client.put(f"/api/rules/{mom['id']}", json=rule("Mom", MOM, "Pass-through"))
    assert edited.json()["applied_count"] == 2  # unchanged until applied
    assert client.post(f"/api/rules/{mom['id']}/apply").json() == {"set": 1, "cleared": 1}
    rows = by_particulars(sessions)
    assert rows[RENT_TO_MOM].category == "Pass-through"
    assert rows[ROWS[1][0]].category is None and rows[ROWS[1][0]].category_source is None


def test_deleting_a_rule_clears_only_its_rows(client: TestClient, data, sessions):
    mom = create(client, "Mom", MOM, "Pass-through")
    swiggy = create(client, "Swiggy", all_of(cond("particulars", "contains", "swiggy")), "Food & Dining")
    client.post("/api/rules/apply")
    assert client.delete(f"/api/rules/{mom['id']}").status_code == 204
    rows = by_particulars(sessions)
    assert rows[RENT_TO_MOM].category is None
    assert (rows["UPI/SWIGGY/100%_OFF"].category, rows["UPI/SWIGGY/100%_OFF"].category_rule_id) == (
        "Food & Dining", swiggy["id"]
    )
    assert client.delete(f"/api/rules/{mom['id']}").status_code == 404


def test_setting_a_category_by_hand_detaches_the_rule(client: TestClient, data, sessions):
    mom = create(client, "Mom", MOM, "Pass-through")
    client.post(f"/api/rules/{mom['id']}/apply")
    row_id = by_particulars(sessions)[RENT_TO_MOM].id
    changed = client.patch(f"/api/transactions/{row_id}", json={"category": "Transfer to Others"}).json()
    assert (changed["category_source"], changed["category_rule_id"]) == ("manual", None)
    assert client.post("/api/rules/apply").json()["set"] == 0  # manual wins


# ---------------------------------------------------------------- where rules run


def test_upload_applies_rules(client: TestClient, fake_parse):  # noqa: F811
    create(client, "Swiggy", all_of(cond("particulars", "contains", "swiggy")), "Food & Dining")
    created = upload(client, FAKE_PDF).json()
    assert created["categorised_count"] == 1
    swiggy, salary = client.get(f"/api/statements/{created['id']}/transactions").json()
    assert (swiggy["category"], swiggy["category_source"]) == ("Food & Dining", "rule")
    assert salary["category"] is None  # left for Laya or Jev, which run only when asked


def test_categorising_runs_rules_first_and_the_model_never_overwrites_them(
    client: TestClient, data, sessions, laya: FakeLaya
):
    create(client, "Mom", MOM, "Pass-through")
    statement_id = by_particulars(sessions)[RENT_TO_MOM].statement_id
    for redo in ("false", "true"):
        laya.calls.clear()
        assert client.post(f"/api/statements/{statement_id}/categorise?redo={redo}").status_code == 202
        assert RENT_TO_MOM not in {tx.narration for tx in laya.calls}
        row = by_particulars(sessions)[RENT_TO_MOM]
        assert (row.category, row.category_source) == ("Pass-through", "rule")
    assert by_particulars(sessions)["ATM WDL"].category_source == "manual"


def test_pass_through_set_by_a_rule_is_not_counted(client: TestClient, data):
    before = client.get("/api/analytics/monthly?exclude_self=false").json()[0]["money_out"]
    mom = create(client, "Mom", MOM, "Pass-through")
    client.post(f"/api/rules/{mom['id']}/apply")
    after = client.get("/api/analytics/monthly?exclude_self=false").json()[0]["money_out"]
    assert Decimal(before) - Decimal(after) == Decimal("26000")
