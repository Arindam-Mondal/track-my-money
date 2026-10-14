"""Generic bank statement parser (SBI, Axis, ICICI, HDFC, ...) built on pdfplumber.

Instead of hard-coding one bank's layout, it finds the transaction table by its
header row and maps columns by name ("Txn Date", "Narration", "Withdrawal Amt.",
"Deposit", "Closing Balance", ...). Columns it doesn't recognise are kept as
per-transaction metadata; "Key : Value" text above the table and summary rows
(opening/closing balance, totals) become statement metadata.

Usage:
    uv run statement_parser.py path/to/statement.pdf [--json]
"""

import bisect
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

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

def column_role(header):
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


def map_header(cells):
    """Return {role: column index} plus 'extra' columns, or None if not a transaction header."""
    mapping = {"extra": []}
    for i, cell in enumerate(cells):
        role = column_role(cell) if cell else None
        if role and role not in mapping:
            mapping[role] = i
        elif cell:
            mapping["extra"].append((i, cell))
    has_amounts = ("debit" in mapping and "credit" in mapping) or "amount" in mapping
    return mapping if "date" in mapping and has_amounts else None


# ------------------------------------------------------------- row sources

def ruled_table_rows(pdf):
    """Rows from tables drawn with cell borders (most net-banking PDFs)."""
    for page in pdf.pages:
        for table in page.extract_tables():
            yield from table


def text_lines(page, tolerance=3):
    """Group a page's words into lines (top to bottom), each sorted left to right."""
    lines = []
    for w in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if lines and w["top"] - lines[-1][0]["top"] <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def text_layout_rows(pdf, min_gap=8):
    """Rows for borderless tables: column edges come from the header words' positions."""
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
            if map_header(names):
                edges = [(a[-1]["x1"] + b[0]["x0"]) / 2 for a, b in zip(cells, cells[1:])]
                start = i + 1
                yield names
                break
        if edges is None:
            continue
        for line in lines[start:]:
            row = [""] * (len(edges) + 1)
            for w in line:
                col = bisect.bisect(edges, (w["x0"] + w["x1"]) / 2)
                row[col] = f"{row[col]} {w['text']}".strip()
            yield row


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


def build_transactions(rows, metadata):
    transactions = []
    mapping = ncols = None

    for row in rows:
        cells = [clean(c) for c in row]
        header = map_header(cells)
        if header:
            mapping, ncols = header, len(cells)
            continue
        if mapping is None or len(cells) != ncols:
            continue

        def cell(role):
            return cells[mapping[role]] if role in mapping else ""

        tx_date = parse_date(cell("date"))
        particulars = cell("particulars")
        amounts = {r: parse_amount(cell(r)) for r in ("debit", "credit", "amount", "balance") if r in mapping}
        amounts = {r: v for r, v in amounts.items() if v is not None}

        if tx_date is None:
            filled = [i for i, c in enumerate(cells) if c]
            if particulars and amounts:
                # Summary row such as OPENING BALANCE / TRANSACTION TOTAL.
                label = particulars.title()
                for role, value in amounts.items():
                    metadata[label if len(amounts) == 1 else f"{label} {role.title()}"] = value
            elif transactions and filled == [mapping.get("particulars")]:
                # Narration wrapped onto its own line.
                transactions[-1].particulars += " " + particulars
            continue

        balance = amounts.get("balance")
        if "amount" in mapping:
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

        extra = {name: cells[i] for i, name in mapping["extra"] if cells[i]}
        transactions.append(Transaction(tx_date, particulars, debit, credit, balance, extra))

    return transactions


def parse(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        if not any(page.extract_text() for page in pdf.pages):
            raise ValueError(f"{pdf_path} has no text layer (scanned?) - run OCR on it first.")

        metadata = header_metadata(first_page_text)
        transactions = build_transactions(ruled_table_rows(pdf), metadata)
        if not transactions:
            transactions = build_transactions(text_layout_rows(pdf), metadata)

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
    statement = parse(Path(args[0]))
    if "--json" in sys.argv:
        print(to_json(statement))
    else:
        print_report(statement)


if __name__ == "__main__":
    main()
