"""Jev, the System One model behind column reading and categorising: one key, one endpoint, one client.

The endpoint is TypeSafe's cloud unless JEV_BASE_URL is set; any Jev-compatible server works,
including Command Code's Provider API, which wants JEV_BASE_URL and JEV_MODEL together.
"""

from typesafe_sdk import RetryPolicy, TypeSafeClient

from app.config import settings

# Fail over to the keyword rules quickly when the API is down: 2 attempts of at most 15 s each.
JEV_RETRY = RetryPolicy(max_retries=1)
JEV_TIMEOUT = 15.0


def jev_key(sent_key: str | None = None) -> str | None:
    """The key to call Jev with: the one the browser sent, else the server's own; None for neither."""
    return (sent_key or "").strip() or settings.jev_api_key.strip() or None


def jev_client(api_key: str) -> TypeSafeClient:
    """An HTTP client for Jev with this key; the SDK fills in the endpoint when none is configured."""
    return TypeSafeClient(
        api_key=api_key.strip(),
        base_url=settings.jev_base_url or None,
        model=settings.jev_model or None,
        retry=JEV_RETRY,
        timeout=JEV_TIMEOUT,
        compression=False,  # the SDK zstd-compresses bodies over 1 KB; Command Code reads only plain JSON
    )
