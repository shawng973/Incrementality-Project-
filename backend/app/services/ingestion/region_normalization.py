"""
Region Identifier Normalization.

Normalizes geo identifiers to canonical forms used internally:
  - State:  2-letter uppercase abbreviation (e.g., "California" → "CA")
  - DMA:    Numeric DMA code as string, zero-padded to 3 digits (e.g., "801", "039")
  - ZIP:    5-digit string, zero-padded (e.g., "1234" → "01234")

Unrecognized identifiers are flagged as errors so the user can correct them
before analysis begins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class RegionGranularity(str, Enum):
    STATE = "state"
    DMA = "dma"
    ZIP = "zip"


@dataclass
class NormalizationResult:
    """Output of normalize_regions()."""

    normalized_series: pd.Series   # cleaned region identifiers
    unrecognized: list[str]         # identifiers that could not be normalized
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# US State lookup tables
# ---------------------------------------------------------------------------

# Full name → abbreviation (lowercase keys for case-insensitive matching)
_STATE_NAME_TO_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
}

# Valid 2-letter abbreviations (uppercase)
_VALID_STATE_ABBRS: set[str] = set(_STATE_NAME_TO_ABBR.values())

# DMA code range — accept any 1-3 digit numeric code.
# Production lookup against a full DMA table happens in the API layer.
_DMA_MIN = 1
_DMA_MAX = 999

# ZIP code: 5-digit US postal code
_ZIP_PATTERN = re.compile(r"^\d{1,5}$")


def normalize_regions(
    series: pd.Series,
    granularity: RegionGranularity,
) -> NormalizationResult:
    """
    Normalize a Series of region identifiers.

    Args:
        series:      Raw region identifier column from uploaded CSV.
        granularity: Geo granularity (state, dma, zip).

    Returns:
        NormalizationResult with normalized identifiers and any issues.
    """
    normalized: list[str] = []
    unrecognized: list[str] = []

    for raw in series:
        if pd.isna(raw):
            unrecognized.append(str(raw))
            normalized.append("")
            continue

        raw_str = str(raw).strip()

        if granularity == RegionGranularity.STATE:
            norm, ok = _normalize_state(raw_str)
        elif granularity == RegionGranularity.DMA:
            norm, ok = _normalize_dma(raw_str)
        elif granularity == RegionGranularity.ZIP:
            norm, ok = _normalize_zip(raw_str)
        else:
            norm, ok = raw_str, True  # unknown granularity — pass through

        if ok:
            normalized.append(norm)
        else:
            unrecognized.append(raw_str)
            normalized.append(raw_str)  # preserve original in output

    result = NormalizationResult(
        normalized_series=pd.Series(normalized, index=series.index),
        unrecognized=unrecognized,
        is_valid=len(unrecognized) == 0,
    )

    if unrecognized:
        sample = unrecognized[:5]
        result.errors.append(
            f"{len(unrecognized)} region identifier(s) could not be normalized "
            f"as {granularity.value}. Sample: {sample}. "
            "Fix these identifiers before uploading."
        )

    return result


# ---------------------------------------------------------------------------
# Per-granularity normalizers
# ---------------------------------------------------------------------------


def _normalize_state(raw: str) -> tuple[str, bool]:
    """Return (normalized_abbr, is_valid)."""
    # Already a valid 2-letter abbreviation
    upper = raw.upper()
    if upper in _VALID_STATE_ABBRS:
        return upper, True

    # Full name lookup (case-insensitive)
    lower = raw.lower()
    if lower in _STATE_NAME_TO_ABBR:
        return _STATE_NAME_TO_ABBR[lower], True

    return raw, False


def _normalize_dma(raw: str) -> tuple[str, bool]:
    """Return (zero-padded 3-digit DMA code string, is_valid)."""
    # Strip leading zeros then check numeric range
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return raw, False
    code = int(digits)
    if _DMA_MIN <= code <= _DMA_MAX:
        return f"{code:03d}", True
    return raw, False


def _normalize_zip(raw: str) -> tuple[str, bool]:
    """Return (5-digit zero-padded ZIP string, is_valid)."""
    digits = re.sub(r"[^\d]", "", raw)
    if not digits or len(digits) > 5:
        return raw, False
    if not _ZIP_PATTERN.match(digits):
        return raw, False
    return digits.zfill(5), True
