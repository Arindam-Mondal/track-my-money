"""Check the masker on synthetic narrations where we know exactly what is private.

The generator's helpers (person names, UPI IDs, reference numbers, accounts, IFSC codes) are
wrapped to record every private value they produce. Each narration is masked, then:

  leak          a recorded private value is still in the masked text
  over-masked   a known brand (app/masking/brands.py) used in the narration was masked

Run from backend/:  uv run python training/check_masking.py [--n 2000]
"""

import argparse
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_dataset as gen  # noqa: E402

from app.categorising.categories import model_categories  # noqa: E402
from app.masking.brands import BRANDS  # noqa: E402
from app.masking.masker import mask_narration  # noqa: E402

SECRET = b"check-masking"
BRAND_SET = {b.lower() for b in BRANDS}
recorded: list[tuple[str, str]] = []  # (kind, private value) for the narration being generated


def record(kind: str, fn):
    def wrapper(*args, **kwargs):
        value = fn(*args, **kwargs)
        recorded.append((kind, value))
        return value
    return wrapper


gen.name = record("name", gen.name)
gen.ref = record("ref", gen.ref)
gen.acct = record("account", gen.acct)
gen.ifsc = record("ifsc", gen.ifsc)
_vpa = gen.vpa
gen.vpa = lambda person=None: record("upi", _vpa)(person)


def leaks(masked: str, private: list[tuple[str, str]]) -> list[str]:
    found = []
    upper = masked.upper()
    for kind, value in private:
        if kind == "name":
            found += [f"name:{w}" for w in value.upper().split() if len(w) > 2 and re.search(rf"\b{re.escape(w)}\b", upper)]
        elif kind == "upi":
            local = value.split("@")[0].upper()
            if local and local in upper:
                found.append(f"upi:{local}")
        elif kind in ("ref", "account", "ifsc"):
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 3 and digits in masked:
                found.append(f"{kind}:{digits}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    random.seed(args.seed)

    categories = [(d, c) for d in ("out", "in") for c in model_categories(d)]
    leak_counts, over_masked, unknown_merchants = Counter(), Counter(), Counter()
    examples: list[str] = []
    for i in range(args.n):
        direction, category = categories[i % len(categories)]
        merchant = random.choice(gen.MERCHANTS.get(category, [""]))
        recorded.clear()
        narration = random.choice(gen.templates_for(category))(merchant)
        masked = mask_narration(narration, SECRET)

        found = leaks(masked, recorded)
        for item in found:
            leak_counts[item.split(":")[0]] += 1
        if found and len(examples) < 12:
            examples.append(f"LEAK {found}: {narration}  ->  {masked}")

        if merchant and merchant.upper() in narration.upper():
            if merchant.lower() in BRAND_SET:
                if merchant.upper() not in masked.upper():
                    over_masked[merchant] += 1
                    if len(examples) < 12:
                        examples.append(f"OVER-MASKED {merchant}: {narration}  ->  {masked}")
            else:
                unknown_merchants[merchant] += 1

    print(f"Masked {args.n} synthetic narrations.")
    print(f"Leaks: {sum(leak_counts.values())}  {dict(leak_counts) or ''}")
    print(f"Known brands over-masked: {sum(over_masked.values())}  {dict(over_masked.most_common(10)) or ''}")
    if unknown_merchants:
        print(f"Generator merchants not in the brand list (masked by design; add them if they're public brands): "
              f"{', '.join(sorted(unknown_merchants))}")
    for line in examples:
        print("  " + line)
    sys.exit(1 if leak_counts or over_masked else 0)


if __name__ == "__main__":
    main()
