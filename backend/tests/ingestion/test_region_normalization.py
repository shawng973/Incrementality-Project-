"""
Tests for region_normalization.py
"""

import pandas as pd
import pytest

from app.services.ingestion.region_normalization import (
    normalize_regions,
    RegionGranularity,
    _normalize_state,
    _normalize_dma,
    _normalize_zip,
    _VALID_STATE_ABBRS,
)


# ---------------------------------------------------------------------------
# State normalization
# ---------------------------------------------------------------------------


def test_valid_state_abbreviation_uppercase_passes():
    s = pd.Series(["CA", "NY", "TX"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert result.is_valid
    assert list(result.normalized_series) == ["CA", "NY", "TX"]


def test_lowercase_state_abbreviation_uppercased():
    s = pd.Series(["ca", "ny", "tx"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert result.is_valid
    assert list(result.normalized_series) == ["CA", "NY", "TX"]


def test_full_state_name_converted_to_abbreviation():
    s = pd.Series(["California", "New York", "Texas"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert result.is_valid
    assert list(result.normalized_series) == ["CA", "NY", "TX"]


def test_full_state_name_case_insensitive():
    s = pd.Series(["california", "CALIFORNIA", "California"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert all(v == "CA" for v in result.normalized_series)


def test_all_50_state_abbreviations_valid():
    s = pd.Series(sorted(_VALID_STATE_ABBRS))
    result = normalize_regions(s, RegionGranularity.STATE)
    assert result.is_valid
    assert len(result.unrecognized) == 0


def test_invalid_state_flagged():
    s = pd.Series(["CA", "ZZ", "NY"])  # ZZ is not a state
    result = normalize_regions(s, RegionGranularity.STATE)
    assert not result.is_valid
    assert "ZZ" in result.unrecognized


def test_invalid_state_generates_error_message():
    s = pd.Series(["INVALID"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert len(result.errors) > 0
    assert "INVALID" in result.errors[0]


def test_dc_recognized_as_valid_state():
    s = pd.Series(["DC", "Washington DC", "Washington D.C."])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert result.is_valid


def test_normalize_state_function_directly():
    assert _normalize_state("california") == ("CA", True)
    assert _normalize_state("CA") == ("CA", True)
    assert _normalize_state("ca") == ("CA", True)
    assert _normalize_state("ZZ")[1] is False


# ---------------------------------------------------------------------------
# DMA normalization
# ---------------------------------------------------------------------------


def test_valid_dma_code_as_integer_string():
    s = pd.Series(["501", "803", "623"])
    result = normalize_regions(s, RegionGranularity.DMA)
    assert result.is_valid


def test_dma_code_zero_padded_to_3_digits():
    s = pd.Series(["100", "200"])
    result = normalize_regions(s, RegionGranularity.DMA)
    assert list(result.normalized_series) == ["100", "200"]


def test_dma_code_with_leading_zeros_normalized():
    s = pd.Series(["501"])
    result = normalize_regions(s, RegionGranularity.DMA)
    assert result.normalized_series[0] == "501"


def test_short_dma_code_zero_padded():
    """DMA code 100 should output as '100', code 39 → '039'."""
    s = pd.Series(["39"])
    result = normalize_regions(s, RegionGranularity.DMA)
    assert result.normalized_series[0] == "039"


def test_dma_out_of_range_flagged():
    s = pd.Series(["501", "9999"])  # 9999 out of range
    result = normalize_regions(s, RegionGranularity.DMA)
    assert not result.is_valid
    assert "9999" in result.unrecognized


def test_non_numeric_dma_flagged():
    s = pd.Series(["LosAngeles"])
    result = normalize_regions(s, RegionGranularity.DMA)
    assert not result.is_valid


def test_normalize_dma_function_directly():
    assert _normalize_dma("501") == ("501", True)
    assert _normalize_dma("039") == ("039", True)
    assert _normalize_dma("39") == ("039", True)
    assert _normalize_dma("9999")[1] is False
    assert _normalize_dma("abc")[1] is False


# ---------------------------------------------------------------------------
# ZIP normalization
# ---------------------------------------------------------------------------


def test_5_digit_zip_is_valid():
    s = pd.Series(["90210", "10001", "02134"])
    result = normalize_regions(s, RegionGranularity.ZIP)
    assert result.is_valid
    assert list(result.normalized_series) == ["90210", "10001", "02134"]


def test_short_zip_zero_padded():
    s = pd.Series(["1234"])  # should become "01234"
    result = normalize_regions(s, RegionGranularity.ZIP)
    assert result.normalized_series[0] == "01234"
    assert result.is_valid


def test_zip_with_dash_stripped():
    """ZIP+4 format: strip the +4 suffix (non-digit characters removed)."""
    # "90210-1234" → digits = "902101234" → 9 digits → invalid (too long)
    s = pd.Series(["90210-1234"])
    result = normalize_regions(s, RegionGranularity.ZIP)
    assert not result.is_valid  # >5 digits after stripping


def test_zip_with_alpha_chars_flagged():
    s = pd.Series(["ABCDE"])
    result = normalize_regions(s, RegionGranularity.ZIP)
    assert not result.is_valid


def test_normalize_zip_function_directly():
    assert _normalize_zip("90210") == ("90210", True)
    assert _normalize_zip("1234") == ("01234", True)
    assert _normalize_zip("02134") == ("02134", True)
    assert _normalize_zip("123456")[1] is False  # >5 digits
    assert _normalize_zip("ABC")[1] is False


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------


def test_null_values_flagged_as_unrecognized():
    s = pd.Series(["CA", None, "NY"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert not result.is_valid
    assert len(result.unrecognized) == 1


# ---------------------------------------------------------------------------
# Partial failures
# ---------------------------------------------------------------------------


def test_partial_failure_reports_count():
    s = pd.Series(["CA", "ZZ", "XX", "NY"])
    result = normalize_regions(s, RegionGranularity.STATE)
    assert len(result.unrecognized) == 2


def test_error_message_includes_sample_of_bad_identifiers():
    bad = [f"BAD{i}" for i in range(10)]
    s = pd.Series(bad)
    result = normalize_regions(s, RegionGranularity.STATE)
    assert len(result.errors) > 0
    # Error should mention at least one bad identifier
    assert any(b in result.errors[0] for b in bad[:5])
