"""Masking keeps what decides the category and hides what identifies someone."""

import re

import pytest

from app.masking.masker import mask_narration

SECRET = b"test-secret"


def mask(text: str) -> str:
    return mask_narration(text, SECRET)


@pytest.mark.parametrize("narration, person", [
    ("UPI/P2A/412345678901/RAHUL SHARMA/rahul.12@okaxis/rent oct", "RAHUL SHARMA"),
    ("TO TRANSFER-UPI/DR/621665601900/PRIYA NAIR/HDFC/priya7@okhdfcbank/Payment", "PRIYA NAIR"),
    ("BY TRANSFER-UPI/CR/621665601900/ANAND IYER/SBI/anand@oksbi/Payment", "ANAND IYER"),
    ("IMPS/P2A/123040631118/ARINDAM NAIR/RENT", "ARINDAM NAIR"),
    ("NEFT Dr-UTIB0281200-ARJUN IYER-HOUSE RENT JUL", "ARJUN IYER"),
    ("BY TRANSFER-NEFT*HDFC0001234*HDFCN123456789*ROSE KING", "ROSE KING"),
    ("BRN-CLG-CHQ PAID TO Mrs MAYA VISHNU/BANK OF MAHARASHTRA", "MAYA VISHNU"),
    ("UPI/MOHAN DAS/mohan@ybl/Payment/AXIS", "MOHAN DAS"),
    ("DEP TFR 1234567890 SUNIL KUMAR", "SUNIL KUMAR"),
])
def test_people_in_known_positions_become_person_tokens(narration, person):
    masked = mask(narration)
    assert re.search(r"\[PERSON_[0-9A-F]{4}\]", masked)
    for word in person.split():
        assert word not in masked


def test_the_same_person_gets_the_same_token():
    a = mask("UPI/P2A/111111111111/RAHUL SHARMA/x@okaxis/Payment")
    b = mask("IMPS/P2A/222222222222/RAHULSHARMA/HDFCBANK/IMPStran")
    token = re.search(r"\[PERSON_[0-9A-F]{4}\]", a).group(0)
    assert token in b
    assert token != re.search(r"\[PERSON_[0-9A-F]{4}\]", mask_narration("UPI/P2A/1/RAHUL SHARMA/x", b"other")).group(0)


@pytest.mark.parametrize("narration, expected", [
    ("MY PAN ABCPE1234F", "MY PAN [PAN]"),
    ("MOB +91 9876543210", "MOB [PHONE]"),
    ("mail rahul@gmail.com", "mail [EMAIL]"),
    ("AADHAAR 1234 5678 9012", "AADHAAR [AADHAAR]"),
    ("GST 27AABTA3323M1ZT", "GST [GSTIN]"),
    ("NEFT-UTIB0281200-X", "NEFT-[IFSC:UTIB]-X"),
    ("CC PAYMENT/HDFC CREDIT CARD/XX1234", "CC PAYMENT/HDFC CREDIT CARD/[ACCOUNT]"),
    ("ATW-374846XXXXXX8255-15765421-KOLKATA", "ATW-[ACCOUNT]-[REF]-[CITY]"),
    ("Int.Pd:01-04-2026 to 30-06-2026", "Int.Pd:[DATE] to [DATE]"),
    ("ATM WDL/NFS/CASH WITHDRAWAL/S1ANMU12", "ATM WDL/NFS/CASH WITHDRAWAL/[REF]"),
    ("UPI/P2M/412345678901/rahul.12@okaxis", "UPI/P2M/[REF]/[UPI_ID]@okaxis"),
])
def test_identifiers_become_typed_placeholders(narration, expected):
    assert mask(narration) == expected


@pytest.mark.parametrize("narration", [
    "UPI/P2M/998877665544/SWIGGY/swiggy@icici/Payment",
    "NACH-MUT-DR/BSE STAR MF/SIP 4567",
    "BURGER KING BANGALORE IN",
    "UPI/77889900/IRCTC/irctc@sbi",
    "NEFT/PYTM230935558493/PAYTM PAYMENTS SERVICES LIM",
    "IMPS-2353139652-OLA-ICICI",
])
def test_brands_and_keywords_are_kept(narration):
    masked = mask(narration)
    for brand in ("SWIGGY", "swiggy@icici", "BSE STAR MF", "SIP", "BURGER KING", "IRCTC", "PAYTM", "OLA", "NACH"):
        if brand in narration:
            assert brand in masked, (brand, masked)


def test_business_words_kept_names_masked():
    assert mask("POS 458024 SRI LAKSHMI ENTERPRISES NASHIK").startswith("POS [REF] SRI [NAME_")
    assert mask("POS 458024 SRI LAKSHMI ENTERPRISES NASHIK").endswith(" ENTERPRISES [CITY]")
    assert mask("CITY HOSPITAL PVT LTD KIDS SPORTS STORE") == "CITY HOSPITAL PVT LTD KIDS SPORTS STORE"
    assert "ROSE" not in mask("PAYMENT TO ROSE")
    assert "ANAND" not in mask("PAYMENT TO ANAND")
    assert mask("dinner split rent oct") == "dinner split rent oct"


def test_initials_go_with_the_name():
    assert mask("PAID TO R. K. SHARMA/SBI").startswith("PAID TO [PERSON_")
    assert mask("POS 1234 A B C STORES PUNE") == "POS [REF] A B C STORES [CITY]"


@pytest.mark.parametrize("narration", [
    "UPI/P2A/412345678901/RAHUL SHARMA/rahul.12@okaxis/rent oct",
    "29325130CARDAXIS CC 057578",
    "RTGS/SK/UTIBR52023040600372162/1/ASHOKA /BANK O",
    "NEFT/CHASH12345678/Salary for OCT 2026 Infosys/ICICI BANK",
])
def test_no_digits_survive_outside_tokens(narration):
    outside_tokens = re.sub(r"\[[A-Z_:0-9A-F]+\]", "", mask(narration)).replace("P2A", "")
    assert not re.search(r"[0-8]", outside_tokens)  # any digit left is a masking 9


def test_masking_key_is_kept_in_its_file(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """In Docker the key lives on a volume (MASKING_SECRET_FILE): made once, then reused."""
    from app import masking
    from app.config import settings

    key_file = tmp_path / "state" / "masking_secret"
    monkeypatch.setattr(settings, "masking_secret", "")
    monkeypatch.setattr(settings, "masking_secret_file", str(key_file))
    first = masking.masking_secret()
    assert key_file.read_text().strip() == first.decode()

    monkeypatch.setattr(settings, "masking_secret", "")  # a restarted container
    assert masking.masking_secret() == first
