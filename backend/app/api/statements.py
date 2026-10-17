"""Upload, list, read and delete statements.

One upload request per PDF. A locked PDF is answered with 422 `password_required`; the client
sends the same file again with its password. PDFs, passwords and Jev keys are never stored.
"""

import hashlib
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Statement, Transaction
from app.parsing import statement_parser
from app.parsing.header_classifier import jev_classifier
from app.schemas import Health, StatementOut, TransactionOut, UploadError, UploadErrorCode

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {"model": UploadError, "description": "This file was already imported"},
    413: {"model": UploadError, "description": "File too large"},
    422: {"model": UploadError, "description": "Locked, wrong password, unreadable, or no transactions"},
}


def upload_error(status: int, code: UploadErrorCode, message: str) -> HTTPException:
    return HTTPException(status, detail=UploadError(code=code, message=message).model_dump())


def jsonable(metadata: dict[str, Any]) -> dict[str, Any]:
    """Parsed metadata for a JSONB column: amounts (Decimal) become strings."""
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in metadata.items()}


def to_out(statement: Statement, transaction_count: int) -> StatementOut:
    return StatementOut(
        id=statement.id,
        filename=statement.filename,
        bank=statement.bank,
        account_number=statement.account_number,
        period=statement.period,
        header_mapping=statement.header_mapping,
        balance_check=statement.balance_check,
        uploaded_at=statement.uploaded_at,
        transaction_count=transaction_count,
    )


@router.get("/health")
def health(session: SessionDep) -> Health:
    session.execute(text("select 1"))
    return Health(database="ok", server_jev_key=bool(settings.typesafe_api_key.strip()))


@router.post("/statements", status_code=201, responses=UPLOAD_ERRORS)
def upload_statement(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="A bank statement PDF")],
    password: Annotated[str | None, Form(description="Password, if the PDF is locked")] = None,
    typesafe_key: Annotated[str | None, Header(alias="X-TypeSafe-Key", description="The user's Jev key")] = None,
) -> StatementOut:
    # A plain `def`: FastAPI runs it in a worker thread, as parsing and Jev calls block.
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise upload_error(413, "too_large", f"Files can be at most {settings.max_upload_mb} MB.")
    if b"%PDF" not in data[:1024]:
        raise upload_error(422, "not_a_pdf", "This file isn't a PDF.")

    sha256 = hashlib.sha256(data).hexdigest()
    if session.scalar(select(Statement.id).where(Statement.file_sha256 == sha256)) is not None:
        raise upload_error(409, "duplicate", "This statement was already imported.")

    with jev_classifier(typesafe_key or settings.typesafe_api_key) as classify:
        try:
            parsed = statement_parser.parse(data, password, classify)
        except statement_parser.PasswordRequired:
            raise upload_error(422, "password_required", "This PDF is locked. Enter its password.") from None
        except statement_parser.WrongPassword:
            raise upload_error(422, "wrong_password", "That password doesn't open this PDF.") from None
        except statement_parser.NoTextLayer as error:
            raise upload_error(422, "no_text_layer", str(error)) from None
        except (PdfminerException, PDFSyntaxError):
            raise upload_error(422, "not_a_pdf", "This PDF couldn't be read.") from None

    if not parsed.transactions:
        raise upload_error(422, "no_transactions", "No transaction table was recognised in this statement.")

    metadata = parsed.metadata
    statement = Statement(
        filename=file.filename or "statement.pdf",
        file_sha256=sha256,
        bank=metadata.get("Bank"),
        account_number=metadata.get("Account Number"),
        period=metadata.get("Statement Period"),
        header_mapping=metadata.get("Header Mapping"),
        balance_check=statement_parser.check_balances(parsed),
        metadata_=jsonable(metadata),
        transactions=[
            Transaction(
                row_index=i,
                date=t.date,
                particulars=t.particulars,
                debit=t.debit,
                credit=t.credit,
                balance=t.balance,
                extra=t.metadata,
            )
            for i, t in enumerate(parsed.transactions)
        ],
    )
    session.add(statement)
    try:
        session.commit()
    except IntegrityError:  # the same file finished uploading in parallel
        session.rollback()
        raise upload_error(409, "duplicate", "This statement was already imported.") from None
    return to_out(statement, len(parsed.transactions))


@router.get("/statements")
def list_statements(session: SessionDep) -> list[StatementOut]:
    rows = session.execute(
        select(Statement, func.count(Transaction.id))
        .outerjoin(Transaction)
        .group_by(Statement.id)
        .order_by(Statement.uploaded_at.desc(), Statement.id.desc())
    ).all()
    return [to_out(statement, count) for statement, count in rows]


@router.get("/statements/{statement_id}/transactions")
def list_transactions(statement_id: int, session: SessionDep) -> list[TransactionOut]:
    if session.get(Statement, statement_id) is None:
        raise HTTPException(404, "Statement not found")
    transactions = session.scalars(
        select(Transaction).where(Transaction.statement_id == statement_id).order_by(Transaction.row_index)
    )
    return [TransactionOut.model_validate(t) for t in transactions]


@router.delete("/statements/{statement_id}", status_code=204)
def delete_statement(statement_id: int, session: SessionDep) -> Response:
    statement = session.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(404, "Statement not found")
    session.delete(statement)
    session.commit()
    return Response(status_code=204)
