"""Mask a bank narration: hide everything that identifies someone, keep what decides the category.

The approach is an allow-list. Known brands, payment keywords, business words and common English
words are kept; identifiers become typed placeholders; anything else becomes [NAME_xxxx]. People
in fields whose position says "person" (UPI/P2A/<ref>/<NAME>/...) become [PERSON_xxxx].

The xxxx suffix is a keyed hash (HMAC-SHA256 with a local secret), so the same name gets the same
token in every statement, but the token can't be turned back into the name without the secret.

    UPI/P2A/412345678901/RAHUL SHARMA/rahul.12@okaxis/rent oct
      -> UPI/P2A/[REF]/[PERSON_7F3A]/[UPI_ID]@okaxis/rent oct
"""

import hashlib
import hmac
import re
from collections.abc import Callable

from app.masking.brands import BRANDS
from app.masking.wordlists import BANK_WORDS, CITIES, COMMERCE_WORDS, KEEP_KEYWORDS, NAMES, common_words

# Bump when the rules change; the backfill re-masks rows stored with an older version.
MASKING_VERSION = 3  # 3: more names (syed, md…); short words treated as initials, except of/in/at…

# Protected parts are swapped for one private-use character each: no digits and never part of a
# word, so later steps (including the final digit pass) can't change them.
_SENTINEL_BASE = 0xE000
_SENTINEL = "[-]"
_SENTINEL_RE = re.compile(_SENTINEL)

_L = r"(?<![A-Za-z0-9])"  # word edges that also treat digits as part of a word
_R = r"(?![A-Za-z0-9])"
_MONTH = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*"
_I = re.IGNORECASE

_BRAND_RE = re.compile(_L + "(" + "|".join(re.escape(b) for b in sorted(BRANDS, key=len, reverse=True)) + ")" + _R, _I)
_BRAND_WORDS = frozenset(w for b in BRANDS for w in re.findall(r"[a-z0-9]+", b))

# (pattern, kind, replacement) for identifiers, applied in this order.
_IDENTIFIERS: list[tuple[re.Pattern[str], str, Callable[[re.Match[str]], str]]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z][\w.-]*"), "EMAIL", lambda m: "[EMAIL]"),
    # The local part stops at "-": narrations join fields with it (UPI-KFC-kfc@axl).
    (re.compile(r"(?P<local>[A-Za-z0-9._]+)@(?P<psp>[A-Za-z]+)"), "UPI", lambda m: _upi(m)),
    (re.compile(_L + r"[A-Z]{5}\d{4}[A-Z]" + _R, _I), "PAN", lambda m: "[PAN]"),
    (re.compile(_L + r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]" + _R, _I), "GSTIN", lambda m: "[GSTIN]"),
    (re.compile(_L + r"(?P<bank>[A-Z]{4})0[A-Z0-9]{6}" + _R, _I), "IFSC", lambda m: f"[IFSC:{m['bank'].upper()}]"),
    (re.compile(_L + r"\d{4,6}[X*]{4,8}\d{4}" + _R, _I), "ACCOUNT", lambda m: "[ACCOUNT]"),
    (re.compile(_L + r"[X*]{2,}\d{3,6}" + _R, _I), "ACCOUNT", lambda m: "[ACCOUNT]"),
    (re.compile(r"\b(?P<label>A/?C(?:\s*NO)?\.?|ACCOUNT(?:\s*NO)?\.?)\s*[:\-]?\s*[X*\d]{4,}", _I), "ACCOUNT",
     lambda m: f"{m['label']} [ACCOUNT]"),
    (re.compile(r"\+91[\s-]?\d{10}" + _R), "PHONE", lambda m: "[PHONE]"),
    (re.compile(_L + r"\d{4}\s\d{4}\s\d{4}" + _R), "AADHAAR", lambda m: "[AADHAAR]"),
    (re.compile(_L + r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}[-/ ]?" + _MONTH + r"[-/ ]?\d{2,4})"
                + _R, _I), "DATE", lambda m: "[DATE]"),
]
_REF_RE = re.compile(_L + r"[A-Za-z]*\d[A-Za-z\d]*" + _R)
_DIGIT_KEYWORDS = re.compile(_L + r"P2[AMP]" + _R, _I)  # payment-type codes whose digit must survive

# Fields that hold a person in common narration formats (group "n" is the name field).
_PERSON_PATTERNS = [re.compile(p, _I) for p in (
    r"\bUPI/P2[AP]/[^/]+/(?P<n>[^/]+)",
    r"\b(?:TO|BY) TRANSFER-UPI/(?:DR|CR)/[^/]+/(?P<n>[^/]+)",
    r"\bIMPS/P2A/[^/]+/(?P<n>[^/]+)",
    r"\bIMPS-[^-]+-(?P<n>[^-]+)-",
    r"\bNEFT (?:DR|CR)-[^-]+-(?P<n>[^-]+)",
    r"\bNEFT\*[^*]+\*[^*]+\*(?P<n>[^*]+)",
    r"\bRTGS/[^/]+/(?P<n>[^/]+)",
    r"\bPAID TO (?:(?:MR|MRS|MS|SHRI|SMT)\.? )?(?P<n>[^/]+)",
    r"\bTRANSFER FROM (?P<n>[^(/]+)",
    r"\bDEP TFR \S+ (?P<n>[^/]+)$",
)]
_BEFORE_UPI_ID = re.compile(r"\bUPI/(?P<n>[^/]+)/(?P<id>" + _SENTINEL + ")", _I)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'.&]*")


def _upi(match: re.Match[str]) -> str:
    """Keep a merchant's UPI ID (swiggy@icici); hide a person's (rahul.12@okaxis -> [UPI_ID]@okaxis)."""
    letters = re.sub(r"[^a-z]", "", match["local"].lower())
    is_brand = letters in _BRAND_WORDS or any(len(w) >= 4 and w in letters for w in _BRAND_WORDS)
    return match.group(0) if is_brand else f"[UPI_ID]@{match['psp']}"


def _word_kind(word: str) -> str:
    """keep | city | mask | letter, for one word outside identifiers, brands and person fields."""
    w = word.lower().strip(".'&")
    if not w or w in KEEP_KEYWORDS or w in COMMERCE_WORDS or w in BANK_WORDS:
        return "keep"
    if w.endswith("bank") and (w[:-4] in BANK_WORDS or w[:-4] in KEEP_KEYWORDS):  # HDFCBANK, YESBANK
        return "keep"
    if w in CITIES:
        return "city"
    if w in NAMES:
        return "mask"
    if len(w) <= 2:  # initials and fragments (R, SK, MD): masked when they touch a masked word
        return "letter"
    return "keep" if w in common_words() else "mask"


class _Masker:
    def __init__(self, secret: bytes) -> None:
        self.secret = secret
        self.parts: list[tuple[str, str]] = []  # (kind, replacement), indexed by sentinel

    def token(self, kind: str, value: str) -> str:
        normalised = re.sub(r"[^A-Z]", "", value.upper())
        digest = hmac.new(self.secret, f"{kind}:{normalised}".encode(), hashlib.sha256).hexdigest()[:4].upper()
        return f"[{kind}_{digest}]"

    def protect(self, kind: str, replacement: str) -> str:
        self.parts.append((kind, replacement))
        return chr(_SENTINEL_BASE + len(self.parts) - 1)

    def kind(self, sentinel: str) -> str:
        return self.parts[ord(sentinel) - _SENTINEL_BASE][0]

    def restore(self, text: str) -> str:
        while _SENTINEL_RE.search(text):  # a replacement can contain earlier sentinels
            text = _SENTINEL_RE.sub(lambda m: self.parts[ord(m.group(0)) - _SENTINEL_BASE][1], text)
        return text

    def person_field(self, match: re.Match[str]) -> str:
        """Replace the name field of a person-position match with [PERSON_xxxx], unless it's a business."""
        name = match["n"]
        words = [w.lower() for w in _WORD_RE.findall(_SENTINEL_RE.sub(" ", name))]
        if not words or any(w in COMMERCE_WORDS or w in KEEP_KEYWORDS for w in words):
            return match.group(0)  # brand, reference or business: the word pass decides
        start, end = match.start("n") - match.start(), match.end("n") - match.start()
        whole = match.group(0)
        return whole[:start] + self.protect("PERSON", self.token("PERSON", name)) + whole[end:]

    def mask_words(self, s: str) -> str:
        """Keep-lists decide each word; consecutive masked words (and initials) become one [NAME_xxxx]."""
        words = [(m.start(), m.end(), m.group(0)) for m in _WORD_RE.finditer(s)]
        kinds = [_word_kind(w) for _, _, w in words]

        def touching(a: int, b: int) -> bool:  # only spaces or dots between words a and b
            return s[words[a][1]:words[b][0]].strip(" .") == ""

        # Initials and short fragments (R. K. SHARMA, SK KHAN) are masked when they touch a masked word, directly or through
        # other initials; otherwise they're kept (A B C STORES).
        changed = True
        while changed:
            changed = False
            for i, kind in enumerate(kinds):
                if kind == "letter" and any(
                    0 <= j < len(kinds) and kinds[j] == "mask" and touching(min(i, j), max(i, j)) for j in (i - 1, i + 1)
                ):
                    kinds[i], changed = "mask", True
        kinds = ["keep" if k == "letter" else k for k in kinds]

        out, pos, i = [], 0, 0
        while i < len(words):
            start, end, _ = words[i]
            if kinds[i] == "city":
                out += [s[pos:start], self.protect("CITY", "[CITY]")]
                pos = end
            elif kinds[i] == "mask":
                j = i
                while j + 1 < len(words) and kinds[j + 1] == "mask" and touching(j, j + 1):
                    j += 1
                run_end = words[j][1]
                out += [s[pos:start], self.protect("NAME", self.token("NAME", s[start:run_end]))]
                pos, i = run_end, j
            i += 1
        out.append(s[pos:])
        return "".join(out)


def mask_narration(text: str, secret: bytes) -> str:
    m = _Masker(secret)
    s = " ".join(text.split())

    # 1. Identifiers become typed placeholders.
    for pattern, kind, replace in _IDENTIFIERS:
        s = pattern.sub(lambda x, k=kind, r=replace: m.protect(k, r(x)), s)

    # 2. Known brands are kept as written.
    s = _BRAND_RE.sub(lambda x: m.protect("BRAND", x.group(0)), s)

    # 3. Reference numbers: any remaining word with 3+ digits.
    s = _REF_RE.sub(lambda x: m.protect("REF", "[REF]") if sum(c.isdigit() for c in x.group(0)) >= 3 else x.group(0), s)

    # 4. People, found by where they sit in the narration.
    for pattern in _PERSON_PATTERNS:
        s = pattern.sub(m.person_field, s)
    s = _BEFORE_UPI_ID.sub(lambda x: m.person_field(x) if m.kind(x["id"]) == "UPI" else x.group(0), s)

    # 5. Every other word (P2A/P2M/P2P are protected first so their digit survives the last step).
    s = _DIGIT_KEYWORDS.sub(lambda x: m.protect("KEYWORD", x.group(0)), s)
    s = m.mask_words(s)

    # 6. Any digit still outside a protected part becomes 9; then the placeholders go back in.
    return m.restore(re.sub(r"\d", "9", s))
