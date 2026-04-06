"""
Tests for /api/tests endpoints.

Covers:
- Authentication (401 for unauthenticated)
- Authorization (403 for cross-workspace access)
- CRUD operations
- Input validation (422)
- Pagination
"""

import uuid
import pytest


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_unauthenticated_list_returns_401(client_unauthenticated):
    response = client_unauthenticated.get("/api/tests/")
    assert response.status_code == 401


def test_unauthenticated_create_returns_401(client_unauthenticated):
    response = client_unauthenticated.post(
        "/api/tests/",
        json={"name": "Test", "test_type": "geo_split", "channel": "ctv"},
    )
    assert response.status_code == 401


def test_unauthenticated_get_returns_401(client_unauthenticated):
    response = client_unauthenticated.get(f"/api/tests/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Authorization (cross-workspace)
# ---------------------------------------------------------------------------


def test_user_cannot_access_other_workspace_test(client_a, client_b):
    # client_b creates a test; client_a tries to access it
    r = client_b.post("/api/tests/", json={"name": "Workspace B Only"})
    test_id = r.json()["id"]
    response = client_a.get(f"/api/tests/{test_id}")
    assert response.status_code == 403


def test_user_can_access_own_workspace_test(client_a):
    r = client_a.post("/api/tests/", json={"name": "Accessible by A"})
    test_id = r.json()["id"]
    response = client_a.get(f"/api/tests/{test_id}")
    assert response.status_code == 200


def test_super_admin_can_access_any_workspace_test(client_b, client_super_admin):
    r = client_b.post("/api/tests/", json={"name": "Super Admin Visibility"})
    test_id = r.json()["id"]
    response = client_super_admin.get(f"/api/tests/{test_id}")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_test_returns_201_with_id(client_a):
    response = client_a.post(
        "/api/tests/",
        json={
            "name": "Q1 CTV Test",
            "test_type": "geo_split",
            "channel": "ctv",
            "region_granularity": "state",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "Q1 CTV Test"
    assert data["status"] == "draft"


def test_create_test_assigns_to_authenticated_workspace(client_a):
    from tests.api.conftest import WORKSPACE_A_ID

    response = client_a.post("/api/tests/", json={"name": "Workspace Test"})
    assert response.status_code == 201
    assert response.json()["workspace_id"] == str(WORKSPACE_A_ID)


def test_create_test_missing_name_returns_422(client_a):
    response = client_a.post("/api/tests/", json={"test_type": "geo_split"})
    assert response.status_code == 422


def test_create_test_invalid_test_type_returns_422(client_a):
    response = client_a.post(
        "/api/tests/", json={"name": "Test", "test_type": "invalid_type"}
    )
    assert response.status_code == 422


def test_create_test_n_cells_out_of_range_returns_422(client_a):
    response = client_a.post(
        "/api/tests/", json={"name": "Test", "n_cells": 5}  # max is 4
    )
    assert response.status_code == 422


def test_create_test_n_cells_1_returns_422(client_a):
    response = client_a.post(
        "/api/tests/", json={"name": "Test", "n_cells": 1}  # min is 2
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_returns_only_own_workspace_tests(client_a, client_b):
    """
    Each client creates a uniquely-named test and verifies workspace isolation.
    Creates test data via HTTP (no async fixture mixing).
    """
    unique_a = f"Isolation-Test-A-{uuid.uuid4().hex[:8]}"
    unique_b = f"Isolation-Test-B-{uuid.uuid4().hex[:8]}"

    r_a = client_a.post("/api/tests/", json={"name": unique_a})
    r_b = client_b.post("/api/tests/", json={"name": unique_b})
    assert r_a.status_code == 201
    assert r_b.status_code == 201

    list_a = client_a.get("/api/tests/")
    list_b = client_b.get("/api/tests/")

    names_a = {item["name"] for item in list_a.json()["items"]}
    names_b = {item["name"] for item in list_b.json()["items"]}

    assert unique_a in names_a, "client_a should see its own test"
    assert unique_b not in names_a, "client_a should NOT see client_b's test"
    assert unique_b in names_b, "client_b should see its own test"
    assert unique_a not in names_b, "client_b should NOT see client_a's test"


def test_list_pagination_returns_correct_page(client_a):
    # Create 5 tests
    for i in range(5):
        client_a.post("/api/tests/", json={"name": f"Pagination Test {i}"})

    page1 = client_a.get("/api/tests/?page=1&page_size=2")
    page2 = client_a.get("/api/tests/?page=2&page_size=2")

    assert page1.status_code == 200
    assert page2.status_code == 200
    assert len(page1.json()["items"]) == 2
    # Items on page 1 and 2 should be different
    ids_page1 = {item["id"] for item in page1.json()["items"]}
    ids_page2 = {item["id"] for item in page2.json()["items"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_response_includes_total(client_a):
    client_a.post("/api/tests/", json={"name": "Total Test"})
    response = client_a.get("/api/tests/")
    assert response.status_code == 200
    assert "total" in response.json()
    assert response.json()["total"] >= 1


def test_list_filter_by_status(client_a):
    # Create one draft and one active test
    client_a.post("/api/tests/", json={"name": "Draft Test"})
    create_resp = client_a.post("/api/tests/", json={"name": "Active Test"})
    test_id = create_resp.json()["id"]
    client_a.patch(f"/api/tests/{test_id}", json={"status": "active"})

    draft_resp = client_a.get("/api/tests/?status=draft")
    active_resp = client_a.get("/api/tests/?status=active")

    assert all(item["status"] == "draft" for item in draft_resp.json()["items"])
    assert all(item["status"] == "active" for item in active_resp.json()["items"])


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_test_name(client_a):
    r = client_a.post("/api/tests/", json={"name": "Original Name"})
    test_id = r.json()["id"]
    response = client_a.patch(f"/api/tests/{test_id}", json={"name": "Updated Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_update_test_invalid_status_returns_422(client_a):
    r = client_a.post("/api/tests/", json={"name": "Status Test"})
    test_id = r.json()["id"]
    response = client_a.patch(f"/api/tests/{test_id}", json={"status": "invalid_status"})
    assert response.status_code == 422


def test_cannot_update_other_workspace_test(client_a, client_b):
    r = client_b.post("/api/tests/", json={"name": "B's Test"})
    test_id = r.json()["id"]
    response = client_a.patch(f"/api/tests/{test_id}", json={"name": "Hijacked"})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_test_returns_204(client_a):
    create_resp = client_a.post("/api/tests/", json={"name": "To Delete"})
    test_id = create_resp.json()["id"]
    delete_resp = client_a.delete(f"/api/tests/{test_id}")
    assert delete_resp.status_code == 204


def test_delete_test_then_get_returns_404(client_a):
    create_resp = client_a.post("/api/tests/", json={"name": "To Delete 2"})
    test_id = create_resp.json()["id"]
    client_a.delete(f"/api/tests/{test_id}")
    get_resp = client_a.get(f"/api/tests/{test_id}")
    assert get_resp.status_code == 404


def test_cannot_delete_other_workspace_test(client_a, client_b):
    r = client_b.post("/api/tests/", json={"name": "B Delete Test"})
    test_id = r.json()["id"]
    response = client_a.delete(f"/api/tests/{test_id}")
    assert response.status_code == 403


def test_delete_nonexistent_test_returns_404(client_a):
    response = client_a.delete(f"/api/tests/{uuid.uuid4()}")
    assert response.status_code == 404
