"""Masking of narrations before anything is sent to a cloud model. See masker.py for the rules."""

import secrets
from pathlib import Path

from app.config import settings
from app.masking.masker import MASKING_VERSION, mask_narration

__all__ = ["MASKING_VERSION", "mask", "masking_secret"]

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def masking_secret() -> bytes:
    """The key behind [PERSON_xxxx] tokens. Created once and saved to backend/.env if missing.

    Keep it: a new key gives every name a new token, so earlier and later statements no longer match.
    """
    if not settings.masking_secret:
        settings.masking_secret = secrets.token_hex(32)
        with ENV_FILE.open("a", encoding="utf-8") as env:
            env.write(f"\n# Key for consistent masking tokens. Keep it; changing it re-keys all tokens.\n"
                      f"MASKING_SECRET={settings.masking_secret}\n")
    return settings.masking_secret.encode()


def mask(narration: str) -> str:
    return mask_narration(narration, masking_secret())
