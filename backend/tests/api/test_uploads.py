"""
Tests for /api/tests/{test_id}/uploads endpoints.

Covers:
- Authentication (401)
- Authorization (403 cross-workspace)
- Upload happy path: 201, record created, stats populated
- Upload error paths: non-CSV, invalid columns, too few rows, bad upload_type
- List uploads
- Delete upload
"""
from __future__ import annotations

import io
import uuid

import pandas as pd
import pytest

from tests.api.conftest import WORKSPACE_A_ID, WORKSPACE_B_ID, USER_A_ID


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _make_valid_csv(n_rows: int = 50, *, include_spend: bool = False) -> bytes:
    """Build a minimal valid CSV with canonical column names."""
    import numpy as np

    rng = np.random.default_rng(42)
    geos = [f"CA", "TX", "FL", "NY", "WA", "OR", "CO", "AZ", "GA", "IL"] * (n_rows // 10 + 1)
    periods = [f"2025-0{(i % 8) + 1}-01" for i in range(n_rows)]
    data = {
        "region": geos[:n_rows],
        "period": periods,
        "metric": rng.uniform(10_000, 100_000, n_rows).round(2),
    }
    if include_spend:
        data["spend"] = rng.uniform(1_000, 10_000, n_rows).round(2)
    return pd.DataFrame(data).to_csv(index=False).encode()


def _make_csv_bytes(content: str) -> bytes:
    return content.encode()


def _upload_file(client, test_id: str, csv_bytes: bytes, upload_type: str = "historical", filename: str = "data.csv"):
    return client.post(
        f"/api/tests/{test_id}/uploads",
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        params={"upload_type": upload_type},
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_upload_unauthenticated_returns_401(client_unauthenticated):
    r = client_unauthenticated.post(
        f"/api/tests/{uuid.uuid4()}/uploads",
        files={"file": ("data.csv", io.BytesIO(b"region,period,metric"), "text/csv")},
    )
    assert r.status_code == 401


def test_list_uploads_unauthenticated_returns_401(client_unauthenticated):
    r = client_unauthenticated.get(f"/api/tests/{uuid.uuid4()}/uploads")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_upload_cross_workspace_returns_403(client_a, client_b):
    r = client_b.post("/api/tests/", json={"name": "B Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv())
    assert resp.status_code == 403


def test_list_uploads_cross_workspace_returns_403(client_a, client_b):
    r = client_b.post("/api/tests/", json={"name": "B Test"})
    tid = r.json()["id"]
    resp = client_a.get(f"/api/tests/{tid}/uploads")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Upload — happy path
# ---------------------------------------------------------------------------


def test_upload_valid_csv_returns_201(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv())
    assert resp.status_code == 201


def test_upload_returns_filename(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv(), filename="my_data.csv")
    assert resp.json()["filename"] == "my_data.csv"


def test_upload_returns_row_count(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv(n_rows=50))
    assert resp.json()["row_count"] == 50


def test_upload_returns_geo_count(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv(n_rows=50))
    assert resp.json()["geo_count"] is not None
    assert resp.json()["geo_count"] > 0


def test_upload_returns_column_mapping(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv())
    mapping = resp.json()["column_mapping"]
    assert mapping is not None
    assert "region" in mapping.values()


def test_upload_assigns_correct_workspace(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv())
    assert resp.json()["workspace_id"] == str(WORKSPACE_A_ID)


def test_upload_results_type(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv(), upload_type="results")
    assert resp.status_code == 201
    assert resp.json()["upload_type"] == "results"


def test_upload_with_spend_column(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, _make_valid_csv(include_spend=True))
    assert resp.status_code == 201
    assert resp.json()["row_count"] == 50


# ---------------------------------------------------------------------------
# Upload — error paths
# ---------------------------------------------------------------------------


def test_upload_non_csv_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = client_a.post(
        f"/api/tests/{tid}/uploads",
        files={"file": ("report.xlsx", io.BytesIO(b"not a csv"), "application/vnd.ms-excel")},
    )
    # .xlsx extension rejected
    assert resp.status_code == 422


def test_upload_missing_required_columns_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    bad_csv = b"foo,bar,baz\n1,2,3\n4,5,6\n"
    resp = _upload_file(client_a, tid, bad_csv)
    assert resp.status_code == 422


def test_upload_too_few_rows_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    # Only 5 rows — below MIN_ROWS=30
    resp = _upload_file(client_a, tid, _make_valid_csv(n_rows=5))
    assert resp.status_code == 422


def test_upload_invalid_upload_type_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = client_a.post(
        f"/api/tests/{tid}/uploads",
        files={"file": ("data.csv", io.BytesIO(_make_valid_csv()), "text/csv")},
        params={"upload_type": "baseline"},
    )
    assert resp.status_code == 422


def test_upload_nonexistent_test_returns_404(client_a):
    resp = _upload_file(client_a, str(uuid.uuid4()), _make_valid_csv())
    assert resp.status_code == 404


def test_upload_malformed_csv_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Upload Test"})
    tid = r.json()["id"]
    resp = _upload_file(client_a, tid, b"\x00\x01\x02\x03binary garbage")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List uploads
# ---------------------------------------------------------------------------


def test_list_returns_uploaded_files(client_a):
    r = client_a.post("/api/tests/", json={"name": "List Test"})
    tid = r.json()["id"]
    _upload_file(client_a, tid, _make_valid_csv(), filename="first.csv")
    _upload_file(client_a, tid, _make_valid_csv(), filename="second.csv")

    resp = client_a.get(f"/api/tests/{tid}/uploads")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    filenames = {item["filename"] for item in data["items"]}
    assert "first.csv" in filenames
    assert "second.csv" in filenames


def test_list_empty_when_no_uploads(client_a):
    r = client_a.post("/api/tests/", json={"name": "Empty Uploads Test"})
    tid = r.json()["id"]
    resp = client_a.get(f"/api/tests/{tid}/uploads")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_does_not_include_other_test_uploads(client_a):
    r1 = client_a.post("/api/tests/", json={"name": "Test A"})
    r2 = client_a.post("/api/tests/", json={"name": "Test B"})
    tid_a = r1.json()["id"]
    tid_b = r2.json()["id"]

    _upload_file(client_a, tid_a, _make_valid_csv(), filename="for_a.csv")

    resp = client_a.get(f"/api/tests/{tid_b}/uploads")
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_upload_returns_204(client_a):
    r = client_a.post("/api/tests/", json={"name": "Delete Test"})
    tid = r.json()["id"]
    upload_r = _upload_file(client_a, tid, _make_valid_csv())
    upload_id = upload_r.json()["id"]

    resp = client_a.delete(f"/api/tests/{tid}/uploads/{upload_id}")
    assert resp.status_code == 204


def test_delete_upload_removes_from_list(client_a):
    r = client_a.post("/api/tests/", json={"name": "Delete Test"})
    tid = r.json()["id"]
    upload_r = _upload_file(client_a, tid, _make_valid_csv())
    upload_id = upload_r.json()["id"]

    client_a.delete(f"/api/tests/{tid}/uploads/{upload_id}")

    resp = client_a.get(f"/api/tests/{tid}/uploads")
    assert resp.json()["total"] == 0


def test_delete_nonexistent_upload_returns_404(client_a):
    r = client_a.post("/api/tests/", json={"name": "Delete Test"})
    tid = r.json()["id"]
    resp = client_a.delete(f"/api/tests/{tid}/uploads/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_cross_workspace_returns_403(client_a, client_b):
    r = client_b.post("/api/tests/", json={"name": "B Test"})
    tid = r.json()["id"]
    upload_r = _upload_file(client_b, tid, _make_valid_csv())
    upload_id = upload_r.json()["id"]

    resp = client_a.delete(f"/api/tests/{tid}/uploads/{upload_id}")
    assert resp.status_code == 403
