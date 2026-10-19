"""Generate synthetic, labelled Indian bank narrations to fine-tune Laya on our categories.

Every narration is fictional: public brand names plus random reference numbers, UPI handles
and person names. No real transaction data is used, so the output can be uploaded to Kaggle.

Merchant lists and several narration shapes are adapted from Sumeetgpt's
"indian-transaction-categorization-synthetic" generator (MIT License, see NOTICE.md), extended
with our 32 categories, both directions, and the Axis/SBI narration formats seen in this app.

Each row is in the format `laya-train` reads, built with the app's own `build_state` and
`build_question`, so the model is trained on exactly what the app asks:
    {"state": {...}, "questions": {"category": {...}}, "expected": {"category": "<label>"}}

Usage (from backend/):
    uv run python training/generate_dataset.py                       # round 1: ~150 per category
    uv run python training/generate_dataset.py --round 2 --focus "Food & Dining,Groceries" \\
        --extra 400 --mix-previous 0.3                               # a targeted follow-up round
"""

import argparse
import json
import random
import string
import sys
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.categorising.categories import Direction, model_categories  # noqa: E402
from app.categorising.laya import TxInput, build_question, build_state  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
QUESTION_ID = "category"

# ------------------------------------------------------------------------------ random parts

FIRST = ["Aarav", "Vivaan", "Aditya", "Rohan", "Arjun", "Rahul", "Priya", "Ananya", "Diya", "Kavya", "Sneha",
         "Pooja", "Neha", "Anjali", "Vikram", "Suresh", "Ramesh", "Lakshmi", "Meera", "Farhan", "Imran", "Joseph",
         "Gurpreet", "Harpreet", "Sanjay", "Deepak", "Nisha", "Rekha", "Arindam", "Sourav", "Ishita", "Karthik"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Shah", "Gupta", "Singh", "Kumar", "Das", "Mondal",
        "Banerjee", "Chatterjee", "Khan", "Fernandes", "Menon", "Pillai", "Joshi", "Kulkarni", "Rao", "Ghosh"]
BANKS = ["ICICI", "HDFC", "AXIS", "SBI", "YES BANK", "KOTAK", "IDFC", "PNB", "BOB", "CANARA"]
CITIES = ["BANGALORE", "MUMBAI", "DELHI", "PUNE", "CHENNAI", "HYDERABAD", "GURGAON", "KOLKATA", "NASHIK", "DURGAPUR"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
HANDLES = ["okicici", "oksbi", "okaxis", "okhdfcbank", "ybl", "paytm", "ibl", "axl", "apl"]
IFSC_PREFIX = ["HDFC", "ICIC", "UTIB", "SBIN", "KKBK", "YESB", "PUNB", "BARB"]


def name() -> str:
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def ref(n: int = 12) -> str:
    return "".join(random.choices(string.digits, k=n))


def vpa(person: str | None = None) -> str:
    base = (person or random.choice(FIRST)).split()[0].lower()
    return f"{base}{random.randint(1, 999)}@{random.choice(HANDLES)}"


def merchant_vpa(m: str) -> str:
    return f"{''.join(c for c in m.lower() if c.isalnum())[:12]}@{random.choice(HANDLES)}"


def ifsc() -> str:
    return f"{random.choice(IFSC_PREFIX)}0{ref(6)}"


def acct() -> str:
    return f"XX{ref(4)}"


def month_year() -> str:
    return f"{random.choice(MONTHS)} {random.randint(2024, 2026)}"


def date() -> str:
    return f"{random.randint(1, 28):02d}-{random.randint(1, 12):02d}-{random.randint(2024, 2026)}"


# ------------------------------------------------------------------------------ narration shapes

Template = Callable[[str], str]

# Paying a business: UPI, card and bank-transfer shapes across ICICI/HDFC/Axis/SBI statements.
PURCHASE: list[Template] = [
    lambda m: f"UPI/{m}/{merchant_vpa(m)}/Payment/{random.choice(BANKS)}",
    lambda m: f"UPI/P2M/{ref()}/{m.upper()}/{random.choice(['Pay', 'Payment', 'UPI', 'order'])}",
    lambda m: f"UPI-{m.upper()}-{merchant_vpa(m)}-{random.choice(IFSC_PREFIX)}0000{ref(3)}-{ref(12)}-UPI",
    lambda m: f"TO TRANSFER-UPI/DR/{ref()}/{m.upper()[:20]}/{random.choice(BANKS)}/{merchant_vpa(m)}/Payment",
    lambda m: f"POS {ref(6)} {m.upper()} {random.choice(CITIES)}",
    lambda m: f"POS/{m.upper()}/{random.choice(CITIES)}/{ref(6)}",
    lambda m: f"{m.upper()} {random.choice(CITIES)} IN",
    lambda m: f"BIL/ONL/{ref(9)}/{m.upper()}/{ref(6)}",
    lambda m: f"IMPS-{ref(10)}-{m.upper()}-{random.choice(BANKS)}",
    lambda m: f"ACH/TP ACH {m.upper()} {ref(10)}",
    lambda m: f"{m} Ref#{ref(8)}",
    lambda m: f"{m.upper()}",
]

# Money to or from a person (UPI P2A, IMPS, NEFT, cheque).
def person_out() -> str:
    p = name()
    return random.choice([
        f"UPI/P2A/{ref()}/{p.upper()}/{random.choice(BANKS)}",
        f"UPI/{p.upper()}/{vpa(p)}/{random.choice(['Payment', 'UPI', 'dinner split', 'gift', 'loan return', 'NA'])}/{random.choice(BANKS)}",
        f"TO TRANSFER-UPI/DR/{ref()}/{p.upper()[:20]}/{random.choice(BANKS)}/{vpa(p)}/Payment",
        f"IMPS/P2A/{ref()}/{p.upper().replace(' ', '')}/{random.choice(BANKS)}BANK/IMPStran",
        f"NEFT Dr-{ifsc()}-{p.upper()}-NETBANK, MUM-N{ref(9)}",
        f"NEFT/{random.choice(IFSC_PREFIX)}N{ref(11)}/{p.upper()}",
        f"BRN-CLG-CHQ PAID TO {random.choice(['Mr', 'Mrs', 'Ms'])} {p.upper()}/{random.choice(BANKS)}",
        f"RTGS/{random.choice(IFSC_PREFIX)}R{ref(16)}/{p.upper()}",
    ])


def person_in() -> str:
    p = name()
    return random.choice([
        f"UPI/P2A/{ref()}/{p.upper()}/{random.choice(BANKS)}",
        f"UPI/{p.upper()}/{vpa(p)}/{random.choice(['Payment', 'UPI', 'dinner split', 'returning', 'NA'])}/{random.choice(BANKS)}",
        f"BY TRANSFER-UPI/CR/{ref()}/{p.upper()[:20]}/{random.choice(BANKS)}/{vpa(p)}/Payment",
        f"IMPS/P2A/{ref()}/{p.upper().replace(' ', '')}/{random.choice(BANKS)}BANK",
        f"NEFT CR-{ifsc()}-{p.upper()}-{ref(10)}",
        f"BY TRANSFER-NEFT*{ifsc()}*{random.choice(IFSC_PREFIX)}N{ref(9)}*{p.upper()}",
        f"DEP TFR {ref(10)} {p.upper()}",
    ])


def self_transfer(out: bool) -> str:
    return random.choice([
        f"MOB/SELFFT/{ref(10)}/{ref(10)}",
        f"SELF FUND TRANSFER {'TO' if out else 'FROM'} A/C {acct()}",
        f"{'TO' if out else 'FROM'} OWN ACCOUNT {acct()} {ref(8)}",
        f"SELF TRANSFER {'TO' if out else 'FROM'} {random.choice(BANKS)} {acct()}",
        f"UPI/SELF/{ref()}/{'to' if out else 'from'} own account",
        f"{'TRF TO' if out else 'TRF FROM'} LINKED A/C {acct()}",
        f"IMPS-SELF-{ref(10)}-{random.choice(BANKS)}",
    ])


# ------------------------------------------------------------------------------ categories

MERCHANTS: dict[str, list[str]] = {
    "Groceries": ["BigBasket", "Blinkit", "Zepto", "Swiggy Instamart", "DMart", "More Supermarket", "Reliance Fresh",
                  "Nature's Basket", "Spencer's", "Star Bazaar", "JioMart", "Ratnadeep", "Kirana Store"],
    "Food & Dining": ["Swiggy", "Zomato", "Domino's Pizza", "McDonald's", "KFC", "Starbucks", "Cafe Coffee Day",
                      "Chai Point", "Barbeque Nation", "Faasos", "Behrouz Biryani", "Subway", "Haldiram's", "EatSure"],
    "Shopping": ["Amazon", "Flipkart", "Myntra", "Ajio", "Nykaa", "Meesho", "Tata CLiQ", "Croma", "Reliance Digital",
                 "Decathlon", "IKEA", "Lifestyle", "Westside", "Urban Company", "Lenskart"],
    "Health & Medical": ["Apollo Pharmacy", "PharmEasy", "1mg", "Netmeds", "MedPlus", "Apollo Hospitals",
                         "Fortis Healthcare", "Manipal Hospital", "Practo", "Thyrocare", "Dr Lal PathLabs", "Cult.fit"],
    "Fuel & Transport": ["Uber", "Ola", "Rapido", "Indian Oil", "HP Petrol Pump", "Bharat Petroleum",
                         "Namma Metro", "Delhi Metro", "FASTag Recharge", "Park+", "Shell Petrol"],
    "Travel": ["IRCTC", "MakeMyTrip", "Goibibo", "IndiGo", "Air India", "Akasa Air", "OYO Rooms", "Airbnb",
               "Cleartrip", "RedBus", "Yatra", "Ixigo"],
    "Entertainment & Subscriptions": ["Netflix", "Amazon Prime", "JioHotstar", "Spotify", "YouTube Premium",
                                      "BookMyShow", "PVR Cinemas", "INOX", "Sony LIV", "Apple Media Services",
                                      "Google Play", "Zee5"],
    "Education": ["BYJU'S", "Unacademy", "Vedantu", "Coursera", "Udemy", "Cuemath", "Kidzee",
                  "School Fee Payment", "College Fees", "Physics Wallah"],
    "Utilities": ["BESCOM", "Tata Power", "Adani Electricity", "BSES Rajdhani", "MSEDCL", "WBSEDCL",
                  "Mahanagar Gas", "Indane Gas", "HP Gas", "Bharat Gas", "BWSSB Water", "MyGate Maintenance",
                  "NoBrokerHood Maintenance"],
    "Mobile & Internet": ["Airtel Postpaid", "Jio Prepaid", "Jio Fiber", "Vodafone Idea", "BSNL", "ACT Fibernet",
                          "Hathway Broadband", "Tata Play", "Airtel Xstream Fiber", "Airtel Digital TV"],
    "Insurance": ["LIC", "HDFC Life", "ICICI Prudential Life", "Star Health", "Bajaj Allianz", "Niva Bupa",
                  "Tata AIG", "SBI Life", "Max Life", "Care Health"],
    "Mutual Fund / SIP": ["HDFC Mutual Fund", "ICICI Prudential MF", "SBI Mutual Fund", "Axis Mutual Fund",
                          "Mirae Asset MF", "Parag Parikh MF", "Nippon India MF", "BSE STAR MF", "CAMS", "KFINTECH",
                          "Groww", "Zerodha Coin", "Kuvera", "Indian Clearing Corp"],
    "Stocks & Trading": ["Zerodha Broking", "Upstox", "Angel One", "ICICI Securities", "HDFC Securities",
                         "Groww Invest", "5paisa", "Kotak Securities", "Dhan"],
    "EMI & Loan Repayment": ["HDFC Home Loan", "SBI Home Loan", "ICICI Personal Loan", "Bajaj Finserv",
                             "Tata Capital", "Axis Bank Loan", "IDFC First Loan", "LIC Housing Finance",
                             "Muthoot Finance", "Car Loan"],
    "House Rent": ["NoBroker Rent", "CRED Rent", "Housing.com Rent", "Magicbricks Rent"],
    "Refund & Cashback": ["Amazon", "Flipkart", "Swiggy", "Zomato", "Myntra", "Paytm", "PhonePe", "Google Pay",
                          "MakeMyTrip", "IRCTC", "BigBasket"],
    "Dividend": ["INFOSYS LTD", "TCS LTD", "ITC LTD", "HDFC BANK LTD", "RELIANCE INDUSTRIES", "COAL INDIA",
                 "HINDUSTAN UNILEVER", "BAJAJ AUTO", "WIPRO LTD", "POWER GRID"],
    "Salary": ["Infosys", "TCS", "Wipro", "Akamai Technologies", "Google India", "Microsoft India", "Amazon India",
               "JP Morgan", "Deloitte", "Accenture", "Cognizant", "Flipkart Internet", "Ashoka Centre"],
}

GENERIC: dict[str, list[Template]] = {name_: PURCHASE for name_ in (
    "Groceries", "Food & Dining", "Shopping", "Health & Medical", "Fuel & Transport", "Travel",
    "Entertainment & Subscriptions", "Education", "Utilities", "Mobile & Internet",
)}

SPECIFIC: dict[str, list[Callable[[str], str]]] = {
    "Utilities": PURCHASE + [
        lambda m: f"BBPS/{m.upper()}/{ref(10)}", lambda m: f"BILLPAY/{m.upper()}/{ref(8)}/ELECTRICITY",
    ],
    "Mobile & Internet": PURCHASE + [
        lambda m: f"BIL/ONL/{ref(9)}/{m.upper()} RECHARGE", lambda m: f"{m.upper()} RECHARGE {ref(10)}",
    ],
    "Insurance": [
        lambda m: f"NACH/{m.upper()} PREMIUM/{ref(10)}", lambda m: f"ACH D- {m.upper()}-{ref(12)}",
        lambda m: f"POLICY {ref(9)} PREMIUM {m.upper()}", lambda m: f"BIL/ONL/{ref(9)}/{m.upper()}",
        lambda m: f"UPI/P2M/{ref()}/{m.upper()}/Premium",
    ],
    "Mutual Fund / SIP": [
        lambda m: f"NACH-MUT-DR/{m.upper()}/SIP {ref(4)}", lambda m: f"ACH D- {m.upper()}-{ref(12)}",
        lambda m: f"NACH/TP ACH {m.upper()}/{ref(10)}", lambda m: f"BSE STAR MF/{ref(10)}/SIP",
        lambda m: f"UPI/P2M/{ref()}/{m.upper()}/SIP", lambda m: f"MF SIP {m.upper()} {ref(8)}",
        lambda m: f"{m.upper()} SIP PURCHASE {ref(8)}",
    ],
    "Stocks & Trading": [
        lambda m: f"NEFT Dr-{ifsc()}-{m.upper()} LTD-NSE CLIENT {ref(6)}", lambda m: f"UPI/P2M/{ref()}/{m.upper()}/Add funds",
        lambda m: f"IMPS-{ref(10)}-{m.upper()}-FUNDS", lambda m: f"IPO {random.choice(MERCHANTS['Dividend'])} ASBA BLOCK {ref(8)}",
        lambda m: f"{m.upper()} PAYIN {ref(8)}",
    ],
    "EMI & Loan Repayment": [
        lambda _m: f"{ref(15)}_EMI_{date()}", lambda _m: f"ECS EMI {ref(6)}", lambda m: f"{m.upper()} EMI PAYMENT",
        lambda m: f"AUTO DEBIT EMI {m.upper()}", lambda _m: f"LOAN EMI DEBIT {ref(8)}",
        lambda m: f"NACH/{m.upper()}/EMI {ref(6)}", lambda m: f"EMI/{m.upper()}/{ref(4)}",
    ],
    "House Rent": [
        lambda m: f"UPI/P2M/{ref()}/{m.upper()}/rent", lambda m: f"{m.upper()} PAYMENT {ref(10)}",
        lambda _m: f"UPI/{ref()}/RENT {random.choice(MONTHS)}/{vpa()}",
        lambda _m: f"NEFT Dr-{ifsc()}-{name().upper()}-HOUSE RENT {random.choice(MONTHS)}",
        lambda _m: f"UPI/{name().upper()}/{vpa()}/Rent {month_year()}/{random.choice(BANKS)}",
        lambda _m: f"IMPS/P2A/{ref()}/{name().upper()}/RENT",
    ],
    "Credit Card Payment": [
        lambda _m: f"{ref(8)}CARD{random.choice(['AXIS', 'HDFC', 'ICICI', 'SBI'])} CC {ref(6)}",
        lambda _m: f"CC PAYMENT/{random.choice(BANKS)} CREDIT CARD/XX{ref(4)}",
        lambda _m: f"CRD-PMNT-{ref(6)}****{ref(4)}", lambda _m: f"CreditCard Payment XX {ref(4)}",
        lambda _m: f"UPI/P2M/{ref()}/CRED Club/credit card bill", lambda _m: f"BILLDESK/{random.choice(BANKS)}CARDS/{ref(10)}",
        lambda _m: f"BIL/ONL/{ref(9)}/{random.choice(BANKS)} CREDIT CARD", lambda _m: f"MB PAYMENT CARD XX{ref(4)}",
    ],
    "ATM Withdrawal": [
        lambda _m: f"ATM WDL/NFS/CASH WITHDRAWAL/S1A{ref(5)}", lambda _m: f"ATM-WDL {random.choice(CITIES)} {ref(6)}",
        lambda _m: f"NFS/CASH WDL/{ref(10)}/{random.choice(CITIES)}", lambda _m: f"CWDR/{ref(10)}/{random.choice(BANKS)} ATM {random.choice(CITIES)}",
        lambda _m: "CASH WITHDRAWAL BY SELF", lambda _m: f"ATW-{ref(6)}XXXXXX{ref(4)}-{ref(8)}-{random.choice(CITIES)}",
        lambda _m: f"WDL TFR ATM {random.choice(CITIES)} {ref(6)}", lambda _m: f"POS {random.choice(BANKS)} ATM WITHDRAWAL {random.choice(CITIES)}",
    ],
    "Taxes": [
        lambda _m: f"INCOME TAX/CHALLAN 280/{ref(10)}", lambda _m: f"TIN-NSDL TAX {ref(10)}",
        lambda _m: f"GST PAYMENT {ref(2)}AAB{''.join(random.choices(string.ascii_uppercase, k=2))}{ref(4)}",
        lambda _m: f"PROPERTY TAX {random.choice(CITIES)} MUNICIPAL CORP", lambda _m: f"ADVANCE TAX ITNS 280 {ref(8)}",
        lambda _m: "e-PAY INCOME TAX DEPT", lambda _m: f"BIL/ONL/{ref(9)}/INCOME TAX DEPARTMENT",
    ],
    "Bank Charges & Fees": [
        lambda _m: "Consolidated Charges for A/c", lambda _m: f"SMS ALERT CHGS {random.choice(MONTHS)}",
        lambda _m: "DEBIT CARD ANNUAL FEE", lambda _m: f"GST ON CHARGES {ref(6)}", lambda _m: "MIN BAL CHGS",
        lambda _m: f"ATM TXN CHGS {ref(6)}", lambda _m: "CHQ BOOK CHGS", lambda _m: f"NEFT CHGS {ref(8)}",
        lambda _m: f"IMPS CHARGES {ref(8)}", lambda _m: "DC ANNUAL FEE GST",
    ],
    "Fixed / Recurring Deposit": [
        lambda _m: f"TRF TO FD A/C {acct()}", lambda _m: f"RD INSTALLMENT {acct()}", lambda _m: f"TO RD A/C {acct()}",
        lambda _m: f"AUTO SWEEP TO FD {ref(8)}", lambda _m: "AUTOSWEEP-Transfer to linked fixed deposit",
        lambda _m: f"TRANSFER TO DEPOSIT A/C {acct()}", lambda _m: f"FD BOOKING {ref(10)}",
    ],
    "Transfer to Others": [lambda _m: person_out()],
    "Transfer to Self": [lambda _m: self_transfer(out=True)],
    "Other Expense": [
        lambda _m: f"DONATION {random.choice(['GIVEINDIA', 'AKSHAYA PATRA', 'CRY', 'TEMPLE TRUST'])} {ref(6)}",
        lambda _m: f"MISC DEBIT {ref(8)}", lambda _m: f"POS {ref(6)} SRI {random.choice(LAST).upper()} ENTERPRISES",
        lambda _m: f"UPI/P2M/{ref()}/{random.choice(LAST).upper()} TRADERS/Payment",
        lambda _m: f"PASSPORT SEVA FEE {ref(8)}", lambda _m: f"COURT FEE {ref(6)}",
    ],
    "Salary": [
        lambda m: f"NEFT TRANSFER FROM SALARY FOR {month_year()} {m.upper()}",
        lambda m: f"NEFT/CHASH{ref(8)}/Salary for {month_year()} {m}/{random.choice(BANKS)} BANK",
        lambda _m: f"NEFT/CHASH{ref(8)}/Sala", lambda m: f"SALARY CREDIT {m.upper()}", lambda m: f"SAL CR {m.upper()} {random.choice(MONTHS)}",
        lambda m: f"BY TRANSFER-NEFT*{ifsc()}*{ref(9)}*{m.upper()} SAL", lambda m: f"{m.upper()} SALARY {month_year()}",
        lambda m: f"PAYROLL {m.upper()} {ref(6)}",
    ],
    "Interest": [
        lambda _m: f"Int.Pd:{date()} to {date()}", lambda _m: "INTEREST CREDIT", lambda _m: f"SB INT CR {date()}",
        lambda _m: "CREDIT INTEREST CAPITALISED", lambda _m: f"INT ON FD {acct()}", lambda _m: f"INTEREST PAID {random.choice(MONTHS)}",
        lambda _m: f"{acct()} INT.PD", lambda _m: "QTRLY INTEREST CREDIT",
    ],
    "Dividend": [
        lambda m: f"DIV/{m}/{ref(8)}", lambda m: f"ACH C- {m} DIV {ref(10)}", lambda m: f"{m} FINAL DIVIDEND",
        lambda m: f"NACH-DIV-{m}-{ref(6)}", lambda m: f"{m} INTERIM DIV {ref(6)}",
    ],
    "Investment Redemption": [
        lambda _m: f"MF REDEMPTION {random.choice(MERCHANTS['Mutual Fund / SIP']).upper()} {ref(8)}",
        lambda _m: f"BSE STAR MF REDEMPTION {ref(8)}", lambda _m: f"ZERODHA BROKING PAYOUT {ref(6)}",
        lambda _m: f"FD MATURITY PROCEEDS {acct()}", lambda _m: f"RD MATURITY {acct()}",
        lambda _m: f"NEFT/{random.choice(MERCHANTS['Mutual Fund / SIP']).upper()} REDEMPTION/{ref(8)}",
        lambda _m: f"{random.choice(MERCHANTS['Stocks & Trading']).upper()} WITHDRAWAL {ref(8)}",
        lambda _m: "AUTO SWEEP REVERSAL FROM FD",
    ],
    "Refund & Cashback": [
        lambda m: f"REFUND/{m.upper()}/{ref(10)}", lambda _m: f"UPI/REV/{ref()}/REVERSAL", lambda m: f"CASHBACK {m.upper()}",
        lambda _m: f"REVERSAL OF {ref(12)}", lambda m: f"{m.upper()} REFUND {ref(8)}", lambda m: f"UPI/P2M/{ref()}/{m.upper()}/Refund",
        lambda _m: f"ATM TXN REVERSAL {ref(6)}",
    ],
    "Rent Received": [
        lambda _m: f"UPI/{ref()}/RENT {random.choice(MONTHS)}/{vpa()}", lambda _m: f"NEFT CR-{ifsc()}-{name().upper()}-RENT {random.choice(MONTHS)}",
        lambda _m: f"RENT RECEIVED FROM {name().upper()}", lambda _m: f"UPI/{name().upper()}/{vpa()}/House rent/{random.choice(BANKS)}",
        lambda _m: f"IMPS/P2A/{ref()}/{name().upper()}/RENT {month_year()}",
    ],
    "Transfer from Others": [lambda _m: person_in()],
    "Transfer from Self": [lambda _m: self_transfer(out=False)],
    "Other Income": [
        lambda _m: f"CASH DEPOSIT {random.choice(CITIES)} BRANCH", lambda _m: f"CHQ DEP {ref(6)}",
        lambda _m: f"INSURANCE CLAIM {random.choice(MERCHANTS['Insurance']).upper()} {ref(8)}",
        lambda _m: "PRIZE MONEY CREDIT", lambda _m: f"OLX SALE {ref(6)}", lambda _m: f"BY CASH {ref(6)}",
        lambda _m: f"GOVT SUBSIDY {ref(8)}",
    ],
}

AMOUNTS: dict[str, tuple[int, int]] = {
    "Groceries": (80, 6000), "Food & Dining": (60, 4000), "Shopping": (150, 40000), "Health & Medical": (100, 50000),
    "Fuel & Transport": (40, 5000), "Travel": (300, 60000), "Entertainment & Subscriptions": (49, 2000),
    "Education": (500, 150000), "Utilities": (100, 8000), "Mobile & Internet": (99, 3000), "Insurance": (1000, 80000),
    "Mutual Fund / SIP": (500, 50000), "Stocks & Trading": (1000, 200000), "Fixed / Recurring Deposit": (1000, 500000),
    "House Rent": (5000, 80000), "EMI & Loan Repayment": (2000, 90000), "Credit Card Payment": (500, 200000),
    "ATM Withdrawal": (100, 20000), "Taxes": (500, 300000), "Bank Charges & Fees": (1, 1200),
    "Transfer to Others": (10, 100000), "Transfer to Self": (500, 500000), "Other Expense": (50, 20000),
    "Salary": (15000, 400000), "Interest": (1, 20000), "Dividend": (10, 30000), "Investment Redemption": (1000, 500000),
    "Refund & Cashback": (10, 20000), "Rent Received": (5000, 80000), "Transfer from Others": (10, 100000),
    "Transfer from Self": (500, 500000), "Other Income": (100, 100000),
}


def templates_for(category: str) -> list[Template]:
    return SPECIFIC.get(category) or GENERIC[category]


def narration(category: str) -> str:
    merchant = random.choice(MERCHANTS.get(category, [""]))
    return random.choice(templates_for(category))(merchant)


def amount(category: str) -> Decimal:
    low, high = AMOUNTS[category]
    value = random.uniform(low, high)
    return Decimal(round(value)) if value > 1000 and random.random() < 0.6 else Decimal(f"{value:.2f}")


def row(category: str, direction: Direction) -> dict:
    tx = TxInput(narration(category), direction, amount(category))
    return {
        "state": build_state(tx),
        "questions": {QUESTION_ID: build_question(direction).model_dump(exclude_none=True, mode="json")},
        "expected": {QUESTION_ID: category},
    }


def generate(per_category: int, only: list[str] | None = None) -> list[dict]:
    rows = []
    for direction in ("out", "in"):
        categories = model_categories(direction)
        for category in categories:
            if only and category not in only:
                continue
            rows.extend(row(category, direction) for _ in range(per_category))
    random.shuffle(rows)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", type=int, default=1, help="round number; output goes to data/round-N/")
    parser.add_argument("--per-category", type=int, default=150, help="examples per category (all categories)")
    parser.add_argument("--focus", default="", help="comma-separated categories to add extra examples for")
    parser.add_argument("--extra", type=int, default=0, help="extra examples per focus category")
    parser.add_argument("--mix-previous", type=float, default=0.0,
                        help="fraction of the previous round's training rows to mix in (for continued training)")
    parser.add_argument("--eval-fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=None, help="random seed (default: 1000 + round)")
    args = parser.parse_args()

    random.seed(args.seed if args.seed is not None else 1000 + args.round)
    all_categories = [c for d in ("out", "in") for c in model_categories(d)]
    focus = [c.strip() for c in args.focus.split(",") if c.strip()]
    unknown = [c for c in focus if c not in all_categories]
    if unknown:
        sys.exit(f"Unknown categories: {unknown}")

    rows = generate(args.per_category) if args.per_category else []
    if focus and args.extra:
        rows += generate(args.extra, only=focus)
    if args.mix_previous:
        previous = DATA_DIR / f"round-{args.round - 1}" / "train.jsonl"
        old = [json.loads(line) for line in previous.read_text(encoding="utf-8").splitlines()]
        rows += random.sample(old, round(len(old) * args.mix_previous))
    random.shuffle(rows)

    cut = round(len(rows) * (1 - args.eval_fraction))
    out = DATA_DIR / f"round-{args.round}"
    write_jsonl(out / "train.jsonl", rows[:cut])
    write_jsonl(out / "eval.jsonl", rows[cut:])

    counts = Counter(r["expected"][QUESTION_ID] for r in rows)
    print(f"Wrote {cut} training and {len(rows) - cut} eval rows to {out}")
    print(f"{len(counts)} categories, {min(counts.values())}-{max(counts.values())} examples each")
    print("\nSamples:")
    by_category: dict[str, list[str]] = {}
    for r in rows:
        by_category.setdefault(r["expected"][QUESTION_ID], []).append(r["state"]["narration"])
    for category in all_categories:
        for text in by_category.get(category, [])[:3]:
            print(f"  {category:<30} {text}")


if __name__ == "__main__":
    main()
