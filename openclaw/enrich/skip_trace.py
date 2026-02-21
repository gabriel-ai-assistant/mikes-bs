"""Skip-trace stub — BatchSkipTracing API integration placeholder.

Wire this to the real API when SKIP_TRACE_API_KEY is configured.
Interface is stable — callers won't need changes.
"""

import logging
from openclaw.config import settings

logger = logging.getLogger(__name__)


def skip_trace(parcel_id: str) -> dict:
    """Look up owner contact info for a parcel.

    Args:
        parcel_id: UUID of the parcel record.

    Returns:
        dict with keys: phone (str|None), email (str|None)
    """
    if not settings.SKIP_TRACE_API_KEY:
        logger.debug(f"Skip-trace stub called for {parcel_id} — no API key configured")
        return {"phone": None, "email": None}

    # TODO: Implement real BatchSkipTracing API call
    # POST https://api.batchskiptracing.com/v1/lookup
    # Headers: Authorization: Bearer {SKIP_TRACE_API_KEY}
    # Body: { "parcel_id": parcel_id }
    # Response: { "phone": "...", "email": "..." }
    raise NotImplementedError("BatchSkipTracing API integration not yet implemented")


if __name__ == "__main__":
    result = skip_trace("test-parcel-id")
    print(result)
