"""Check that the local Laya answers category questions, and measure its speed.

Run from backend/ after `docker compose up -d laya`:
    uv run python scripts/laya_smoke.py
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.categorising.laya import TxInput, laya_classifier  # noqa: E402
from app.config import settings  # noqa: E402

SAMPLES = [
    TxInput("ATM WDL/NFS/CASH WITHDRAWAL/S1ANMU12", "out", Decimal("5000")),
    TxInput("NACH-MUT-DR/BSE STAR MF/SIP 4567", "out", Decimal("10000")),
    TxInput("UPI/412345678/SWIGGY/swiggy@icici", "out", Decimal("450")),
    TxInput("UPI/98765/RENT OCT/landlord@okhdfc", "out", Decimal("25000")),
    TxInput("NEFT/ACME TECHNOLOGIES PVT LTD/SALARY OCT", "in", Decimal("120000")),
    TxInput("Int.Pd:01-04-2026 to 30-06-2026", "in", Decimal("812")),
]

print(f"Laya at {settings.laya_base_url}")
with laya_classifier() as classify:
    started = time.perf_counter()
    for tx in SAMPLES:
        answer = classify(tx)
        print(f"  {tx.narration[:44]:<44} -> {answer.category:<22} confidence {answer.confidence:.2f}")
    sequential = len(SAMPLES) / (time.perf_counter() - started)

    batch = SAMPLES * 5
    started = time.perf_counter()
    with ThreadPoolExecutor(settings.categorise_workers) as pool:
        list(pool.map(classify, batch))
    parallel = len(batch) / (time.perf_counter() - started)

print(f"Speed: {sequential:.1f} calls/s one at a time, {parallel:.1f} calls/s with {settings.categorise_workers} workers")
