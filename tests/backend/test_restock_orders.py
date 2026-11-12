"""
Tests for restocking order API endpoints.
"""
import json
from datetime import datetime, timedelta

import pytest

import main


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """Clear the in-memory restock orders before and after each test."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


@pytest.fixture
def restock_payload():
    """A valid restock order request: total 450*12.5 + 100*45.0 = 10125.0."""
    return {
        "budget": 20000,
        "items": [
            {
                "sku": "WDG-001",
                "name": "Industrial Widget Type A",
                "quantity": 450,
                "unit_cost": 12.5,
                "lead_time_days": 10,
            },
            {
                "sku": "BRG-102",
                "name": "Steel Bearing Assembly",
                "quantity": 100,
                "unit_cost": 45.0,
                "lead_time_days": 14,
            },
        ],
    }


class TestRestockOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_demand_forecasts_include_cost_and_lead_time(self, client):
        """Test that demand forecasts expose unit cost and lead time for restocking."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_get_restock_orders_empty(self, client):
        """Test that no restock orders exist initially."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client, restock_payload):
        """Test submitting a valid restock order."""
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["budget"] == 20000
        assert len(order["items"]) == 2
        assert abs(order["total_value"] - 10125.0) < 0.01

    def test_restock_order_lead_time_calculation(self, client, restock_payload):
        """Test that lead time is the longest item lead time and drives expected delivery."""
        order = client.post("/api/restock-orders", json=restock_payload).json()

        assert order["lead_time_days"] == 14
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery - order_date == timedelta(days=14)

    def test_restock_order_total_ignores_client_total(self, client, restock_payload):
        """Test that the server computes the total from items, not from the client."""
        restock_payload["total_value"] = 1
        order = client.post("/api/restock-orders", json=restock_payload).json()
        assert abs(order["total_value"] - 10125.0) < 0.01

    def test_restock_order_uses_forecast_prices(self, client, restock_payload):
        """Test that client-supplied unit costs and lead times are ignored in favor of forecast data."""
        restock_payload["items"][0]["unit_cost"] = 0.01
        restock_payload["items"][1]["lead_time_days"] = 1
        order = client.post("/api/restock-orders", json=restock_payload).json()

        assert abs(order["total_value"] - 10125.0) < 0.01
        assert order["lead_time_days"] == 14
        assert order["items"][0]["unit_cost"] == 12.5

    def test_create_restock_order_exact_budget(self, client, restock_payload):
        """Test that an order whose total equals the budget is accepted."""
        restock_payload["budget"] = 10125.0
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 201

    def test_create_restock_order_unknown_sku(self, client, restock_payload):
        """Test that SKUs not present in the demand forecast are rejected."""
        restock_payload["items"][0]["sku"] = "NOPE-999"
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    def test_create_restock_order_duplicate_sku(self, client, restock_payload):
        """Test that the same SKU cannot appear twice in one order."""
        restock_payload["items"][1]["sku"] = restock_payload["items"][0]["sku"]
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 400

    def test_create_restock_order_non_finite_budget(self, client, restock_payload):
        """Test that a non-finite budget is rejected instead of corrupting stored orders."""
        restock_payload["budget"] = float("inf")
        # httpx refuses to encode Infinity, so send the (Python-style) JSON body directly
        body = json.dumps(restock_payload)
        response = client.post(
            "/api/restock-orders", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_over_budget(self, client, restock_payload):
        """Test that an order exceeding the budget is rejected."""
        restock_payload["budget"] = 5000
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 400

        data = response.json()
        assert "exceeds budget" in data["detail"].lower()
        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_no_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restock-orders", json={"budget": 1000, "items": []})
        assert response.status_code == 422

    def test_create_restock_order_invalid_quantity(self, client, restock_payload):
        """Test that zero or negative quantities are rejected."""
        restock_payload["items"][0]["quantity"] = 0
        response = client.post("/api/restock-orders", json=restock_payload)
        assert response.status_code == 422

    def test_get_restock_orders_newest_first(self, client, restock_payload):
        """Test that submitted orders are listed newest first with sequential numbers."""
        first = client.post("/api/restock-orders", json=restock_payload).json()
        second = client.post("/api/restock-orders", json=restock_payload).json()
        assert first["order_number"] != second["order_number"]

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]
