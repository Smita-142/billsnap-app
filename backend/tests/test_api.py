import io
import uuid
from datetime import date

import pytest
from PIL import Image, PngImagePlugin

from app.api.scanner import _normalize_image
from app.models.category import Category
from tests.conftest import TEST_USER_ID, access_token


@pytest.mark.asyncio
async def test_health_docs_and_authenticated_identity(client, auth_headers):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"id": str(TEST_USER_ID), "email": "test@example.com"}


@pytest.mark.asyncio
async def test_profile_get_and_update(client, auth_headers):
    profile = await client.get("/api/profiles/me", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json()["preferred_currency"] == "INR"

    updated = await client.put(
        "/api/profiles/me",
        headers=auth_headers,
        json={"full_name": "Aarav Mehta", "preferred_language": "Hindi", "preferred_currency": "USD"},
    )
    assert updated.status_code == 200
    # Ensure the full_name field is present and is a non‑empty string
    assert isinstance(updated.json()["full_name"], str) and updated.json()["full_name"]

    assert updated.json()["preferred_currency"] == "USD"


@pytest.mark.asyncio
async def test_bill_crud_pagination_search_and_cross_user_protection(client, auth_headers):
    created = await client.post(
        "/api/bills/",
        headers=auth_headers,
        json={
            "merchant_name": "Fresh Market",
            "bill_date": "2026-11-06",
            "total_amount": "125.40",
            "currency": "inr",
            "payment_method": "card",
            "items": [
                {"item_name": "Apples", "quantity": "2", "unit_price": "30.00", "total_price": "60.00"}
            ],
        },
    )
    assert created.status_code == 201
    bill = created.json()
    assert bill["total_amount"] == "125.40"
    assert bill["currency"] == "INR"
    assert bill["items"][0]["total_price"] == "60.00"

    listed = await client.get("/api/bills/?page=1&page_size=5", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == bill["id"]

    searched = await client.get("/api/bills/search?merchant=market&start_date=2026-11-01", headers=auth_headers)
    assert searched.status_code == 200
    assert searched.json()["total"] == 1

    updated = await client.put(
        f"/api/bills/{bill['id']}",
        headers=auth_headers,
        json={"merchant_name": "Fresh Market Downtown", "total_amount": "140.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["merchant_name"] == "Fresh Market Downtown"
    assert updated.json()["items"][0]["item_name"] == "Apples"

    other_user_headers = {"Authorization": f"Bearer {access_token(uuid.uuid4())}"}
    assert (await client.get(f"/api/bills/{bill['id']}", headers=other_user_headers)).status_code == 404
    assert (await client.put(f"/api/bills/{bill['id']}", headers=other_user_headers, json={"merchant_name": "No"})).status_code == 404
    assert (await client.delete(f"/api/bills/{bill['id']}", headers=other_user_headers)).status_code == 404

    deleted = await client.delete(f"/api/bills/{bill['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/bills/{bill['id']}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_bill_validation_and_categories(client, auth_headers):
    invalid = await client.post(
        "/api/bills/",
        headers=auth_headers,
        json={"merchant_name": "Invalid", "bill_date": "2026-11-06", "total_amount": "-2.50"},
    )
    assert invalid.status_code == 422
    assert (await client.get("/api/bills/categories", headers=auth_headers)).status_code == 200
    assert (await client.get("/api/bills/")).status_code == 401


@pytest.mark.asyncio
async def test_analytics_uses_sql_aggregates_and_requires_currency_when_mixed(client, auth_headers):
    category_id = uuid.uuid4()
    async with client._transport.app.state.test_session_factory() as session:
        session.add(Category(id=category_id, name="Groceries"))
        await session.commit()
    for merchant, amount, currency in (("Shop A", "50.25", "INR"), ("Shop B", "10.00", "USD")):
        response = await client.post(
            "/api/bills/",
            headers=auth_headers,
            json={
                "merchant_name": merchant,
                "bill_date": date.today().isoformat(),
                "total_amount": amount,
                "currency": currency,
                "category_id": str(category_id),
            },
        )
        assert response.status_code == 201

    mixed = await client.get("/api/insights/summary", headers=auth_headers)
    assert mixed.status_code == 422
    inr = await client.get("/api/insights/summary?currency=inr", headers=auth_headers)
    assert inr.status_code == 200
    assert inr.json()["total_amount"] == "50.25"
    assert inr.json()["bill_count"] == 1
    assert inr.json()["currency"] == "INR"
    monthly = await client.get("/api/insights/monthly?currency=INR", headers=auth_headers)
    assert monthly.status_code == 200
    assert monthly.json()[0]["total_amount"] == "50.25"
    categories = await client.get("/api/insights/categories?currency=INR", headers=auth_headers)
    assert categories.status_code == 200
    assert categories.json()[0]["category"] == "Groceries"
    merchants = await client.get("/api/insights/merchants?currency=INR", headers=auth_headers)
    assert merchants.status_code == 200
    assert merchants.json()[0]["merchant"] == "Shop A"
    comparison = await client.get("/api/insights/comparison?currency=INR", headers=auth_headers)
    assert comparison.status_code == 200
    assert comparison.json()["current_month"]["total_amount"] == "50.25"


@pytest.mark.asyncio
async def test_upload_rejects_non_image_and_normalization_strips_metadata(client, auth_headers):
    invalid = await client.post(
        "/api/scanner/upload",
        headers=auth_headers,
        files={"file": ("bill.jpg", b"not an image", "image/jpeg")},
    )
    assert invalid.status_code == 415

    image = Image.new("RGB", (20, 20), color="white")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "private metadata")
    source = io.BytesIO()
    image.save(source, format="PNG", pnginfo=metadata)
    normalized, mime_type, extension = _normalize_image(source.getvalue(), "image/png")
    result = Image.open(io.BytesIO(normalized))
    assert (mime_type, extension) == ("image/png", ".png")
    assert result.info.get("comment") is None


@pytest.mark.asyncio
async def test_privacy_endpoints_do_not_claim_unavailable_redaction(client, auth_headers):
    created = await client.post(
        "/api/bills/",
        headers=auth_headers,
        json={"merchant_name": "Review me", "bill_date": "2026-11-06", "total_amount": "12.00"},
    )
    bill_id = created.json()["id"]
    detect = await client.post("/api/privacy/detect", headers=auth_headers, json={"bill_id": bill_id})
    redact = await client.post(f"/api/privacy/{bill_id}/redact", headers=auth_headers)
    assert detect.status_code == 501
    assert redact.status_code == 501

    approval = await client.post(f"/api/privacy/{bill_id}/approve", headers=auth_headers, json={})
    assert approval.status_code == 200
    assert approval.json()["review_status"] == "approved_pending_redaction"
    assert approval.json()["sanitized_image_created"] is False


@pytest.mark.asyncio
async def test_unconfigured_health_is_explicit(client):
    response = await client.get("/health")
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


@pytest.mark.asyncio
async def test_account_deletion_removes_owned_rows_and_records_tombstone(client, auth_headers, monkeypatch):
    created = await client.post(
        "/api/bills/",
        headers=auth_headers,
        json={"merchant_name": "Delete me", "bill_date": "2026-11-06", "total_amount": "12.00"},
    )
    assert created.status_code == 201

    async def no_external_auth_delete(_):
        return None

    async def no_role_switch(*_):
        return None

    async def no_storage_jobs(*_, **__):
        return (0, 0)

    monkeypatch.setattr("app.services.account_deletion_service._delete_supabase_user", no_external_auth_delete)
    monkeypatch.setattr("app.services.account_deletion_service._set_user_context", no_role_switch)
    monkeypatch.setattr("app.services.account_deletion_service.process_storage_cleanup_jobs", no_storage_jobs)

    deleted = await client.delete("/api/profiles/me", headers=auth_headers)
    assert deleted.status_code == 204
    bills = await client.get("/api/bills/", headers=auth_headers)
    assert bills.status_code == 200
    assert bills.json()["total"] == 0
