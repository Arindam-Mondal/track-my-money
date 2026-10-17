"""Shared fixtures: generated PDFs, and an API client on the trackmymoney_test database."""

import io
from collections.abc import Iterator

import PIL.Image
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

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


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An API client on an emptied test database, with no server-side Jev key."""
    with engine.begin() as connection:
        connection.execute(text("truncate statements restart identity cascade"))
    monkeypatch.setattr(settings, "typesafe_api_key", "")
    sessions = sessionmaker(engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
