"""The category lists. Edit this file to add, rename or describe categories.

Laya reads both the name and the description, so descriptions should say what belongs in a
category and name the merchants or keywords that usually appear in Indian bank narrations.
Money out (debits) and money in (credits) have separate lists, so each question offers fewer options.
"""

from decimal import Decimal
from typing import Literal

Direction = Literal["in", "out"]

CATEGORIES: dict[Direction, dict[str, str]] = {
    "out": {
        "Mutual Fund / SIP": "Investments into mutual funds: SIP, NACH or ACH debits to AMCs, BSE StAR MF, CAMS, KFintech, Groww, Zerodha Coin, Kuvera, Paytm Money.",
        "Stocks & Trading": "Money moved to a stock broker or trading account: Zerodha, Upstox, Angel One, ICICI Direct, IPO applications.",
        "Fixed / Recurring Deposit": "Money moved into a fixed deposit, recurring deposit or sweep-in deposit at a bank.",
        "House Rent": "Monthly rent for a house or flat, paid to a landlord or through NoBroker, CRED rent or Housing.com.",
        "EMI & Loan Repayment": "EMI or repayment of a home, car, personal or education loan.",
        "Credit Card Payment": "Payment of a credit card bill (CC payment, CRED, BillDesk card payment, autopay to a card).",
        "Insurance": "Insurance premiums: LIC, health, term, motor or life insurance.",
        "ATM Withdrawal": "Cash taken out at an ATM or a bank counter (ATM WDL, cash withdrawal, NFS, CWDR).",
        "Groceries": "Supermarkets and grocery apps: BigBasket, Blinkit, Zepto, DMart, Swiggy Instamart, local kirana stores.",
        "Food & Dining": "Restaurants, cafes and food delivery: Swiggy, Zomato, restaurant bills.",
        "Shopping": "Online and offline shopping for goods: Amazon, Flipkart, Myntra, Ajio, Nykaa, retail stores.",
        "Utilities": "Electricity, water, piped gas and LPG cylinder bills, and housing society maintenance.",
        "Mobile & Internet": "Mobile recharges, postpaid bills, broadband and DTH: Jio, Airtel, Vi, BSNL, Tata Play.",
        "Fuel & Transport": "Fuel, FASTag, tolls, cabs, auto, metro and local transport: Uber, Ola, Rapido, petrol pumps.",
        "Travel": "Flights, trains, buses and hotels: IRCTC, MakeMyTrip, Goibibo, airlines, hotel bookings.",
        "Health & Medical": "Hospitals, doctors, pharmacies, lab tests: Apollo, PharmEasy, 1mg, Practo.",
        "Education": "School or college fees, courses, books and coaching.",
        "Entertainment & Subscriptions": "Streaming and subscriptions, movies and events: Netflix, Prime, Hotstar, Spotify, BookMyShow, Google Play.",
        "Taxes": "Income tax, advance tax, GST or property tax payments to the government.",
        "Bank Charges & Fees": "Charges the bank takes: SMS charges, annual card fees, minimum balance penalties, GST on charges.",
        "Transfer to Others": "Money sent to another person (UPI, IMPS, NEFT, RTGS) that is not a purchase from a business.",
        "Transfer to Self": "Money moved to another account of the same account holder.",
        "Other Expense": "Money going out that fits none of the other categories.",
    },
    "in": {
        "Salary": "Salary or wages credited by an employer (SAL, SALARY, payroll).",
        "Interest": "Interest the bank pays on savings or deposits (Int.Pd, interest credit).",
        "Dividend": "Dividends from shares or mutual funds (DIV, dividend credit).",
        "Investment Redemption": "Money back from selling or redeeming mutual funds, shares or a matured fixed deposit.",
        "Refund & Cashback": "Refunds of earlier payments and cashback or rewards from merchants and apps.",
        "Rent Received": "Rent paid to the account holder by a tenant.",
        "Transfer from Others": "Money received from another person (UPI, IMPS, NEFT, RTGS).",
        "Transfer from Self": "Money moved in from another account of the same account holder.",
        "Other Income": "Money coming in that fits none of the other categories.",
    },
}

# Own-account transfers: excluded from income and spending totals by default.
SELF_TRANSFERS = frozenset({"Transfer to Self", "Transfer from Self"})
UNCATEGORISED = "Uncategorised"


def direction_of(debit: Decimal) -> Direction:
    """A transaction with a debit is money out; everything else is money in."""
    return "out" if debit > 0 else "in"


def is_valid(category: str, direction: Direction) -> bool:
    return category in CATEGORIES[direction]
