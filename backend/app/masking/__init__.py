"""Masking of narrations before anything is sent to a cloud model. See masker.py for the rules."""

import secrets
from pathlib import Path

from app.config import settings
from app.masking.masker import MASKING_VERSION, mask_narration

__all__ = ["MASKING_VERSION", "mask", "masking_secret"]

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def masking_secret() -> bytes:
    """The key behind [PERSON_xxxx] tokens. Created once if missing, and saved to
    MASKING_SECRET_FILE when that is set (in Docker: a volume), else to backend/.env.

    Keep it: a new key gives every name a new token, so earlier and later statements no longer match.
    """
    if not settings.masking_secret:
        if settings.masking_secret_file:
            settings.masking_secret = secret_from_file(Path(settings.masking_secret_file))
        else:
            settings.masking_secret = secrets.token_hex(32)
            with ENV_FILE.open("a", encoding="utf-8") as env:
                env.write(f"\n# Key for consistent masking tokens. Keep it; changing it re-keys all tokens.\n"
                          f"MASKING_SECRET={settings.masking_secret}\n")
    return settings.masking_secret.encode()


def secret_from_file(path: Path) -> str:
    """The key in `path`, created there first if the file is missing or empty."""
    if path.exists() and (secret := path.read_text(encoding="utf-8").strip()):
        return secret
    secret = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret + "\n", encoding="utf-8")
    path.chmod(0o600)
    return secret


def mask(narration: str) -> str:
    return mask_narration(narration, masking_secret())
