"""Parse an Axis Bank account statement PDF with pdfplumber and print its transactions.

Usage:
    uv run parse_statement.py [path/to/statement.pdf]
"""

import re
import sys
from decimal import Decimal
from pathlib import Path

import pdfplumber

DEFAULT_PDF = Path(__file__).resolve().parent.parent / "sample_statements" / "axis_sample_statement.pdf"
HEADER = ["Tran Date", "Chq No", "Particulars", "Debit", "Credit", "Balance", "Init. Br"]
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def clean(cell):
    """Normalise a table cell: None -> '', collapse wrapped lines into one."""
    return " ".join((cell or "").split())


def to_amount(value):
    return Decimal(value) if value else Decimal("0")


def parse_statement(pdf_path):
    info = {}
    transactions = []
    summary = {}

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        account = re.search(r"Account No\s*:\s*(\d+)", first_page_text)
        period = re.search(r"From\s*:\s*([\d-]+)\s*To\s*:\s*([\d-]+)", first_page_text)
        if account:
            info["account_no"] = account.group(1)
        if period:
            info["period"] = f"{period.group(1)} to {period.group(2)}"

        for page in pdf.pages:
            for table in page.extract_tables():
                # Only the 7-column transaction table matters; skip others (e.g. invoices).
                if not table or len(table[0]) != len(HEADER):
                    continue
                for raw in table:
                    row = [clean(c) for c in raw]
                    date, chq, particulars, debit, credit, balance, branch = row

                    if particulars == "OPENING BALANCE":
                        summary["opening"] = to_amount(balance)
                    elif particulars == "CLOSING BALANCE":
                        summary["closing"] = to_amount(balance)
                    elif particulars == "TRANSACTION TOTAL":
                        summary["total_debit"] = to_amount(debit)
                        summary["total_credit"] = to_amount(credit)
                    elif DATE_RE.match(date):
                        transactions.append({
                            "date": date,
                            "chq_no": chq,
                            "particulars": particulars,
                            "debit": to_amount(debit),
                            "credit": to_amount(credit),
                            "balance": to_amount(balance),
                            "branch": branch,
                        })
                    # Anything else is a repeated header row.

    return info, transactions, summary


def fmt(amount):
    return f"{amount:,.2f}" if amount else ""


def print_report(info, transactions, summary):
    print("Account No :", info.get("account_no", "?"))
    print("Period     :", info.get("period", "?"))
    print()

    line = f"{'Date':<10}  {'Chq No':<7}  {'Particulars':<45}  {'Debit':>12}  {'Credit':>12}  {'Balance':>14}  {'Br':>4}"
    print(line)
    print("-" * len(line))
    for t in transactions:
        print(
            f"{t['date']:<10}  {t['chq_no']:<7}  {t['particulars'][:45]:<45}  "
            f"{fmt(t['debit']):>12}  {fmt(t['credit']):>12}  {fmt(t['balance']):>14}  {t['branch']:>4}"
        )
    print("-" * len(line))

    total_debit = sum(t["debit"] for t in transactions)
    total_credit = sum(t["credit"] for t in transactions)
    print(f"Transactions   : {len(transactions)}")
    print(f"Opening balance: {fmt(summary.get('opening', Decimal(0)))}")
    print(f"Total debit    : {fmt(total_debit)}  (statement says {fmt(summary.get('total_debit', Decimal(0)))})")
    print(f"Total credit   : {fmt(total_credit)}  (statement says {fmt(summary.get('total_credit', Decimal(0)))})")
    print(f"Closing balance: {fmt(summary.get('closing', Decimal(0)))}")

    if "opening" in summary and "closing" in summary:
        expected = summary["opening"] - total_debit + total_credit
        status = "OK" if expected == summary["closing"] else f"MISMATCH (computed {fmt(expected)})"
        print(f"Reconciliation : {status}")


def main():
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    info, transactions, summary = parse_statement(pdf_path)
    print_report(info, transactions, summary)


if __name__ == "__main__":
    main()
