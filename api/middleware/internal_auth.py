import hmac

from fastapi import Header, HTTPException, Depends, status

from settings import Settings
from dependencies import get_settings


def verify_internal_api_key(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Protection for internal endpoints (e.g., `/rag/index*`).
    Expects an `X-Internal-Api-Key` header that matches `settings.INTERNAL_API_KEY`.

    This is a SECOND layer of protection, separate from `HMACAuthMiddleware`:
    HMAC verifies that the request originated from Moodle in the first place,
    whereas this key verifies that it specifically came from a trusted internal call (task),
    rather than just any code within the plugin.
    """
    if not x_internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal API key",
        )

    if not hmac.compare_digest(x_internal_api_key, settings.INTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )