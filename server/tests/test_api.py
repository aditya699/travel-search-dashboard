from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

HEAD = {"X-User-Email": "head.analytics@travel.example"}
DELHI = {"X-User-Email": "delhi.desk@travel.example"}
MUMBAI = {"X-User-Email": "Mumbai.Desk@travel.example"}  # case does not matter


@pytest.fixture(scope="module")
def client(built):
    with TestClient(create_app(built)) as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["warehouse"] is True


def test_sign_in_is_required(client):
    assert client.get("/api/summary").status_code == 401
    assert client.get("/api/summary", headers={"X-User-Email": "x@y.z"}).status_code == 403


def test_rls_limits_routes_to_the_viewers_airports(client):
    head = {r["origin"] for r in client.get("/api/routes", headers=HEAD).json()}
    delhi = {r["origin"] for r in client.get("/api/routes", headers=DELHI).json()}
    mumbai = {r["origin"] for r in client.get("/api/routes", headers=MUMBAI).json()}
    assert head == {"DEL", "BOM", "BLR"}
    assert delhi == {"DEL"}
    assert mumbai == {"BOM"}


def test_rls_applies_before_aggregation(client):
    head = client.get("/api/summary", headers=HEAD).json()
    delhi = client.get("/api/summary", headers=DELHI).json()
    assert 0 < delhi["quotes"] < head["quotes"]
    assert delhi["routes"] < head["routes"]
    rows = client.get("/api/cheapest", headers=DELHI).json()
    assert rows and all(r["origin"] == "DEL" for r in rows)


def test_hidden_route_is_not_found(client):
    assert client.get("/api/trend", params={"route": "BOM-DEL"}, headers=DELHI).status_code == 404
    assert client.get("/api/trend", params={"route": "BOM-DEL"}, headers=MUMBAI).status_code == 200


def test_charts_have_data(client):
    trend = client.get("/api/trend", params={"route": "DEL-BOM"}, headers=HEAD).json()
    lead = client.get("/api/lead-time", params={"route": "DEL-BOM"}, headers=HEAD).json()
    sites = client.get("/api/sites", headers=HEAD).json()
    quality = client.get("/api/quality", headers=HEAD).json()
    assert trend and lead and sites
    assert {s["site_key"] for s in quality["by_site"]} >= {"skybazaar", "ghoomo"}
    assert quality["top_reasons"]
