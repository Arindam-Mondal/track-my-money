"""Generic bank statement parser (SBI, Axis, ICICI, HDFC, ...) built on pdfplumber.

Instead of hard-coding one bank's layout, it finds the transaction table by its
header row and asks Jev (TypeSafe's model, see header_classifier.py) what each column
holds, from the header names plus masked sample values. When a header's names aren't
stored as text (SBI), Jev reads images of the header cells instead. If Jev is
unavailable, keyword rules map the columns by name ("Txn Date", "Withdrawal Amt.", ...).
Other columns are kept as per-transaction metadata; "Key : Value" text above the table
and summary rows (opening/closing balance, totals) become statement metadata.

A PDF is read from a path or from bytes (an upload). A locked one raises PasswordRequired
or WrongPassword; the CLI then asks for the password.

Usage (from backend/; JEV_API_KEY is read from backend/.env):
    uv run python -m app.parsing.statement_parser path/to/statement.pdf [--json] [--rules-only]

    --rules-only (or HEADER_RULES_ONLY=1) skips Jev and uses the keyword rules only.
"""

import bisect
import io
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from getpass import getpass
from pathlib import Path
from typing import Literal

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException
from typesafe_sdk import TypeSafeError

from app.jev import jev_key
from app.parsing.header_classifier import Classifier, Label, Role, header_png, jev_classifier

logger = logging.getLogger(__name__)


DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %b %y", "%d %B %Y",
    "%Y-%m-%d", "%b %d, %Y",
]
DATE_PATTERN = r"\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ]\d{2,4}"

# IFSC prefix -> bank name; the most reliable way to tell banks apart.
IFSC_BANKS = {
    "SBIN": "State Bank of India", "UTIB": "Axis Bank", "ICIC": "ICICI Bank",
    "HDFC": "HDFC Bank", "KKBK": "Kotak Mahindra Bank", "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda", "CNRB": "Canara Bank", "UBIN": "Union Bank of India",
    "IDIB": "Indian Bank", "YESB": "Yes Bank", "IDFB": "IDFC First Bank",
    "INDB": "IndusInd Bank", "FDRL": "Federal Bank", "BKID": "Bank of India",
}

KNOWN_FIELDS = {
    "Account Number": r"(?:account|a/c)\s*(?:no|number|num)?\.?\s*:?-?\s*([0-9Xx*]{6,20})",
    "IFSC": r"\b([A-Z]{4}0[A-Z0-9]{6})\b",
    "Customer ID": r"(?:customer|cust|cif)\s*(?:id|no|number)\.?\s*:?-?\s*([A-Za-z0-9]+)",
}
PERIOD_RE = re.compile(
    rf"(?:from|period)\D{{0,15}}?({DATE_PATTERN})\s*(?:to|-|till)\s*:?\s*({DATE_PATTERN})", re.I
)
# "Key : Value" pairs; a value runs until the next "Some Key :" on the same line.
KEY_VALUE_RE = re.compile(
    r"(?P<key>[A-Za-z][\w .&/()'-]*?)\s*:-?\s*(?P<value>.*?)(?=\s+\S+(?:\s\S+){0,3}\s*:|$)"
)


@dataclass
class HeaderMap:
    columns: dict[Role, int]          # role -> column index
    extra: list[tuple[int, str]]      # (column index, header name) kept as metadata


class PasswordRequired(Exception):
    """The PDF is locked and no password was given."""


class WrongPassword(Exception):
    """The PDF is locked and the given password doesn't open it."""


class NoTextLayer(ValueError):
    """The PDF has no text to read (a scan); it needs OCR first."""


# Renders a table's header cells as PNGs, only when asked (rendering is slow).
HeaderImages = Callable[[], list[bytes]]
HeaderSource = Literal["rules", "rules (no Jev key)", "jev", "jev (image)", "rules (fallback)"]


@dataclass
class Transaction:
    date: date
    particulars: str
    debit: Decimal
    credit: Decimal
    balance: Decimal | None
    metadata: dict = field(default_factory=dict)


@dataclass
class Statement:
    metadata: dict
    transactions: list[Transaction]


# ---------------------------------------------------------------- cell parsing

def clean(cell):
    return " ".join((cell or "").split())


def parse_date(text):
    text = clean(text)
    if not text:
        return None
    candidates = [text, " ".join(text.split()[:3]), text.split()[0]]
    for candidate in candidates:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def parse_amount(text):
    """'1,234.50' -> 1234.50; '1,234.50 Dr', '(1,234.50)' and '-1234.50' -> negative."""
    text = clean(text)
    text = re.sub(r"(?i)(₹|inr|rs\.?)", "", text).replace(",", "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    suffix = re.search(r"(?i)\s*\b(cr|dr)\.?$", text)
    if suffix:
        negative = suffix.group(1).lower() == "dr"
        text = text[: suffix.start()]
    try:
        value = Decimal(text.strip("()").strip())
    except InvalidOperation:
        return None
    return -abs(value) if negative else value


# ------------------------------------------------------------- header mapping

def column_role(header: str) -> Role | None:
    h = re.sub(r"[^a-z/ ]", "", header.lower()).strip()
    if "balance" in h:
        return "balance"
    if "withdraw" in h or "debit" in h or h in ("dr", "debits"):
        return "debit"
    if "deposit" in h or "credit" in h or h in ("cr", "credits"):
        return "credit"
    if h in ("dr/cr", "cr/dr", "dr / cr", "type", "txn type"):
        return "drcr"
    if "amount" in h or h == "amt":
        return "amount"
    if any(k in h for k in ("particular", "description", "narration", "detail", "remark")):
        return "particulars"
    if "date" in h and "value" not in h:
        return "date"
    return None


def rule_labels(cells: list[str]) -> list[Label | None]:
    """Keyword-rule label per header cell: its role, "other" if unrecognised, None if empty."""
    return [(column_role(cell) or "other") if cell else None for cell in cells]


def map_header(cells: list[str], labels: list[Label | None]) -> HeaderMap | None:
    """Which column holds each role, or None if this row isn't a transaction header."""
    columns: dict[Role, int] = {}
    extra: list[tuple[int, str]] = []
    for i, (cell, label) in enumerate(zip(cells, labels)):
        if label is None:
            continue
        if label != "other" and label not in columns:
            columns[label] = i
        else:
            extra.append((i, cell or f"Column {i + 1}"))
    has_amounts = ("debit" in columns and "credit" in columns) or "amount" in columns
    return HeaderMap(columns, extra) if "date" in columns and has_amounts else None


def looks_like_header(cells: list[str]) -> bool:
    """Cheap check before asking Jev: 3+ filled cells, none a date or amount, mostly words."""
    filled = [c for c in cells if c]
    if len(filled) < 3:
        return False
    if any(len(c) > 40 for c in filled):
        return False
    if any(parse_date(c) is not None or parse_amount(c) is not None for c in filled):
        return False
    return sum(any(ch.isalpha() for ch in c) for c in filled) * 2 >= len(filled)


def looks_like_unreadable_header(cells: list[str]) -> bool:
    """A header whose names aren't stored as text: mostly empty cells and no data in it."""
    empty = sum(1 for c in cells if not c)
    if len(cells) < 3 or empty * 2 <= len(cells):
        return False
    return not any(parse_date(c) is not None or parse_amount(c) is not None for c in cells if c)


def has_dated_row(rows: list[list[str]]) -> bool:
    """Whether any row has a date in it; a transaction header is followed by dated rows."""
    return any(parse_date(c) is not None for row in rows for c in row)


def ask_jev(
    classify: Classifier, cells: list[str], samples: list[list[str]], images: list[bytes] | None = None
) -> HeaderMap | None:
    """Jev's mapping for this header row, or None (with the reason on stderr) if it's unusable."""
    try:
        header = map_header(cells, list(classify(cells, samples, images)))
    except TypeSafeError as e:
        logger.warning("Jev unavailable, using rules: %s", e)
        return None
    if header is None:
        logger.warning("Jev's labels don't form a usable header, using rules (%d columns)", len(cells))
    return header


def detect_header(
    cells: list[str],
    samples: list[list[str]],
    classify: Classifier | None,
    render_images: HeaderImages | None = None,
) -> tuple[HeaderMap | None, HeaderSource]:
    """Map a header row with Jev when possible (from images if its text is unreadable), else the rules.

    Jev is only asked about rows followed by dated rows, so text blocks (addresses, disclaimers,
    invoices) never reach it.
    """
    rules = map_header(cells, rule_labels(cells))
    if classify is None:
        return rules, "rules (no Jev key)"
    if not has_dated_row(samples):
        return rules, "rules"
    if looks_like_header(cells):
        header = ask_jev(classify, cells, samples)
        return (header, "jev") if header else (rules, "rules (fallback)")
    if rules is None and render_images is not None and looks_like_unreadable_header(cells):
        header = ask_jev(classify, cells, samples, render_images())
        return (header, "jev (image)") if header else (rules, "rules (fallback)")
    return rules, "rules"


# ------------------------------------------------------------- row sources

def header_renderer(page, cells) -> HeaderImages | None:
    """A function that renders each header cell as a PNG, or None if a cell has no box (merged)."""
    boxes = [cell for cell in cells if cell is not None]
    if len(boxes) != len(cells):
        return None
    return lambda: [header_png(page, box) for box in boxes]


def ruled_table_rows(pdf):
    """(row, header renderer) pairs from tables drawn with cell borders (most net-banking PDFs).

    Only each table's first row gets a renderer; it may be a header whose names aren't text.
    """
    for page in pdf.pages:
        for table in page.find_tables():
            render = header_renderer(page, table.rows[0].cells)
            for i, row in enumerate(table.extract()):
                yield row, render if i == 0 else None


def text_lines(page, tolerance=3):
    """Group a page's words into lines (top to bottom), each sorted left to right."""
    lines = []
    for w in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if lines and w["top"] - lines[-1][0]["top"] <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def split_line(line, edges):
    """Place a line's words into columns by their horizontal centre."""
    row = [""] * (len(edges) + 1)
    for w in line:
        col = bisect.bisect(edges, (w["x0"] + w["x1"]) / 2)
        row[col] = f"{row[col]} {w['text']}".strip()
    return row


def text_layout_rows(pdf, classify: Classifier | None = None, min_gap=8):
    """(row, None) pairs for borderless tables: column edges come from the header words' positions.

    Jev is only asked about lines where the keyword rules already recognise 2+ columns, so the
    account details above the table are never sent.
    """
    edges = None
    for page in pdf.pages:
        lines = text_lines(page)
        start = 0
        for i, line in enumerate(lines):
            cells = []
            for w in line:
                if cells and w["x0"] - cells[-1][-1]["x1"] < min_gap:
                    cells[-1].append(w)
                else:
                    cells.append([w])
            names = [" ".join(w["text"] for w in c) for c in cells]
            line_edges = [(a[-1]["x1"] + b[0]["x0"]) / 2 for a, b in zip(cells, cells[1:])]
            known = sum(label not in (None, "other") for label in rule_labels(names))
            samples = [split_line(next_line, line_edges) for next_line in lines[i + 1 : i + 4]]
            header, _ = detect_header(names, samples, classify if known >= 2 else None)
            if header:
                edges = line_edges
                start = i + 1
                yield names, None
                break
        if edges is None:
            continue
        for line in lines[start:]:
            yield split_line(line, edges), None


# ------------------------------------------------------------- statement parsing

def header_metadata(first_page_text):
    """Key/value metadata from the text above the transaction table."""
    lines = first_page_text.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if "date" in low and "balance" in low:
            lines = lines[:i]
            break
    text = "\n".join(lines)

    metadata = {}
    ifsc = re.search(KNOWN_FIELDS["IFSC"], text)
    bank = IFSC_BANKS.get(ifsc.group(1)[:4]) if ifsc else None
    if not bank:
        bank = next((name for name in IFSC_BANKS.values() if name.lower() in text.lower()), None)
    if bank:
        metadata["Bank"] = bank
    for key, pattern in KNOWN_FIELDS.items():
        match = re.search(pattern, text, re.I)
        if match:
            metadata[key] = match.group(1)
    period = PERIOD_RE.search(text)
    if period:
        metadata["Statement Period"] = f"{period.group(1)} to {period.group(2)}"

    for line in lines:
        for match in KEY_VALUE_RE.finditer(line):
            key, value = clean(match["key"]), clean(match["value"])
            if value.endswith(")") and "(" not in value:
                value = value[:-1]
            # Skip pairs already captured above (e.g. "NASHIK Customer ID" next to an address).
            if value and key not in metadata and not any(value in str(v) for v in metadata.values()):
                metadata[key] = value
    return metadata


def build_transactions(rows, metadata, classify: Classifier | None = None):
    transactions = []
    mapping = ncols = None
    rows = [([clean(c) for c in row], render) for row, render in rows]

    for i, (cells, render) in enumerate(rows):
        samples = [r for r, _ in rows[i + 1 : i + 4] if len(r) == len(cells)]
        header, source = detect_header(cells, samples, classify, render)
        if header:
            mapping, ncols = header, len(cells)
            metadata["Header Mapping"] = source
            continue
        if mapping is None or len(cells) != ncols:
            continue

        columns = mapping.columns

        def cell(role):
            return cells[columns[role]] if role in columns else ""

        tx_date = parse_date(cell("date"))
        particulars = cell("particulars")
        amounts = {r: parse_amount(cell(r)) for r in ("debit", "credit", "amount", "balance") if r in columns}
        amounts = {r: v for r, v in amounts.items() if v is not None}

        if tx_date is None:
            filled = [i for i, c in enumerate(cells) if c]
            if particulars and amounts:
                # Summary row such as OPENING BALANCE / TRANSACTION TOTAL.
                label = particulars.title()
                for role, value in amounts.items():
                    metadata[label if len(amounts) == 1 else f"{label} {role.title()}"] = value
            elif transactions and filled == [columns.get("particulars")]:
                # Narration wrapped onto its own line.
                transactions[-1].particulars += " " + particulars
            continue

        balance = amounts.get("balance")
        if "amount" in columns:
            amount = amounts.get("amount", Decimal(0))
            direction = cell("drcr").lower()[:2] or None
            if direction not in ("dr", "cr"):
                direction = "dr" if amount < 0 else None
            if direction is None and balance is not None and transactions and transactions[-1].balance is not None:
                direction = "cr" if balance > transactions[-1].balance else "dr"
            debit = abs(amount) if direction == "dr" else Decimal(0)
            credit = abs(amount) if direction != "dr" else Decimal(0)
        else:
            debit = abs(amounts.get("debit", Decimal(0)))
            credit = abs(amounts.get("credit", Decimal(0)))

        extra = {name: cells[i] for i, name in mapping.extra if cells[i]}
        transactions.append(Transaction(tx_date, particulars, debit, credit, balance, extra))

    return transactions


def open_pdf(source: Path | bytes, password: str | None = None):
    """Open a PDF from a path or bytes; raises PasswordRequired / WrongPassword if it's locked."""
    try:
        return pdfplumber.open(io.BytesIO(source) if isinstance(source, bytes) else source, password=password)
    except PdfminerException as e:
        if not isinstance(e.args[0], PDFPasswordIncorrect):
            raise
        raise (WrongPassword() if password else PasswordRequired()) from None


def parse(source: Path | bytes, password: str | None = None, classify: Classifier | None = None):
    """Parse a statement; `classify` asks Jev about headers (None: keyword rules only)."""
    with open_pdf(source, password or None) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        if not any(page.extract_text() for page in pdf.pages):
            raise NoTextLayer("The PDF has no text layer (scanned?) - run OCR on it first.")

        metadata = header_metadata(first_page_text)
        transactions = build_transactions(ruled_table_rows(pdf), metadata, classify)
        if not transactions:
            transactions = build_transactions(text_layout_rows(pdf, classify), metadata, classify)

    return Statement(metadata, transactions)


# ------------------------------------------------------------- verification

def balance_mismatches(transactions, opening=None):
    """Count rows whose balance != previous balance - debit + credit."""
    mismatches, previous = 0, opening
    for t in transactions:
        if t.balance is None:
            continue
        if previous is not None and previous - t.debit + t.credit != t.balance:
            mismatches += 1
        previous = t.balance
    return mismatches


def check_balances(statement):
    if not statement.transactions:
        return "no transactions found - the transaction table wasn't recognised"
    opening = next(
        (parse_amount(str(v)) for k, v in statement.metadata.items()
         if any(label in k.lower() for label in ("opening balance", "brought forward"))),
        None,
    )
    forward = balance_mismatches(statement.transactions, opening)
    if forward == 0:
        return "OK (oldest first)"
    if balance_mismatches(statement.transactions[::-1]) == 0:
        return "OK (newest first)"
    return f"{forward} row(s) don't add up - check the parsed data"


# ------------------------------------------------------------- output

def fmt(amount):
    return f"{amount:,.2f}" if amount else ""


def print_report(statement):
    print("Metadata")
    for key, value in statement.metadata.items():
        print(f"  {key:<28} {value}")
    print()

    line = f"{'Date':<10}  {'Particulars':<45}  {'Debit':>12}  {'Credit':>12}  {'Balance':>14}  Other"
    print(line)
    print("-" * len(line))
    for t in statement.transactions:
        other = ", ".join(f"{k}={v}" for k, v in t.metadata.items())
        balance = fmt(t.balance) if t.balance is not None else ""
        print(
            f"{t.date.isoformat():<10}  {t.particulars[:45]:<45}  "
            f"{fmt(t.debit):>12}  {fmt(t.credit):>12}  {balance:>14}  {other}"
        )
    print("-" * len(line))
    print(f"Transactions : {len(statement.transactions)}")
    print(f"Total debit  : {fmt(sum(t.debit for t in statement.transactions))}")
    print(f"Total credit : {fmt(sum(t.credit for t in statement.transactions))}")
    print(f"Balance check: {check_balances(statement)}")


def to_json(statement):
    def default(value):
        if isinstance(value, (date, Decimal)):
            return str(value)
        raise TypeError(type(value))
    return json.dumps(asdict(statement), default=default, indent=2)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    path = Path(args[0])
    rules_only = "--rules-only" in sys.argv or os.environ.get("HEADER_RULES_ONLY") == "1"
    with jev_classifier(None if rules_only else jev_key()) as classify:
        try:
            statement = parse(path, classify=classify)
        except PasswordRequired:
            try:
                statement = parse(path, getpass(f"Password for {path.name}: "), classify)
            except WrongPassword:
                sys.exit(f"Wrong password for {path.name}")

    if "--json" in sys.argv:
        print(to_json(statement))
    else:
        print_report(statement)


if __name__ == "__main__":
    main()
