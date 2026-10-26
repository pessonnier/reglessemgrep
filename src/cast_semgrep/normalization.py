"""Conservative normalization of published reference identifiers."""

from __future__ import annotations

import re


OWASP_ID = re.compile(r"^(API|A)(\d{1,2})[:-](20\d{2})$", re.IGNORECASE)


def normalize_owasp(value: str) -> str:
    raw = value.strip().upper()
    match = OWASP_ID.fullmatch(raw)
    if match:
        prefix, number, year = match.groups()
        return f"{prefix}{int(number):02d}:{year}"
    return raw
