"""Classify bank statement column headers with Jev (TypeSafe's System One model)."""

import hashlib
import io
import re
import string
from functools import cache
from typing import Literal, get_args

import PIL.Image
from pdfplumber.page import Page
from typesafe_sdk import Choice, ChoiceAnswer, Content, ContentValue, Image, TypeSafeClient


Role = Literal["date", "particulars", "debit", "credit", "amount", "drcr", "balance"]
ROLES: tuple[Role, ...] = get_args(Role)
Label = Role | Literal["other"]
LABELS: tuple[Label, ...] = (*ROLES, "other")
MIN_CONFIDENCE = 0.6  # Below this, Jev is unsure and we ignore the column. Tune on real statements.

ROLE_CRITERIA: dict[str, str] = {
    "date": "The date the transaction happened or was posted. Not the value date.",
    "particulars": "Free-text description of the transaction: narration, remarks, payee, UPI/NEFT details.",
    "debit": "Money going out of the account only: withdrawals or debits.",
    "credit": "Money coming into the account only: deposits or credits.",
    "amount": "A single amount column used for both money in and money out.",
    "drcr": "A marker saying whether the row is a debit or a credit, such as Dr/Cr or D/C.",
    "balance": "The running account balance after the transaction.",
    "other": "Anything else: value date, cheque or reference number, serial number, branch.",
}


# Words that describe a transaction's type, not who or how much; the same on every statement.
KEEP_WORDS = {
    "dr", "cr", "d", "c",
    "upi", "neft", "imps", "rtgs", "ach", "nach", "atm", "pos", "chq",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}
MASK_LENGTH = 24
SEPARATORS = re.compile(f"([\\s{re.escape(string.punctuation)}]+)")
SAMPLE_ROWS = 3
MIN_IMAGE_SIDE, MAX_IMAGE_SIDE = 280, 1568  # TypeSafe rejects images outside this; it doesn't resize
IMAGES_HEADER = {"TypeSafe-Danger-Zone-Images": "true"}  # images are opt-in and experimental


def to_label(answer: ChoiceAnswer) -> Label | None:
    """Jev's answer -> our Label, or None when Jev is too unsure for us to use the column."""
    if answer.confidence < MIN_CONFIDENCE:
        return None
    return next((label for label in LABELS if label == answer.choice), None)


def mask_char(ch: str) -> str:
    if ch.isdigit():
        return "9"
    if ch.isupper():
        return "X"
    return "x"


def mask_word(word: str) -> str:
    if word.lower() in KEEP_WORDS:
        return word
    return "".join(mask_char(ch) for ch in word)


def mask_cell(text: str) -> str:
    """Keep a cell's shape, hide its content: 'UPI/412345/SWIGGY' -> 'UPI/999999/XXXXXX'."""
    parts = SEPARATORS.split(text)
    masked = "".join(part if i % 2 else mask_word(part) for i, part in enumerate(parts))
    return masked[:MASK_LENGTH]


def header_png(page: Page, bbox: tuple[float, float, float, float]) -> bytes:
    """One header cell as a PNG Jev accepts: rendered at 200 dpi, padded with white to the minimum size."""
    rendered = page.crop(bbox).to_image(resolution=200).original.convert("RGB")
    rendered.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    size = (max(rendered.width, MIN_IMAGE_SIDE), max(rendered.height, MIN_IMAGE_SIDE))
    canvas = PIL.Image.new("RGB", size, "white")
    canvas.paste(rendered, ((canvas.width - rendered.width) // 2, (canvas.height - rendered.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def build_state(headers: list[str], samples: list[list[str]], images: list[bytes] | None = None) -> Content:
    """Each column's header, an image of it if given, and up to SAMPLE_ROWS masked values."""
    columns: list[ContentValue] = []
    for i, header in enumerate(headers):
        column: dict[str, ContentValue] = {
            "header": header,
            "samples": [mask_cell(row[i]) for row in samples[:SAMPLE_ROWS] if row[i]],
        }
        if images:
            column["header_image"] = Image(images[i])
        columns.append(column)
    return {"columns": columns}


def build_questions(count: int, with_images: bool = False) -> dict[str, Choice]:
    """One Choice per column; ids aren't sent to Jev, so each question names its column."""
    image_hint = " Its header text is shown in `columns[{i}].header_image`." if with_images else ""
    return {
        f"col_{i}": Choice(
            instructions=(
                f"Which role does the bank statement column `columns[{i}]` play? "
                "Decide from its header and sample values." + image_hint.format(i=i)
            ),
            criteria=ROLE_CRITERIA,
        )
        for i in range(count)
    }


_cache: dict[tuple[tuple[str, ...], str | None], tuple[Label | None, ...]] = {}


def classify_with_jev(
    headers: list[str], samples: list[list[str]], client: TypeSafeClient, images: list[bytes] | None = None
) -> tuple[Label | None, ...]:
    """Each column's label, or None where Jev is unsure; one Jev call per distinct header."""
    key = (tuple(headers), hashlib.sha256(b"".join(images)).hexdigest() if images else None)
    if key not in _cache:
        result = client.system_one(
            build_state(headers, samples, images),
            build_questions(len(headers), with_images=images is not None),
            extra_headers=IMAGES_HEADER if images else None,
        )
        _cache[key] = tuple(to_label(result.choices[f"col_{i}"]) for i in range(len(headers)))
    return _cache[key]


@cache
def jev_client() -> TypeSafeClient:
    """One TypeSafe client per run, created on first use (raises TypeSafeError without a key)."""
    return TypeSafeClient()


def jev_classify(
    headers: list[str], samples: list[list[str]], images: list[bytes] | None = None
) -> tuple[Label | None, ...]:
    """classify_with_jev with the shared client; matches statement_parser's Classifier type."""
    return classify_with_jev(headers, samples, jev_client(), images)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    headers = ["Txn Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    samples = [
        ["01/04/24", "UPI-SWIGGY-swiggy@axisbank-412345", "0000412345", "01/04/24", "450.00", "", "12,300.00"],
        ["02/04/24", "NEFT CR-ACME CORP-SALARY APR", "N123456789", "02/04/24", "", "85,000.00", "97,300.00"],
    ]
    with TypeSafeClient() as client:
        for header, label in zip(headers, classify_with_jev(headers, samples, client)):
            print(f"{header:<18} -> {label}")
