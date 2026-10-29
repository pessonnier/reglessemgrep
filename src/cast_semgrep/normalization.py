"""Canonical, edition-aware keys for published OWASP Top 10 references."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


# Match explicit category + edition, including a reference embedded in its label.
# Never infer an edition from a bare A03 or equate Web, API and Mobile families.
OWASP_ID = re.compile(
    r"(?<![A-Z0-9_])(API|A|M)\s*(\d{1,2})\s*[:\-\u2010-\u2015\u2212]\s*(20\d{2})(?![A-Z0-9])",
    re.IGNORECASE,
)


def extract_owasp(value: str) -> list[str]:
    """Extract deduplicated valid versioned Top 10 keys; preserve originals elsewhere."""
    text = unicodedata.normalize('NFKC', value)
    return sorted({f'{prefix.upper()}{int(number):02d}:{year}'
                   for prefix, number, year in OWASP_ID.findall(text) if 1 <= int(number) <= 10})


def canonical_owasp(values: Iterable[str] | str) -> list[str]:
    if isinstance(values, str):
        values = [values]
    return sorted({ref for value in values if isinstance(value, str) for ref in extract_owasp(value)})


def normalize_owasp(value: str) -> str:
    """Normalize a single reference, retaining unknown text for compatibility."""
    refs = extract_owasp(value)
    return refs[0] if len(refs) == 1 else value.strip().upper()
