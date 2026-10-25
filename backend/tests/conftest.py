"""Shared fixtures: generated PDFs, and an API client on the trackmymoney_test database."""

import io
from collections.abc import Iterator
from contextlib import contextmanager

import PIL.Image
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from typesafe_sdk import TypeSafeError

from app.categorising import jobs
from app.categorising.laya import CategoryAnswer, CategoryClassifier, TxInput
from app.config import settings
from app.db import Base, get_session
from app.main import app


@pytest.fixture
def image_pdf() -> bytes:
    """A one-page PDF that is only an image: valid, but with no text layer."""
    buffer = io.BytesIO()
    PIL.Image.new("RGB", (200, 100), "white").save(buffer, format="PDF")
    return buffer.getvalue()


@pytest.fixture
def locked_pdf(image_pdf: bytes) -> bytes:
    """The image PDF, locked with the password "secret"."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(image_pdf)))
    writer.encrypt("secret", algorithm="AES-256")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(settings.test_database_url)
    try:
        engine.connect().close()
    except OperationalError:
        pytest.skip("Test database not reachable - start it with: docker compose up -d")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


class FakeLaya:
    """Stands in for Laya: answers every transaction with `answers[direction]` and records the calls."""

    def __init__(self) -> None:
        self.answers = {"out": "Other Expense", "in": "Other Income"}
        self.calls: list[TxInput] = []
        self.categorisers: list[tuple[str, str | None]] = []  # (categoriser, api key) per job
        self.fail = False

    def classify(self, tx: TxInput) -> CategoryAnswer:
        if self.fail:
            raise TypeSafeError("Laya is down")
        self.calls.append(tx)
        return CategoryAnswer(self.answers[tx.direction], 0.9)

    @contextmanager
    def factory(self, categoriser: str, api_key: str | None) -> Iterator[CategoryClassifier]:
        self.categorisers.append((categoriser, api_key))
        yield self.classify


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    """Sessions on an emptied test database."""
    with engine.begin() as connection:
        connection.execute(text("truncate statements, rules restart identity cascade"))
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def laya(sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> FakeLaya:
    """Background categorising jobs use the test database and a fake Laya."""
    fake = FakeLaya()
    monkeypatch.setattr(jobs, "session_factory", sessions)
    monkeypatch.setattr(jobs, "classifier_factory", fake.factory)
    monkeypatch.setattr(jobs, "_running", set())
    return fake


@pytest.fixture
def client(sessions: sessionmaker[Session], laya: FakeLaya, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An API client on an emptied test database, with no server-side Jev key and a fake Laya."""
    monkeypatch.setattr(settings, "jev_api_key", "")
    monkeypatch.setattr(settings, "masking_secret", "test-masking-secret")  # never the real key

    def test_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
