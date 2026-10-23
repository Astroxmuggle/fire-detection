"""Redaction helpers for anything that leaves the process.

Camera sources may legitimately contain credentials
(``rtsp://user:password@host/stream``). Those strings are stored as configured
so the worker can connect, but they must never be returned by the API, published
over SSE, or written to the log in clear text.
"""

from __future__ import annotations

import re
from typing import Optional

# scheme://userinfo@host  ->  scheme://***@host
_USERINFO = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<userinfo>[^/@\s]+)@")

# Password-like query parameters.
_SECRET_QUERY = re.compile(
    r"(?i)(?P<key>\b(?:password|passwd|pwd|token|api_?key|secret|auth)=)(?P<value>[^&\s]+)"
)

_MASK = "***"


def redact_source(value: Optional[str]) -> Optional[str]:
    """Mask credentials embedded in a camera source or stream URL."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return text

    text = _USERINFO.sub(lambda match: f"{match.group('scheme')}{_MASK}@", text)
    text = _SECRET_QUERY.sub(lambda match: f"{match.group('key')}{_MASK}", text)
    return text


def contains_credentials(value: Optional[str]) -> bool:
    """True when *value* still carries a userinfo section or a secret query parameter."""
    if not value:
        return False
    return bool(_USERINFO.search(str(value)) or _SECRET_QUERY.search(str(value)))
